"""
Ingest Supreme Court (KKO) Other Rulings (Muut päätökset)
"""

import asyncio
import argparse
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

async def main(year: int):
    logger.info(f"Starting KKO Rulings Ingestion for {year}")
    
    manager = IngestionManager("supreme_court")
    await manager.ingest_year(year, subtype="ruling")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Rulings")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    args = parser.parse_args()
    
    asyncio.run(main(args.year))
