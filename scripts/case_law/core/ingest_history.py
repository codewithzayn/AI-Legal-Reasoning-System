"""
Historical Case Law Ingestion Script
Loops through years (e.g. 1926-2026) and ingests all cases
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, ".")
os.environ.setdefault("LOG_FORMAT", "simple")  # human-readable logs

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Default subtypes per court
COURT_SUBTYPES = {
    "supreme_court": ["precedent", "ruling", "leave_to_appeal"],
    "supreme_administrative_court": ["precedent", "other", "brief"],
}


async def ingest_history(start_year: int, end_year: int, court: str, subtype: str | None = None):
    """
    Ingest case law for a range of years.
    If subtype is specified, only that subtype is processed.
    """
    subtypes = [subtype] if subtype else COURT_SUBTYPES.get(court, [None])
    subtype_label = subtype or "ALL"
    logger.info("STARTING HISTORICAL INGESTION: %s %s-%s (%s)", court.upper(), start_year, end_year, subtype_label)

    start_time = datetime.now()
    years = range(end_year, start_year - 1, -1)
    total_years = len(years)

    manager = IngestionManager(court)
    all_failed: list[str] = []

    for i, year in enumerate(years):
        logger.info("📅 PROCESSING YEAR %s (%s/%s)", year, i + 1, total_years)
        try:
            for st in subtypes:
                failed = await manager.ingest_year(year, force_scrape=False, subtype=st)
                if failed:
                    all_failed.extend(f"[{year}] {fid}" for fid in failed)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error("Failed processing year %s: %s", year, e)
            all_failed.append(f"[{year}] YEAR FAILED: {e}")
            continue

    duration = datetime.now() - start_time
    logger.info("🏁 HISTORICAL INGESTION COMPLETE")
    logger.info("⏱️  Duration: %s", duration)

    if all_failed:
        logger.error("⚠️  ALL FAILED DOCUMENTS (%s):", len(all_failed))
        for fid in all_failed:
            logger.error("  - %s", fid)
    else:
        logger.info("✅ No failures across all years.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest historical case law")
    parser.add_argument("--start", type=int, default=1926, help="Start year (default: 1926)")
    parser.add_argument("--end", type=int, default=2026, help="End year (default: 2026)")
    parser.add_argument(
        "--court",
        type=str,
        default="supreme_court",
        choices=["supreme_court", "supreme_administrative_court"],
        help="Court (supreme_court/supreme_administrative_court)",
    )
    parser.add_argument(
        "--subtype",
        type=str,
        default=None,
        choices=["precedent", "ruling", "leave_to_appeal", "other", "brief"],
        help="Process only this subtype (default: all subtypes for the court)",
    )

    args = parser.parse_args()
    asyncio.run(ingest_history(args.start, args.end, args.court, args.subtype))
