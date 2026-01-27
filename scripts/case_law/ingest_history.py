"""
Historical Case Law Ingestion Script
Loops through years (e.g. 1926-2026) and ingests all cases
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, ".")

# Import single year runner
# Import shared ingestion manager
from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

async def ingest_history(start_year: int, end_year: int, court: str):
    """
    Ingest case law for a range of years
    """
    logger.info(f"STARTING HISTORICAL INGESTION: {court.upper()} {start_year}-{end_year}")
    
    start_time = datetime.now()
    
    # Loop backwards from current year to older years usually better
    # But user asked for 1926-2026 loop. Let's do descending to get recent first.
    years = range(end_year, start_year - 1, -1)
    
    total_years = len(years)
    
    # Initialize manager once
    manager = IngestionManager(court)
    
    for i, year in enumerate(years):
        logger.info(f"📅 PROCESSING YEAR {year} ({i+1}/{total_years})")
        
        try:
            # Run ingestion for this year
            # We don't force scrape by default to use cache if available
            await manager.ingest_year(year, force_scrape=False)
            
            # Brief pause to be nice to Finlex server
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Failed processing year {year}: {e}")
            continue
            
    duration = datetime.now() - start_time
    logger.info(f"🏁 HISTORICAL INGESTION COMPLETE")
    logger.info(f"⏱️  Duration: {duration}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest historical case law")
    parser.add_argument("--start", type=int, default=1926, help="Start year (default: 1926)")
    parser.add_argument("--end", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument("--court", type=str, default="supreme_court", choices=["supreme_court", "supreme_administrative_court"], help="Court (supreme_court/supreme_administrative_court)")
    
    args = parser.parse_args()
    
    asyncio.run(ingest_history(args.start, args.end, args.court))
