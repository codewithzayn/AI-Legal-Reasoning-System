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

from src.services.case_law_scraper import CaseLawScraper, CaseLawDocument, Reference
from src.services.case_law_storage import CaseLawStorage
from src.config.logging_config import setup_logger

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

    async def ingest_year(self, year: int, force_scrape: bool = False):
        """
        Run full ingestion for a year: Load/Scrape -> Store -> Track
        """
        start_time = time.time()
        logger.info(f"🚀 Starting Ingestion: {self.court.upper()} {year}")
        
        # 1. Setup Data Paths
        json_dir = Path(f"data/case_law/{self.court}")
        json_dir.mkdir(parents=True, exist_ok=True)
        json_file = json_dir / f"{year}_all.json"
        
        # 2. Track Start
        self._track_status(year, 'in_progress')
        
        documents = []
        
        # 3. Load or Scrape
        if json_file.exists() and not force_scrape:
            documents = self._load_from_json(json_file)
        else:
            documents = await self._scrape_fresh(year)
            if documents:
                self._save_to_json(documents, json_file)
        
        if not documents:
            logger.info("❌ No documents found.")
            self._track_status(year, 'completed', total=0, processed=0)
            return

        # 4. Store in Database
        logger.info("🗄️  Storing in Supabase (with embeddings)...")
        stored_count = self.storage.store_cases(documents)
        
        # 5. Track Completion
        self._track_status(
            year, 
            'completed', 
            total=len(documents), 
            processed=stored_count, 
            last_case=documents[-1].case_id if documents else None
        )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ COMPLETED: {stored_count}/{len(documents)} stored in {elapsed:.2f}s")

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

    async def _scrape_fresh(self, year: int) -> List[CaseLawDocument]:
        """Scrape fresh data using Playwright"""
        logger.info(f"📡 Scraping fresh data from Finlex (Court: {self.court})...")
        async with CaseLawScraper() as scraper:
            return await scraper.fetch_year(self.court, year)

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

    def _track_status(self, year: int, status: str, total: int=0, processed: int=0, last_case: str=None):
        """Update ingestion status in DB"""
        if not self.sb_client: return
        
        payload = {
            'court': self.court,
            'year': year,
            'status': status,
            'last_updated': 'now()'
        }
        if status == 'in_progress':
            payload['started_at'] = 'now()'
        elif status == 'completed':
            payload['completed_at'] = 'now()'
            payload['total_cases'] = total
            payload['processed_cases'] = processed
            if last_case: payload['last_processed_case'] = last_case
            
        try:
            self.sb_client.table('case_law_ingestion_tracking').upsert(
                payload, on_conflict='court,year'
            ).execute()
        except Exception as e:
            logger.warning(f"Tracking update failed: {e}")
