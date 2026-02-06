"""
Ingest Supreme Court (KKO) Precedents (Ennakkopäätökset)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Simple log format (case_id + message only, no time/level/name) when running ingestion
os.environ.setdefault("LOG_FORMAT", "simple")

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


async def main(year: int, force: bool = False):
    logger.info(f"Starting KKO Precedents Ingestion for {year}")

    manager = IngestionManager("supreme_court")
    await manager.ingest_year(year, force_scrape=force, subtype="precedent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Precedents")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument("--force", action="store_true", help="Force re-scrape")
    args = parser.parse_args()

    asyncio.run(main(args.year, args.force))
