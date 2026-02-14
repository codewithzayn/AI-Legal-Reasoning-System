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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


def _parse_case_ids(value: str) -> list[str]:
    """Parse comma-separated case IDs (e.g. KKO:2018:72,KKO:2018:73)."""
    if not (value or "").strip():
        return []
    return [cid.strip() for cid in value.split(",") if cid.strip()]


async def main(year: int, force: bool = False, case_ids: list[str] | None = None, json_only: bool = False):
    logger.info("Starting KKO Precedents Ingestion for %s", year)

    manager = IngestionManager("supreme_court")
    if case_ids:
        await manager.ingest_case_ids(year, "precedent", case_ids, json_only=json_only)
    else:
        await manager.ingest_year(year, force_scrape=force, subtype="precedent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KKO Precedents")
    parser.add_argument("--year", type=int, default=2026, help="Year to ingest")
    parser.add_argument("--force", action="store_true", help="Force re-scrape (full year)")
    parser.add_argument(
        "--case-ids",
        type=str,
        default=None,
        help="Comma-separated case IDs to ingest only (e.g. KKO:2018:72,KKO:2018:73). Skips full-year run.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Re-scrape and update JSON only (no Supabase). Use to fix empty full_text for PDF export.",
    )
    args = parser.parse_args()

    ids = _parse_case_ids(args.case_ids) if args.case_ids else None
    asyncio.run(main(args.year, args.force, case_ids=ids, json_only=args.json_only))
