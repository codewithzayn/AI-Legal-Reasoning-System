"""
RUN: Supreme Administrative Court Ingestion

Ingests all three KHO subtypes (precedent, other, brief) for the given year
so that nothing is missed. Use ingest_history.py for a year range.
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager

# All KHO subtypes; ingest all so precedent + other + brief are in Supabase
KHO_SUBTYPES = ["precedent", "other", "brief"]


async def main(year: int, force: bool, subtype: str | None):
    manager = IngestionManager("supreme_administrative_court")
    subtypes = [subtype] if subtype else KHO_SUBTYPES
    for st in subtypes:
        await manager.ingest_year(year, force_scrape=force, subtype=st)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Supreme Administrative Court (KHO) case law")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument("--force", action="store_true", help="Force fresh scrape")
    parser.add_argument(
        "--type",
        dest="subtype",
        choices=KHO_SUBTYPES,
        default=None,
        help="Ingest only this subtype (default: all three: precedent, other, brief)",
    )

    args = parser.parse_args()
    asyncio.run(main(args.year, args.force, args.subtype))
