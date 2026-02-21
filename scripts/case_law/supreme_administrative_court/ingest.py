"""
RUN: Supreme Administrative Court Ingestion

Ingests KHO subtypes (precedent, other, brief) for the given year.
Use ingest_history.py for a year range.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("LOG_FORMAT", "simple")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

KHO_SUBTYPES = ["precedent", "other", "brief"]


def _parse_case_ids(value: str) -> list[str]:
    """Parse comma-separated case IDs (e.g. KHO:2000:48,KHO:2000:49)."""
    if not (value or "").strip():
        return []
    return [cid.strip() for cid in value.split(",") if cid.strip()]


async def main(
    year: int,
    force: bool = False,
    subtype: str | None = None,
    case_ids: list[str] | None = None,
    json_only: bool = False,
):
    logger.info("Starting KHO Ingestion for %s", year)
    manager = IngestionManager("supreme_administrative_court")

    if case_ids:
        st = subtype or "precedent"
        await manager.ingest_case_ids(year, st, case_ids, json_only=json_only)
    else:
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
    parser.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help="Comma-separated case IDs to ingest only (e.g. KHO:2000:48,KHO:2000:49)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Re-scrape and update JSON only (no Supabase). Use to fix empty full_text.",
    )

    args = parser.parse_args()
    ids = _parse_case_ids(args.case_ids) if args.case_ids else None
    asyncio.run(main(args.year, args.force, args.subtype, case_ids=ids, json_only=args.json_only))
