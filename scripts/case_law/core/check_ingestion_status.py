"""
Check what case law is ingested in Supabase (by year, court, type).

Run from project root: python3 scripts/case_law/core/check_ingestion_status.py [--year YYYY] [--sync]
Or: make check-ingestion-status   or   make sync-ingestion-status

Definitions (must match ingestion_manager.py):
  total_cases   = documents for that year (from JSON/scrape when run)
  processed_cases = documents now in Supabase (unchanged-skipped + newly stored)
  failed_cases  = documents that failed this run (e.g. empty full_text)
  remaining     = total_cases - processed_cases (= not yet in Supabase; equals failed when run finished)

--sync: Update case_law_ingestion_tracking.processed_cases from actual COUNT in case_law so tracking matches DB.
Uses SUPABASE_URL and SUPABASE_KEY from .env.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# scripts/case_law/core/check_ingestion_status.py -> project root = 4 levels up
_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

os.environ.setdefault("LOG_FORMAT", "simple")

from dotenv import load_dotenv

load_dotenv(_root / ".env")

from supabase import create_client

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


def _actual_count_in_case_law(client, court_type: str, decision_type: str, year: int) -> int | None:
    """Return COUNT(*) from case_law for (court_type, decision_type, case_year). None on error."""
    try:
        r = (
            client.table("case_law")
            .select("id", count="exact")
            .eq("court_type", court_type)
            .eq("decision_type", decision_type)
            .eq("case_year", year)
            .execute()
        )
        return r.count if hasattr(r, "count") and r.count is not None else (len(r.data or []))
    except Exception:
        return None


def main() -> None:  # noqa: C901, PLR0912, PLR0915
    parser = argparse.ArgumentParser(
        description="Check case law ingestion status in Supabase (total, processed, failed, remaining per year)."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Show only this year (tracking + case_law counts).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Compare tracking processed_cases to actual case_law count per year.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Update tracking processed_cases from actual case_law count (keeps Supabase in sync).",
    )
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        logger.error("Set SUPABASE_URL and SUPABASE_KEY in .env")
        sys.exit(1)

    client = create_client(url, key)

    if args.year is not None:
        logger.info("Ingestion status for year %s (Supabase)", args.year)
    else:
        logger.info("Ingestion status for all years (Supabase)")

    # 1) Documents in case_law per year. If --year given, only that year; else all years (paginated).
    by_year: dict[int, int] = {}
    if args.year is not None:
        r_year = client.table("case_law").select("id", count="exact").eq("case_year", args.year).execute()
        by_year[args.year] = (
            r_year.count if hasattr(r_year, "count") and r_year.count is not None else len(r_year.data or [])
        )
    else:
        offset = 0
        page_size = 1000
        while True:
            r2 = client.table("case_law").select("case_year").range(offset, offset + page_size - 1).execute()
            for row in r2.data or []:
                y = row["case_year"]
                by_year[y] = by_year.get(y, 0) + 1
            if len(r2.data or []) < page_size:
                break
            offset += page_size

    logger.info("Documents in case_law (per year):")
    for y in sorted(by_year.keys(), reverse=True):
        if args.year is not None and y != args.year:
            continue
        logger.info("  %s: %s", y, by_year[y])
    if args.year is not None and args.year not in by_year:
        logger.info("  %s: 0", args.year)

    # 2) Ingestion tracking: total, processed, failed, remaining per year
    try:
        q = client.table("case_law_ingestion_tracking").select("*").order("year", desc=True)
        if args.year is not None:
            q = q.eq("year", args.year)
        r5 = q.execute()

        if r5.data:
            if args.sync:
                for row in r5.data:
                    ct = row.get("court_type") or "?"
                    dt = row.get("decision_type") or "?"
                    yr = row.get("year")
                    row_id = row.get("id")
                    if row_id is None:
                        continue
                    actual = _actual_count_in_case_law(client, ct, dt, yr)
                    if actual is not None:
                        try:
                            client.table("case_law_ingestion_tracking").update(
                                {
                                    "processed_cases": actual,
                                    "last_updated": datetime.now().isoformat(),
                                }
                            ).eq("id", row_id).execute()
                            logger.info("Synced %s | %s | %s: processed_cases -> %s", ct, dt, yr, actual)
                        except Exception as e:
                            logger.warning("Failed to sync tracking row %s: %s", row_id, e)

            logger.info(
                "Ingestion tracking: total=expected for year, processed=in Supabase, failed=failed this run, remaining=total−processed"
            )
            logger.info("  [court_type | decision_type | year | status | processed | total | failed | remaining]")
            # Re-fetch after sync so displayed values are current
            if args.sync:
                q2 = client.table("case_law_ingestion_tracking").select("*").order("year", desc=True)
                if args.year is not None:
                    q2 = q2.eq("year", args.year)
                r5 = q2.execute()
            for row in r5.data:
                total_t = row.get("total_cases") or 0
                processed = row.get("processed_cases") or 0
                failed = row.get("failed_cases") or 0
                remaining = max(0, total_t - processed)
                ct = row.get("court_type") or "?"
                dt = row.get("decision_type") or "?"
                yr = row.get("year")
                st = row.get("status") or "?"

                line = (
                    "  %s | %s | %s | %s | processed=%s | total=%s | failed=%s | remaining=%s",
                    ct,
                    dt,
                    yr,
                    st,
                    processed,
                    total_t,
                    failed,
                    remaining,
                )
                logger.info(*line)

                if args.validate and total_t > 0:
                    actual = _actual_count_in_case_law(client, ct, dt, yr)
                    if actual is not None:
                        if actual != processed:
                            logger.warning(
                                "    VALIDATION: case_law count for (%s, %s, %s) = %s (tracking processed=%s)",
                                ct,
                                dt,
                                yr,
                                actual,
                                processed,
                            )
                        else:
                            logger.info("    VALIDATION: case_law count = %s (matches processed)", actual)
        elif args.year is not None:
            logger.info("No tracking row for year %s.", args.year)
        else:
            logger.info("(case_law_ingestion_tracking empty or not available)")
    except Exception as e:
        logger.exception("case_law_ingestion_tracking: %s", e)


if __name__ == "__main__":
    main()
