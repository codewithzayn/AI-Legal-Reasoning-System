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
from scripts.case_law.run_ingest_year import run_year_ingestion
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

async def ingest_history(start_year: int, end_year: int, court: str):
    """
    Ingest case law for a range of years
    """
    print("=" * 70)
    print(f"📚 STARTING HISTORICAL INGESTION: {court.upper()} {start_year}-{end_year}")
    print("=" * 70)
    
    start_time = datetime.now()
    
    # Loop backwards from current year to older years usually better
    # But user asked for 1926-2026 loop. Let's do descending to get recent first.
    years = range(end_year, start_year - 1, -1)
    
    total_years = len(years)
    
    for i, year in enumerate(years):
        print("\n" + "-" * 70)
        print(f"📅 PROCESSING YEAR {year} ({i+1}/{total_years})")
        print("-" * 70)
        
        try:
            # Run ingestion for this year
            # We don't force scrape by default to use cache if available
            await run_year_ingestion(court, year, force_scrape=False)
            
            # Brief pause to be nice to Finlex server
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Failed processing year {year}: {e}")
            print(f"❌ ERROR in year {year}: {e}")
            continue
            
    duration = datetime.now() - start_time
    print("\n" + "=" * 70)
    print(f"🏁 HISTORICAL INGESTION COMPLETE")
    print(f"⏱️  Duration: {duration}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest historical case law")
    parser.add_argument("--start", type=int, default=1926, help="Start year (default: 1926)")
    parser.add_argument("--end", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument("--court", type=str, default="kko", choices=["kko", "kho"], help="Court (kko/kho)")
    
    args = parser.parse_args()
    
    asyncio.run(ingest_history(args.start, args.end, args.court))
