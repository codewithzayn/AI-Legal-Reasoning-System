"""
Complete Case Law Ingestion Script
Scrapes cases for a specific year AND stores them directly in Supabase
"""

import asyncio
import sys
import argparse
import time
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, ".")

from src.services.case_law_scraper import CaseLawScraper, CaseLawDocument, Reference
from src.services.case_law_storage import CaseLawStorage
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

async def run_year_ingestion(court: str, year: int, force_scrape: bool = False):
    """
    Scrape and store cases for a specific year
    
    Args:
        court: "kko" or "kho"
        year: Year to ingest
        force_scrape: If True, ignores existing JSON files and scrapes fresh
    """
    start_time = time.time()
    logger.info(f"Starting Ingestion: {court.upper()} {year}")    
    # Setup paths
    json_dir = Path(f"data/case_law/{court}")
    json_dir.mkdir(parents=True, exist_ok=True)
    json_file = json_dir / f"{year}_all.json"
    
    # Setup Supabase tracking
    load_dotenv()
    
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = os.getenv("SUPABASE_KEY")
    sb_client = create_client(sb_url, sb_key)
    
    # Track START
    try:
        sb_client.table('case_law_ingestion_tracking').upsert({
            'court': court,
            'year': year,
            'status': 'in_progress',
            'started_at': 'now()',
            'last_updated': 'now()'
        }, on_conflict='court,year').execute()
    except Exception as e:
        logger.warning(f"Failed to update tracking start: {e}")
    
    documents: List[CaseLawDocument] = []
    
    # 1. SCRAPING / LOADING
    if json_file.exists() and not force_scrape:
        logger.info(f"📂 Loading existing data from {json_file}...")
        # Load from JSON
        import json
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Reconstruct objects
        for d in data:
            doc = CaseLawDocument(
                case_id=d['case_id'],
                court=d['court'],
                year=d['year'],
                case_number=d['case_number'],
                ecli=d.get('ecli'),
                date=d.get('date'),
                diary_number=d.get('diary_number'),
                keywords=d.get('keywords', []),
                references=[Reference(**r) for r in d.get('references', [])] if d.get('references') else [],
                url=d.get('url', ''),
                abstract=d.get('abstract', ''),
                lower_court=d.get('lower_court', ''),
                court_of_appeal=d.get('court_of_appeal', ''),
                appeal_to_supreme_court=d.get('appeal_to_supreme_court', ''),
                supreme_court_decision=d.get('supreme_court_decision', ''),
                reasoning=d.get('reasoning', ''),
                judgment=d.get('judgment', ''),
                judges=d.get('judges', ''),
                full_text=d.get('full_text', '')
            )
            documents.append(doc)
        logger.info(f"   Loaded {len(documents)} cases")
        
    else:
        logger.info(f"📡 Scraping fresh data from Finlex...")
        # Scrape fresh
        async with CaseLawScraper() as scraper:
            documents = await scraper.fetch_year(court, year)
            
        # Save to JSON for backup
        if documents:
            import json
            # Convert references to dicts for JSON
            output = []
            for doc in documents:
                d = doc.to_dict()
                d['references'] = [vars(r) for r in doc.references]
                output.append(d)
                
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.info(f"   Saved backup to {json_file}")
    
    if not documents:
        logger.info("❌ No documents found to store.")
        # Track FAILURE/EMPTY
        try:
            sb_client.table('case_law_ingestion_tracking').update({
                'status': 'completed', # or failed? 'completed' with 0 is fine
                'total_cases': 0,
                'processed_cases': 0,
                'completed_at': 'now()',
                'last_updated': 'now()'
            }).eq('court', court).eq('year', year).execute()
        except:
            pass
        return

    # 2. STORAGE
    logger.info("Storing in Supabase (with embeddings)...")
    storage = CaseLawStorage()
    
    # Store in batches
    stored_count = storage.store_cases(documents)
    
    # Track COMPLETION
    try:
        sb_client.table('case_law_ingestion_tracking').update({
            'status': 'completed',
            'total_cases': len(documents),
            'processed_cases': stored_count,
            'last_processed_case': documents[-1].case_id if documents else None,
            'completed_at': 'now()',
            'last_updated': 'now()'
        }).eq('court', court).eq('year', year).execute()
    except Exception as e:
        logger.warning(f"Failed to update tracking completion: {e}")
    
    elapsed_time = time.time() - start_time
    logger.info(f"✅ COMPLETED: {stored_count}/{len(documents)} cases stored")
    logger.info(f"⏱️  Year Processing Time: {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description="Ingest case law for a specific year")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest (default: 2026)")
    parser.add_argument("--court", type=str, default="kko", choices=["kko", "kho"], help="Court (kko/kho)")
    parser.add_argument("--force", action="store_true", help="Force scrape even if JSON exists")
    
    args = parser.parse_args()
    
    asyncio.run(run_year_ingestion(args.court, args.year, args.force))
