"""
Ingest Supreme Court (KKO) Leaves to Appeal (Valitusluvat)
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
    logger.info(f"Starting KKO Leaves to Appeal Ingestion for {year}")
    
    manager = IngestionManager("supreme_court")
    await manager.ingest_year(year, subtype="leave_to_appeal")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Leaves to Appeal")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    args = parser.parse_args()
    
    asyncio.run(main(args.year))
