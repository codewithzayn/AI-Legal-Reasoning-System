"""
Historical Case Law Ingestion Script
Loops through years (e.g. 1926-2026) and ingests all cases
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")  # human-readable logs

from scripts.case_law.core.ingestion_manager import IngestionManager
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Default subtypes per court
COURT_SUBTYPES = {
    "supreme_court": ["precedent", "ruling", "leave_to_appeal"],
    "supreme_administrative_court": ["precedent", "other", "brief"],
}


async def ingest_history(
    start_year: int,
    end_year: int,
    court: str,
    subtype: str | None = None,
    max_years: int | None = None,
    year_delay: float = 5.0,
):
    """
    Ingest case law for a range of years.
    If subtype is specified, only that subtype is processed.
    max_years: process at most this many years per run (for batching; avoids Supabase Disk IO exhaustion).
    year_delay: seconds to sleep between years (default 5 to reduce Disk IO pressure).
    """
    subtypes = [subtype] if subtype else COURT_SUBTYPES.get(court, [None])
    subtype_label = subtype or "ALL"
    logger.info(
        "STARTING HISTORICAL INGESTION: %s %s-%s (%s) max_years=%s year_delay=%.1fs",
        court.upper(),
        start_year,
        end_year,
        subtype_label,
        max_years or "all",
        year_delay,
    )

    start_time = datetime.now()
    years = list(range(end_year, start_year - 1, -1))
    if max_years:
        years = years[:max_years]
        logger.info("BATCH MODE: processing %s years this run (%s through %s)", len(years), years[0], years[-1])
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
            if year_delay > 0:
                await asyncio.sleep(year_delay)
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
    parser.add_argument(
        "--max-years",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N years per run (batch mode; reduces Supabase Disk IO). Example: 10",
    )
    parser.add_argument(
        "--year-delay",
        type=float,
        default=5.0,
        metavar="SECS",
        help="Seconds to sleep between years (default 5; increase if hitting Disk IO limits)",
    )

    args = parser.parse_args()
    asyncio.run(
        ingest_history(
            args.start,
            args.end,
            args.court,
            args.subtype,
            max_years=args.max_years,
            year_delay=args.year_delay,
        )
    )
