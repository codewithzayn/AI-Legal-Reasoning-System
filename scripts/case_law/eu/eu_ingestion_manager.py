"""
EU Case Law Ingestion Manager

Orchestrates the ingestion of EU case law (CJEU, General Court, ECHR)
from EUR-Lex CELLAR and HUDOC APIs into the existing case_law pipeline.

Mirrors the pattern of scripts/case_law/core/ingestion_manager.py.
"""

import contextlib
import time

from src.config.logging_config import setup_logger
from src.services.case_law.models import CaseLawDocument
from src.services.case_law.storage import CaseLawStorage
from src.services.eu_case_law.courts import EU_COURT_CODES, build_eu_case_url
from src.services.eu_case_law.eurlex_client import EurLexClient
from src.services.eu_case_law.extractor import EUCaseExtractor
from src.services.eu_case_law.hudoc_client import HudocClient

logger = setup_logger(__name__)


class EUIngestionManager:
    """Handles end-to-end ingestion of EU case law."""

    def __init__(self):
        self.storage = CaseLawStorage()
        self.eurlex = EurLexClient()
        self.hudoc = HudocClient()
        self.extractor = EUCaseExtractor()

    async def ingest_by_year(self, court: str = "cjeu", year: int = 2024, language: str = "EN") -> list[str]:
        """Ingest EU cases for a given court and year.

        Args:
            court: 'cjeu', 'general_court', or 'echr'
            year: Year to ingest
            language: 'EN' or 'FI'

        Returns:
            List of failed case IDs.
        """
        start = time.time()
        logger.info("EU ingestion: court=%s year=%s lang=%s", court, year, language)

        if court == "echr":
            cases = await self.hudoc.search_cases(year=year, language="ENG" if language == "EN" else language)
        else:
            cases = await self.eurlex.search_cases(court=court, year=year, language=language)

        if not cases:
            logger.info("No cases found for %s/%s", court, year)
            return []

        failed = []
        for i, case_meta in enumerate(cases, 1):
            logger.info("[%s/%s] Processing %s", i, len(cases), case_meta.get("celex") or case_meta.get("item_id"))
            try:
                doc = await self._build_document(case_meta, court, language)
                if doc:
                    result = self.storage.store_case(doc)
                    if not result:
                        failed.append(doc.case_id)
            except Exception as e:
                cid = case_meta.get("celex") or case_meta.get("item_id") or "?"
                logger.error("[%s/%s] %s failed: %s", i, len(cases), cid, e)
                failed.append(cid)

        elapsed = time.time() - start
        logger.info(
            "EU ingestion done: %s/%s stored, %s failed in %.1fs",
            len(cases) - len(failed),
            len(cases),
            len(failed),
            elapsed,
        )
        return failed

    async def ingest_by_celex(self, celex_numbers: list[str], languages: list[str] | None = None) -> list[str]:
        """Ingest specific cases by CELEX number (bilingual).

        Args:
            celex_numbers: List of CELEX identifiers.
            languages: Languages to ingest (default: ['EN', 'FI']).

        Returns:
            List of failed identifiers.
        """
        languages = languages or ["EN", "FI"]
        failed = []
        for celex in celex_numbers:
            for lang in languages:
                try:
                    result = await self._ingest_single_celex(celex, lang)
                    if not result:
                        failed.append(f"{celex}_{lang}")
                except Exception as e:
                    logger.error("Failed to ingest %s (%s): %s", celex, lang, e)
                    failed.append(f"{celex}_{lang}")
        return failed

    async def _ingest_single_celex(self, celex: str, language: str) -> str | None:
        """Ingest a single CELEX number in a specific language.

        Returns case UUID on success, None on failure.
        """
        meta = await self.eurlex.fetch_case_metadata(celex)
        if not meta:
            logger.warning("No metadata for CELEX %s", celex)
            return None

        text = await self.eurlex.fetch_case_text(celex, language)
        if not text:
            logger.warning("No text for CELEX %s (%s)", celex, language)
            return None

        # Determine court type from CELEX prefix
        court_type = "cjeu"
        if celex.startswith("6") and "T" in celex[:10]:
            court_type = "general_court"

        case_number = meta.get("case_number", "")
        ecli = meta.get("ecli", "")
        # Use ECLI as case_id if available, else CELEX_LANG
        case_id = ecli if ecli else f"{celex}_{language}"

        year = 0
        date_str = meta.get("date", "")
        if date_str and len(date_str) >= 4:
            with contextlib.suppress(ValueError):
                year = int(date_str[:4])

        # Extract sections
        sections = self.extractor.extract_cjeu(text, case_id, language)

        doc = CaseLawDocument(
            case_id=case_id,
            court_type=court_type,
            court_code=EU_COURT_CODES.get(court_type, "CJEU"),
            decision_type="judgment",
            case_year=year,
            decision_date=date_str[:10] if len(date_str) >= 10 else None,
            ecli=ecli or None,
            title=meta.get("title", ""),
            full_text=text,
            url=build_eu_case_url(court_type, case_number, celex),
            primary_language="English" if language == "EN" else "Finnish" if language == "FI" else language,
            celex_number=celex,
            eu_case_number=case_number,
            referring_court=meta.get("referring_court"),
            referring_country=meta.get("referring_country"),
            advocate_general=meta.get("advocate_general"),
            formation=meta.get("formation"),
            subject_matter=[meta["subject_matter"]] if meta.get("subject_matter") else [],
            language_of_case=language,
        )
        # Attach extracted sections for the storage pipeline
        doc.ai_sections = sections

        return self.storage.store_case(doc)

    async def ingest_finland_references(self) -> list[str]:
        """Ingest all CJEU preliminary rulings referred by Finnish courts (bilingual)."""
        cases = await self.eurlex.find_finnish_preliminary_references()
        if not cases:
            logger.info("No Finnish preliminary references found")
            return []

        celex_numbers = [c["celex"] for c in cases if c.get("celex")]
        logger.info("Found %s Finnish preliminary references, ingesting bilingual...", len(celex_numbers))
        return await self.ingest_by_celex(celex_numbers)

    async def ingest_echr_finland(self) -> list[str]:
        """Ingest all ECHR cases involving Finland as respondent."""
        cases = await self.hudoc.find_finland_cases()
        if not cases:
            logger.info("No ECHR Finland cases found")
            return []

        failed = []
        for i, case_meta in enumerate(cases, 1):
            item_id = case_meta.get("item_id", "")
            logger.info("[%s/%s] ECHR %s", i, len(cases), item_id)
            try:
                doc = await self._build_echr_document(case_meta)
                if doc:
                    result = self.storage.store_case(doc)
                    if not result:
                        failed.append(doc.case_id)
            except Exception as e:
                logger.error("[%s/%s] ECHR %s failed: %s", i, len(cases), item_id, e)
                failed.append(item_id)

        logger.info("ECHR Finland: %s/%s stored, %s failed", len(cases) - len(failed), len(cases), len(failed))
        return failed

    async def _build_document(self, case_meta: dict, court: str, language: str) -> CaseLawDocument | None:
        """Build a CaseLawDocument from EUR-Lex or HUDOC metadata."""
        if court == "echr":
            return await self._build_echr_document(case_meta)
        return await self._build_eurlex_document(case_meta, court, language)

    async def _build_eurlex_document(self, meta: dict, court: str, language: str) -> CaseLawDocument | None:
        """Build CaseLawDocument from EUR-Lex search result."""
        celex = meta.get("celex", "")
        if not celex:
            return None

        text = await self.eurlex.fetch_case_text(celex, language)
        if not text:
            return None

        ecli = meta.get("ecli", "")
        case_id = ecli if ecli else f"{celex}_{language}"
        case_number = meta.get("case_number", "")
        date_str = meta.get("date", "")
        year = 0
        if date_str and len(date_str) >= 4:
            with contextlib.suppress(ValueError):
                year = int(date_str[:4])

        sections = self.extractor.extract_cjeu(text, case_id, language)

        doc = CaseLawDocument(
            case_id=case_id,
            court_type=court,
            court_code=EU_COURT_CODES.get(court, "CJEU"),
            decision_type="judgment",
            case_year=year,
            decision_date=date_str[:10] if len(date_str) >= 10 else None,
            ecli=ecli or None,
            title=meta.get("title", ""),
            full_text=text,
            url=build_eu_case_url(court, case_number, celex),
            primary_language="English" if language == "EN" else "Finnish" if language == "FI" else language,
            celex_number=celex,
            eu_case_number=case_number,
            language_of_case=language,
        )
        doc.ai_sections = sections
        return doc

    async def _build_echr_document(self, meta: dict) -> CaseLawDocument | None:
        """Build CaseLawDocument from HUDOC search result."""
        item_id = meta.get("item_id", "")
        if not item_id:
            return None

        text = await self.hudoc.fetch_case_text(item_id)
        if not text:
            return None

        ecli = meta.get("ecli", "")
        case_id = ecli if ecli else item_id
        app_no = meta.get("app_no", "")
        date_str = meta.get("date", "")
        year = 0
        if date_str and len(date_str) >= 4:
            with contextlib.suppress(ValueError):
                year = int(date_str[:4])

        sections = self.extractor.extract_echr(text, case_id)

        doc = CaseLawDocument(
            case_id=case_id,
            court_type="echr",
            court_code="ECHR",
            decision_type="judgment",
            case_year=year,
            decision_date=date_str[:10] if len(date_str) >= 10 else None,
            ecli=ecli or None,
            title=meta.get("title", ""),
            full_text=text,
            url=build_eu_case_url("echr", item_id),
            primary_language="English",
            eu_case_number=app_no,
            respondent=meta.get("respondent", ""),
            language_of_case="ENG",
        )
        doc.ai_sections = sections
        return doc
