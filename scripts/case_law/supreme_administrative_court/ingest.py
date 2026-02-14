"""
RUN: Supreme Administrative Court Ingestion
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager


async def main(year: int, force: bool):
    manager = IngestionManager("supreme_administrative_court")
    await manager.ingest_year(year, force_scrape=force)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Supreme Administrative Court (KHO) case law")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument("--force", action="store_true", help="Force fresh scrape")

    args = parser.parse_args()
    asyncio.run(main(args.year, args.force))
