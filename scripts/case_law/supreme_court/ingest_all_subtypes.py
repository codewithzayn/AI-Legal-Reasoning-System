"""
Ingest Supreme Court (KKO) all subtypes for one year.
Runs precedent, ruling, and leave_to_appeal in sequence.
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager


async def main(year: int, force: bool):
    manager = IngestionManager("supreme_court")
    subtypes = ["precedent", "ruling", "leave_to_appeal"]
    for subtype in subtypes:
        await manager.ingest_year(year, force_scrape=force, subtype=subtype)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Supreme Court (KKO) all subtypes for one year")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument("--force", action="store_true", help="Force fresh scrape")
    args = parser.parse_args()
    asyncio.run(main(args.year, args.force))
