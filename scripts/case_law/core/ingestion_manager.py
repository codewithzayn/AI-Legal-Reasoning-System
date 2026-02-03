"""
Core Ingestion Manager
Contains shared logic for scraping, caching, and storing case law documents.
"""

import time
import json
import logging
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
import os
from supabase import create_client

from src.services.case_law.scraper import CaseLawScraper, CaseLawDocument, Reference
from src.services.case_law.storage import CaseLawStorage
from src.services.case_law.extractor import CaseLawExtractor
from src.config.logging_config import setup_logger

from datetime import datetime

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

    async def ingest_year(self, year: int, force_scrape: bool = False, subtype: str = None, use_ai: bool = True):
        """
        Run full ingestion for a year: Load/Scrape -> AI Extract -> Store -> Track
        """
        start_time = time.time()
        subtype_str = f" ({subtype})" if subtype else " (ALL)"
        ai_str = " + AI" if use_ai else ""
        logger.info(f"🚀 Starting Ingestion: {self.court.upper()} {year}{subtype_str}{ai_str}")
        
        # 1. Setup Data Paths
        # Map subtype to directory name (pluralize usually)
        subtype_dir_map = {
            "precedent": "precedents",
            "ruling": "rulings", 
            "leave_to_appeal": "leaves_to_appeal",
            "decision": "decisions", # Generic decisions
            None: "other"
        }
        
        subdir = subtype_dir_map.get(subtype, "other")
        json_dir = Path(f"data/case_law/{self.court}/{subdir}")
        json_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{year}.json"
        json_file = json_dir / filename
        
        # 2. Track Start
        tracking_id = self._init_tracking(year, subtype)
        
        documents = []
        
        # 3. Load or Scrape
        if json_file.exists() and not force_scrape:
            documents = self._load_from_json(json_file)
            if tracking_id and documents:
                self._update_tracking_total(tracking_id, len(documents))
        else:
            logger.info(f"📡 Scraping fresh data from Finlex (Court: {self.court}, Subtype: {subtype})...")
            
            async with CaseLawScraper() as scraper:
                documents = await scraper.fetch_year(self.court, year, subtype=subtype)
            
            if tracking_id:
                self._update_tracking_total(tracking_id, len(documents))
            
            # Save raw backup
            if documents:
                self._save_to_json(documents, json_file)
        
        if not documents:
            logger.info("❌ No documents found.")
            self._track_status(year, 'completed', total=0, processed=0, tracking_id=tracking_id, subtype=subtype)
            return

        # 3.5 AI Extraction (The "Enhanced" Step)
        if use_ai:
            extractor = CaseLawExtractor()
            logger.info("🧠 Running AI Extraction on documents...")
            
            processed_with_ai = 0
            for doc in documents:
                # Skip if already has AI sections (e.g. loaded from cached JSON that was already enriched? 
                # Currently _save_to_json saves everything, but let's assume we re-run AI if requested or if missing)
                
                # Check if document has minimal content to process
                if not doc.full_text:
                    continue
                    
                # We can skip if it looks like it was already processed, but for now let's just process.
                # Optimization: In future check doc.ai_sections or similar.
                
                try:
                    logger.info(f"   Extracting {doc.case_id}...")
                    ai_data = extractor.extract_data(doc.full_text, doc.case_id)
                    if ai_data:
                        self._merge_ai_data(doc, ai_data)
                        processed_with_ai += 1
                except Exception as e:
                    logger.error(f"   AI Extraction failed for {doc.case_id}: {e}")
                    if tracking_id:
                         self._track_error(
                            tracking_id=tracking_id,
                            case_id=doc.case_id,
                            url=doc.url,
                            error_type="extraction_error",
                            error_msg=str(e)
                         )
            
            logger.info(f"🧠 AI Extraction complete. {processed_with_ai}/{len(documents)} enriched.")

        # 4. Store in Database & Incremental Tracking
        logger.info("🗄️  Storing in Supabase (with embeddings)...")
        
        stored_count = 0
        for i, doc in enumerate(documents, 1):
            try:
                # Store single case
                case_id = self.storage.store_case(doc)
                
                if case_id:
                    stored_count += 1
                    
                    # Update tracking incrementally (every 1 docs or configured batch)
                    self._track_status(
                        year=year,
                        status='in_progress',
                        total=len(documents),
                        processed=stored_count,
                        last_case=doc.case_id,
                        tracking_id=tracking_id,
                        subtype=subtype
                    )
            except Exception as e:
                logger.error(f"Failed to store case {doc.case_id}: {e}")
                if tracking_id:
                     self._track_error(
                        tracking_id=tracking_id,
                        case_id=doc.case_id,
                        url=doc.url,
                        error_type="storage_error",
                        error_msg=str(e)
                     )
        
        # 5. Track Completion
        final_status = 'completed' if stored_count > 0 else 'failed' # Or pending if 0?
        if len(documents) == 0:
             final_status = 'completed' # Nothing to do is success
             
        self._track_status(
            year, 
            final_status, 
            total=len(documents), 
            processed=stored_count, 
            last_case=documents[-1].case_id if documents else None,
            tracking_id=tracking_id,
            subtype=subtype
        )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ COMPLETED: {stored_count}/{len(documents)} stored in {elapsed:.2f}s")

    def _merge_ai_data(self, doc: CaseLawDocument, ai_data):
        """
        Map the Pydantic model results back to the CaseLawDocument
        """
        # Metadata
        if ai_data.metadata.volume:
            doc.metadata['volume'] = ai_data.metadata.volume
            doc.volume = ai_data.metadata.volume
            
        doc.decision_outcome = ai_data.metadata.decision_outcome
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
        doc.ai_sections = [
            {
                "type": s.type,
                "title": s.title,
                "content": s.content
            }
            for s in ai_data.sections
        ]
        
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

    def _load_from_json(self, path: Path) -> List[CaseLawDocument]:
        """Load documents from cached JSON"""
        logger.info(f"📂 Loading existing data from {path}...")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            docs = []
            for d in data:
                # Reconstruct objects (handling references specifically)
                refs = [Reference(**r) for r in d.get('references', [])] if d.get('references') else []
                # Remove ref dicts from d before unpacking to avoid double arg
                d_copy = d.copy()
                if 'references' in d_copy: del d_copy['references']
                
                doc = CaseLawDocument(**d_copy)
                doc.references = refs
                docs.append(doc)
                
            logger.info(f"   Loaded {len(docs)} cases")
            return docs
        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            return []

    async def _scrape_fresh(self, year: int, subtype: str = None) -> List[CaseLawDocument]:
        """Scrape fresh data using Playwright"""
        logger.info(f"📡 Scraping fresh data from Finlex (Court: {self.court}, Subtype: {subtype})...")
        async with CaseLawScraper() as scraper:
            return await scraper.fetch_year(self.court, year, subtype=subtype)

    def _save_to_json(self, documents: List[CaseLawDocument], path: Path):
        """Save documents to JSON cache"""
        try:
            output = []
            for doc in documents:
                d = doc.to_dict()
                d['references'] = [vars(r) for r in doc.references]
                output.append(d)
                
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.info(f"   Saved backup to {path}")
        except Exception as e:
            logger.error(f"Failed to save JSON: {e}")

    def _track_status(self, year: int, status: str, total: int=0, processed: int=0, last_case: str=None, subtype: str=None):
        """Update ingestion status in DB"""
        if not self.sb_client: return
        
    def _init_tracking(self, year: int, subtype: str) -> Optional[str]:
        """Initialize tracking entry and return ID"""
        if not self.sb_client:
            return None
            
        try:
            # Check if exists
            existing = self.sb_client.table("case_law_ingestion_tracking").select("id").match({
                "court_type": self.court,
                "decision_type": subtype or "unknown",
                "year": year
            }).execute()
            
            if existing.data:
                tracking_id = existing.data[0]['id']
                self.sb_client.table("case_law_ingestion_tracking").update({
                    "status": "in_progress",
                    "started_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }).eq("id", tracking_id).execute()
                return tracking_id
            else:
                data = {
                    "court_type": self.court,
                    "decision_type": subtype or "unknown",
                    "year": year,
                    "status": "in_progress",
                    "total_cases": 0,
                    "started_at": datetime.now().isoformat()
                }
                res = self.sb_client.table("case_law_ingestion_tracking").insert(data).execute()
                if res.data:
                    return res.data[0]['id']
        except Exception as e:
            logger.error(f"Failed to init tracking: {e}")
        return None

    def _update_tracking_total(self, tracking_id: str, total: int):
        """Update total cases count"""
        if not self.sb_client or not tracking_id:
            return
        
        try:
            self.sb_client.table("case_law_ingestion_tracking").update({
                "total_cases": total,
                "last_updated": datetime.now().isoformat()
            }).eq("id", tracking_id).execute()
        except Exception as e:
            logger.error(f"Failed to update tracking total: {e}")

    def _track_status(self, year: int, status: str, total: int = 0, processed: int = 0, last_case: str = None, tracking_id: str = None, subtype: str = None):
        """Update ingestion status"""
        if not self.sb_client:
            return

        try:
            data = {
                "status": status,
                "processed_cases": processed,
                "last_updated": datetime.now().isoformat()
            }
            if total > 0:
                data["total_cases"] = total
            if last_case:
                data["last_processed_case"] = last_case
            if status == 'completed':
                data["completed_at"] = datetime.now().isoformat()
                
            if tracking_id:
                self.sb_client.table("case_law_ingestion_tracking").update(data).eq("id", tracking_id).execute()
            else:
                # Fallback if no ID passed (legacy calls)
                self.sb_client.table("case_law_ingestion_tracking").update(data).match({
                    "court_type": self.court, 
                    "decision_type": subtype or "unknown",
                    "year": year
                }).execute()
                
        except Exception as e:
            logger.error(f"Failed to track status: {e}")

    def _track_error(self, tracking_id: str, case_id: str, error_type: str, error_msg: str, url: str = None):
        """Log specific error to database"""
        if not self.sb_client or not tracking_id:
            return
            
        try:
            self.sb_client.table("case_law_ingestion_errors").insert({
                "tracking_id": tracking_id,
                "case_id": case_id,
                "url": url,
                "error_type": error_type,
                "error_message": str(error_msg),
                "occurred_at": datetime.now().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log error to DB: {e}")
