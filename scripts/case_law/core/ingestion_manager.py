"""
Core Ingestion Manager
Contains shared logic for scraping, caching, and storing case law documents.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.case_law.hybrid_extractor import HybridPrecedentExtractor
from src.services.case_law.scraper import CaseLawDocument, CaseLawScraper, Reference
from src.services.case_law.storage import CaseLawStorage

logger = setup_logger(__name__)


class IngestionManager:
    """
    Handles the end-to-end ingestion process for a specific court and year.
    Reusable by specific court scripts.
    """

    def __init__(self, court: str):
        self.court = court
        self.storage = CaseLawStorage()

        # Setup Supabase tracking client
        load_dotenv()
        sb_url = os.getenv("SUPABASE_URL")
        sb_key = os.getenv("SUPABASE_KEY")
        if sb_url and sb_key:
            self.sb_client = create_client(sb_url, sb_key)
        else:
            self.sb_client = None
            logger.warning("Supabase credentials missing, tracking disabled.")

    async def ingest_year(
        self, year: int, force_scrape: bool = False, subtype: str = None, use_ai: bool = True
    ) -> list[str]:
        """Run full ingestion for a year: Load/Scrape -> Extract -> Store -> Track.

        Returns list of failed case_id descriptions (empty if all succeeded).
        """
        start_time = time.time()
        use_ai = use_ai and getattr(config, "USE_AI_EXTRACTION", True)
        subtype_str = f" ({subtype})" if subtype else " (ALL)"
        extract_str = " + extract" if use_ai else " (regex only)"
        logger.info("🚀 Starting Ingestion: %s %s%s%s", self.court.upper(), year, subtype_str, extract_str)

        # 1. Resolve paths & load/scrape
        json_file, no_json_cache = self._resolve_json_path(year, subtype)
        tracking_id = self._init_tracking(year, subtype)
        documents = await self._load_or_scrape(year, subtype, json_file, no_json_cache, force_scrape, tracking_id)

        if not documents:
            logger.info("❌ No documents found.")
            self._track_status(
                year, "completed", total=0, processed=0, failed=0, tracking_id=tracking_id, subtype=subtype
            )
            return []

        # 1b. Skip documents whose content hasn't changed (hash-based idempotency)
        total_loaded = len(documents)
        skipped_unchanged = 0
        existing_hashes = self._fetch_existing_content_hashes(year)
        if existing_hashes:
            new_docs = []
            for d in documents:
                doc_hash = self.storage.compute_content_hash(d)
                stored_hash = existing_hashes.get(d.case_id)
                if stored_hash and stored_hash == doc_hash:
                    skipped_unchanged += 1
                else:
                    new_docs.append(d)
            if skipped_unchanged:
                logger.info("⏩ Skipping %s documents (content unchanged in Supabase)", skipped_unchanged)
            documents = new_docs

        if not documents:
            logger.info("✅ All documents already in Supabase with same content — nothing to process.")
            self._track_status(
                year,
                "completed",
                total=total_loaded,
                processed=total_loaded,
                failed=0,
                tracking_id=tracking_id,
                subtype=subtype,
            )
            return []

        # 2. Extraction (regex + optional LLM fallback for KKO precedents)
        # Always run extraction for supreme_court precedent; extractor uses config.USE_AI_EXTRACTION
        if self.court == "supreme_court" and subtype == "precedent":
            self._run_extraction(documents, json_file, no_json_cache, tracking_id)

        # 3. Store in Database & track progress
        stored_count, failed_ids = self._store_documents(documents, year, subtype, tracking_id)
        failed_count = len(failed_ids)

        # 4. Track completion: total = full year count; processed = in Supabase (skipped + stored); failed = this run
        processed_total = skipped_unchanged + stored_count
        final_status = "completed" if failed_count == 0 else "partial"
        self._track_status(
            year,
            final_status,
            total=total_loaded,
            processed=processed_total,
            failed=failed_count,
            last_case=documents[-1].case_id if documents else None,
            tracking_id=tracking_id,
            subtype=subtype,
        )

        elapsed = time.time() - start_time
        logger.info(
            "✅ COMPLETED: total=%s | in Supabase=%s (skipped %s, stored %s) | failed=%s | %.2fs",
            total_loaded,
            processed_total,
            skipped_unchanged,
            stored_count,
            failed_count,
            elapsed,
        )

        if failed_ids:
            logger.error("⚠️  FAILED DOCUMENTS for %s %s (%s):", year, subtype or "ALL", len(failed_ids))
            for fid in failed_ids:
                logger.error("  - %s", fid)

        return failed_ids

    async def ingest_case_ids(
        self,
        year: int,
        subtype: str,
        case_ids: list[str],
        use_ai: bool = True,
        update_json_cache: bool = True,
        json_only: bool = False,
    ) -> list[str]:
        """Run ingestion for specific case IDs only: Scrape -> Update JSON -> [Store in Supabase].

        If json_only=True: Only re-scrape and update the JSON file (full_text). No Supabase storage.
        Use this to fix empty full_text in JSON so PDF export / Drive upload has real content.

        Otherwise: Full flow (JSON update + extract + store in Supabase).

        Returns list of failed case_id descriptions (empty if all succeeded).
        """
        if not case_ids:
            logger.info("No case_ids provided.")
            return []
        start_time = time.time()
        use_ai = use_ai and getattr(config, "USE_AI_EXTRACTION", True)
        mode = "JSON-only (no Supabase)" if json_only else "JSON + Supabase"
        logger.info("🚀 Ingesting %s case(s) [%s]: %s", len(case_ids), mode, case_ids)

        json_file, _ = self._resolve_json_path(year, subtype)
        tracking_id = None if json_only else self._init_tracking(year, subtype)

        async with CaseLawScraper() as scraper:
            documents = await scraper.fetch_cases_by_ids(self.court, year, subtype, case_ids)

        if not documents:
            logger.warning("No documents fetched for case_ids=%s", case_ids)
            if not json_only:
                self._track_status(
                    year, "completed", total=0, processed=0, failed=0, tracking_id=tracking_id, subtype=subtype
                )
            return list(case_ids)

        if update_json_cache and json_file.exists():
            self._merge_docs_into_json(documents, json_file)

        if json_only:
            elapsed = time.time() - start_time
            updated = sum(1 for d in documents if (getattr(d, "full_text", None) or "").strip())
            logger.info(
                "✅ JSON-only done: %s/%s cases updated in %s | %.2fs", updated, len(documents), json_file.name, elapsed
            )
            return []

        if self.court == "supreme_court" and subtype == "precedent":
            self._run_extraction(documents, json_file, False, tracking_id)

        stored_count, failed_ids = self._store_documents(documents, year, subtype, tracking_id)
        failed_count = len(failed_ids)
        self._track_status(
            year,
            "completed" if failed_count == 0 else "partial",
            total=len(documents),
            processed=stored_count,
            failed=failed_count,
            last_case=documents[-1].case_id if documents else None,
            tracking_id=tracking_id,
            subtype=subtype,
        )
        elapsed = time.time() - start_time
        logger.info("✅ Case-ID ingestion done: %s stored, %s failed in %.2fs", stored_count, failed_count, elapsed)
        if failed_ids:
            for fid in failed_ids:
                logger.error("  - %s", fid)
        return failed_ids

    def _merge_docs_into_json(self, new_documents: list[CaseLawDocument], json_file: Path) -> None:
        """Load JSON cache, replace entries with same case_id as in new_documents, save.
        Skips docs with empty full_text so we don't overwrite good content with empty."""
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Could not load JSON for merge: %s", e)
            return
        # Boilerplate-only content (Finlex page without case text) - treat as empty
        _BOILERPLATE_MAX = 300
        _BOILERPLATE_MARKERS = ("Korkeimman oikeuden verkkosivuilla", "Vuosilta 1926")

        def _is_meaningful_content(ft: str) -> bool:
            return (
                bool(ft)
                and len(ft) >= 100
                and not (len(ft) < _BOILERPLATE_MAX and all(m in ft for m in _BOILERPLATE_MARKERS))
            )

        new_by_id = {d.case_id: d for d in new_documents}
        updated = 0
        skipped_empty = 0
        for i, item in enumerate(data):
            cid = item.get("case_id")
            if cid in new_by_id:
                doc = new_by_id[cid]
                ft = (getattr(doc, "full_text", None) or "").strip()
                if not _is_meaningful_content(ft):
                    logger.warning(
                        "Skipping merge for %s (scraped full_text empty or boilerplate only; preserve existing)", cid
                    )
                    skipped_empty += 1
                    continue
                data[i] = doc.to_dict()
                data[i]["references"] = [vars(r) for r in doc.references]
                updated += 1
        if not updated:
            if skipped_empty:
                logger.info("No entries updated (skipped %s with empty/boilerplate full_text)", skipped_empty)
            return
        try:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            extra = f" (skipped {skipped_empty} empty)" if skipped_empty else ""
            logger.info("Updated %s entries in %s%s", updated, json_file.name, extra)
        except Exception as e:
            logger.warning("Could not save JSON after merge: %s", e)

    # ------------------------------------------------------------------
    #  ingest_year helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_json_path(year: int, subtype: str | None) -> tuple[Path, bool]:
        """Return (json_file, no_json_cache) for a given year/subtype."""
        subtype_dir_map = {
            "precedent": "precedents",
            "ruling": "rulings",
            "leave_to_appeal": "leaves_to_appeal",
            "decision": "decisions",
            None: "other",
        }
        subdir = subtype_dir_map.get(subtype, "other")
        json_dir = Path(f"data/case_law/supreme_court/{subdir}")
        no_json_cache = os.getenv("CASE_LAW_NO_JSON_CACHE", "").lower() in ("1", "true", "yes")
        return json_dir / f"{year}.json", no_json_cache

    async def _load_or_scrape(
        self,
        year: int,
        subtype: str | None,
        json_file: Path,
        no_json_cache: bool,
        force_scrape: bool,
        tracking_id: str | None,
    ) -> list[CaseLawDocument]:
        """Load cached JSON or scrape fresh data. Returns list of documents."""
        documents: list[CaseLawDocument] = []

        if not no_json_cache and json_file.exists() and not force_scrape:
            documents = self._load_from_json(json_file)
            if tracking_id and documents:
                self._update_tracking_total(tracking_id, len(documents))
        else:
            logger.info("📡 Scraping fresh data from Finlex (Court: %s, Subtype: %s)...", self.court, subtype)
            async with CaseLawScraper() as scraper:
                documents = await scraper.fetch_year(self.court, year, subtype=subtype)
            if tracking_id:
                self._update_tracking_total(tracking_id, len(documents))
            if documents and not no_json_cache:
                json_file.parent.mkdir(parents=True, exist_ok=True)
                self._save_to_json(documents, json_file)

        return documents

    def _run_extraction(
        self,
        documents: list[CaseLawDocument],
        json_file: Path,
        no_json_cache: bool,
        tracking_id: str | None,
    ) -> None:
        """Run hybrid extraction (regex + LLM fallback) on KKO precedents."""
        extractor = HybridPrecedentExtractor()
        total_docs = len(documents)
        logger.info(
            "Hybrid extraction | source=%s | total=%s",
            "scrape" if no_json_cache else str(json_file),
            total_docs,
        )
        processed_with_ai = 0
        for idx, doc in enumerate(documents, 1):
            if not doc.full_text:
                logger.warning("[%s/%s] %s | SKIP (no full_text)", idx, total_docs, doc.case_id)
                continue
            logger.info("[%s/%s] %s | Extracting", idx, total_docs, doc.case_id)
            try:
                ai_data = extractor.extract_data(doc.full_text, doc.case_id)
                if ai_data:
                    self._merge_ai_data(doc, ai_data)
                    processed_with_ai += 1
            except Exception as e:
                logger.error("[%s/%s] %s | EXTRACTION FAILED: %s", idx, total_docs, doc.case_id, e)
                if tracking_id:
                    self._track_error(
                        tracking_id=tracking_id,
                        case_id=doc.case_id,
                        url=doc.url,
                        error_type="extraction_error",
                        error_msg=str(e),
                    )
        logger.info("Extraction complete %s/%s", processed_with_ai, total_docs)

    def _store_documents(
        self,
        documents: list[CaseLawDocument],
        year: int,
        subtype: str | None,
        tracking_id: str | None,
    ) -> tuple[int, list[str]]:
        """Store documents in Supabase and update tracking.

        Returns (stored_count, list_of_failed_case_ids).
        """
        total_to_store = len(documents)
        logger.info("Storing in Supabase | total=%s", total_to_store)

        stored_count = 0
        failed_ids: list[str] = []
        for i, doc in enumerate(documents, 1):
            full_text = (getattr(doc, "full_text", None) or "").strip()
            if not full_text:
                logger.warning(
                    "[%s/%s] %s | SKIP (empty full_text; re-scrape required)", i, total_to_store, doc.case_id
                )
                failed_ids.append(f"{doc.case_id} (empty full_text; re-scrape required)")
                if tracking_id:
                    self._track_error(
                        tracking_id=tracking_id,
                        case_id=doc.case_id,
                        url=doc.url,
                        error_type="empty_full_text",
                        error_msg="Document has no full_text in JSON; re-scrape this case to populate content.",
                    )
                continue
            logger.info("[%s/%s] %s | Storing", i, total_to_store, doc.case_id)
            try:
                case_uuid = self.storage.store_case(doc)
                if case_uuid:
                    stored_count += 1
                    self._track_status(
                        year=year,
                        status="in_progress",
                        total=total_to_store,
                        processed=stored_count,
                        last_case=doc.case_id,
                        tracking_id=tracking_id,
                        subtype=subtype,
                    )
                else:
                    # store_case returned None (e.g. invalid date, schema error)
                    logger.warning("[%s/%s] %s | STORE RETURNED NONE", i, total_to_store, doc.case_id)
                    failed_ids.append(f"{doc.case_id} (storage returned None)")
                    if tracking_id:
                        self._track_error(
                            tracking_id=tracking_id,
                            case_id=doc.case_id,
                            url=doc.url,
                            error_type="storage_error",
                            error_msg="store_case returned None (check storage logs for details)",
                        )
            except Exception as e:
                logger.error("[%s/%s] %s | STORAGE FAILED: %s", i, total_to_store, doc.case_id, e)
                failed_ids.append(f"{doc.case_id} (storage error: {e})")
                if tracking_id:
                    self._track_error(
                        tracking_id=tracking_id,
                        case_id=doc.case_id,
                        url=doc.url,
                        error_type="storage_error",
                        error_msg=str(e),
                    )
        return stored_count, failed_ids

    def _merge_ai_data(self, doc: CaseLawDocument, ai_data):
        """
        Map the Pydantic model results back to the CaseLawDocument
        """
        # Metadata
        if ai_data.metadata.volume:
            doc.metadata["volume"] = ai_data.metadata.volume
            doc.volume = ai_data.metadata.volume

        doc.decision_outcome = ai_data.metadata.decision_outcome
        doc.decision_date = ai_data.metadata.date_of_issue
        doc.judges = ", ".join(ai_data.metadata.judges)
        doc.ecli = ai_data.metadata.ecli
        doc.diary_number = ai_data.metadata.diary_number

        # Keywords
        doc.legal_domains = ai_data.metadata.keywords

        # Courts
        if ai_data.lower_courts.district_court:
            doc.lower_court_name = ai_data.lower_courts.district_court.name
            doc.lower_court_date = ai_data.lower_courts.district_court.date
            doc.lower_court_number = ai_data.lower_courts.district_court.number

        if ai_data.lower_courts.appeal_court:
            doc.appeal_court_name = ai_data.lower_courts.appeal_court.name
            doc.appeal_court_date = ai_data.lower_courts.appeal_court.date
            doc.appeal_court_number = ai_data.lower_courts.appeal_court.number

        # References
        doc.cited_cases = ai_data.references.cited_cases
        doc.cited_eu_cases = ai_data.references.cited_eu_cases
        doc.cited_laws = ai_data.references.cited_laws

        # Store regulations as strings for consistency in document
        # ai_data.references.cited_regulations is List[CitedRegulation]
        doc.cited_regulations = [f"{r.name} {r.article or ''}".strip() for r in ai_data.references.cited_regulations]

        # Sections (We need a way to pass these to storage)
        doc.ai_sections = [{"type": s.type, "title": s.title, "content": s.content} for s in ai_data.sections]

        # Also create references for storage

        new_refs = []
        for ref in ai_data.references.cited_cases:
            new_refs.append(Reference(ref_id=ref, ref_type="case_law"))
        for ref in ai_data.references.cited_eu_cases:
            new_refs.append(Reference(ref_id=ref, ref_type="eu_case"))
        for ref in ai_data.references.cited_laws:
            new_refs.append(Reference(ref_id=ref, ref_type="legislation"))

        # Add regulations to references table
        for reg in ai_data.references.cited_regulations:
            ref_id = f"{reg.name} {reg.article or ''}".strip()
            new_refs.append(Reference(ref_id=ref_id, ref_type="regulation"))

        doc.references = new_refs

    def _fetch_existing_content_hashes(self, year: int) -> dict[str, str]:
        """Query Supabase for case_id -> content_hash mapping for this court + year.
        Returns dict {case_id: content_hash}. Returns empty dict on error or if DB is unavailable.
        """
        if not self.sb_client:
            return {}
        try:
            response = (
                self.sb_client.table("case_law")
                .select("case_id,content_hash")
                .eq("court_type", self.court)
                .eq("case_year", year)
                .execute()
            )
            hashes = {row["case_id"]: (row.get("content_hash") or "") for row in (response.data or [])}
            logger.info("Found %s existing documents in Supabase for %s/%s", len(hashes), self.court, year)
            return hashes
        except Exception as e:
            logger.warning("Could not check existing documents in Supabase: %s", e)
            return {}

    def _load_from_json(self, path: Path) -> list[CaseLawDocument]:
        """Load documents from cached JSON"""
        logger.info("📂 Loading existing data from %s...", path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            docs = []
            for d in data:
                # Reconstruct objects (handling references specifically)
                refs = [Reference(**r) for r in d.get("references", [])] if d.get("references") else []
                # Remove ref dicts from d before unpacking to avoid double arg
                d_copy = d.copy()
                if "references" in d_copy:
                    del d_copy["references"]

                doc = CaseLawDocument(**d_copy)
                doc.references = refs
                docs.append(doc)

            logger.info("   Loaded %s cases", len(docs))
            return docs
        except Exception as e:
            logger.error("Failed to load JSON: %s", e)
            return []

    async def _scrape_fresh(self, year: int, subtype: str = None) -> list[CaseLawDocument]:
        """Scrape fresh data using Playwright"""
        logger.info("📡 Scraping fresh data from Finlex (Court: %s, Subtype: %s)...", self.court, subtype)
        async with CaseLawScraper() as scraper:
            return await scraper.fetch_year(self.court, year, subtype=subtype)

    def _save_to_json(self, documents: list[CaseLawDocument], path: Path):
        """Save documents to JSON cache"""
        try:
            output = []
            for doc in documents:
                d = doc.to_dict()
                d["references"] = [vars(r) for r in doc.references]
                output.append(d)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.info("   Saved backup to %s", path)
        except Exception as e:
            logger.error("Failed to save JSON: %s", e)

    def _init_tracking(self, year: int, subtype: str) -> str | None:
        """Initialize tracking entry and return ID"""
        if not self.sb_client:
            return None

        try:
            # Check if exists
            existing = (
                self.sb_client.table("case_law_ingestion_tracking")
                .select("id")
                .match({"court_type": self.court, "decision_type": subtype or "unknown", "year": year})
                .execute()
            )

            if existing.data:
                tracking_id = existing.data[0]["id"]
                self.sb_client.table("case_law_ingestion_tracking").update(
                    {
                        "status": "in_progress",
                        "started_at": datetime.now().isoformat(),
                        "last_updated": datetime.now().isoformat(),
                    }
                ).eq("id", tracking_id).execute()
                return tracking_id

            data = {
                "court_type": self.court,
                "decision_type": subtype or "unknown",
                "year": year,
                "status": "in_progress",
                "total_cases": 0,
                "started_at": datetime.now().isoformat(),
            }
            res = self.sb_client.table("case_law_ingestion_tracking").insert(data).execute()
            if res.data:
                return res.data[0]["id"]
        except Exception as e:
            logger.error("Failed to init tracking: %s", e)
        return None

    def _update_tracking_total(self, tracking_id: str, total: int):
        """Update total cases count"""
        if not self.sb_client or not tracking_id:
            return

        try:
            self.sb_client.table("case_law_ingestion_tracking").update(
                {"total_cases": total, "last_updated": datetime.now().isoformat()}
            ).eq("id", tracking_id).execute()
        except Exception as e:
            logger.error("Failed to update tracking total: %s", e)

    def _track_status(
        self,
        year: int,
        status: str,
        total: int = 0,
        processed: int = 0,
        failed: int = 0,
        last_case: str = None,
        tracking_id: str = None,
        subtype: str = None,
    ):
        """Update ingestion status. total = full year count; processed = in Supabase; failed = this run."""
        if not self.sb_client:
            return

        try:
            data = {
                "status": status,
                "processed_cases": processed,
                "failed_cases": failed,
                "last_updated": datetime.now().isoformat(),
            }
            if total > 0:
                data["total_cases"] = total
            if last_case:
                data["last_processed_case"] = last_case
            if status in ("completed", "partial", "failed"):
                data["completed_at"] = datetime.now().isoformat()

            if tracking_id:
                self.sb_client.table("case_law_ingestion_tracking").update(data).eq("id", tracking_id).execute()
            else:
                self.sb_client.table("case_law_ingestion_tracking").update(data).match(
                    {"court_type": self.court, "decision_type": subtype or "unknown", "year": year}
                ).execute()

        except Exception as e:
            logger.error("Failed to track status: %s", e)

    def _track_error(self, tracking_id: str, case_id: str, error_type: str, error_msg: str, url: str = None):
        """Log specific error to database"""
        if not self.sb_client or not tracking_id:
            return

        try:
            self.sb_client.table("case_law_ingestion_errors").insert(
                {
                    "tracking_id": tracking_id,
                    "case_id": case_id,
                    "url": url,
                    "error_type": error_type,
                    "error_message": str(error_msg),
                    "occurred_at": datetime.now().isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to log error to DB: %s", e)
