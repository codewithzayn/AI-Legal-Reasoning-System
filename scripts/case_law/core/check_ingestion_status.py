"""
Check what case law is ingested in Supabase (by year, court, type).

Run from project root: python3 scripts/case_law/core/check_ingestion_status.py [--year YYYY]
Or: make check-ingestion-status

Definitions (must match ingestion_manager.py):
  total_cases   = documents for that year (from JSON/scrape when run)
  processed_cases = documents now in Supabase (unchanged-skipped + newly stored)
  failed_cases  = documents that failed this run (e.g. empty full_text)
  remaining     = total_cases - processed_cases (= not yet in Supabase; equals failed when run finished)

Uses SUPABASE_URL and SUPABASE_KEY from .env.
"""

import argparse
import os
import sys
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
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        logger.error("Set SUPABASE_URL and SUPABASE_KEY in .env")
        sys.exit(1)

    client = create_client(url, key)

    logger.info("Case law ingestion status (Supabase)")

    # 1) Total cases and year range (from case_law)
    r = client.table("case_law").select("case_year", count="exact").execute()
    total = r.count if hasattr(r, "count") and r.count is not None else len(r.data or [])
    if not r.data:
        logger.info("No case_law rows found.")
    else:
        years = [row["case_year"] for row in (r.data or [])]
        min_y = min(years)
        max_y = max(years)
        logger.info("Total cases in case_law: %s | Year range: %s – %s", total, min_y, max_y)

    # 2) Count by year (from case_law)
    r2 = client.table("case_law").select("case_year").execute()
    by_year: dict[int, int] = {}
    for row in r2.data or []:
        y = row["case_year"]
        by_year[y] = by_year.get(y, 0) + 1

    logger.info("Cases per year (case_law):")
    for y in sorted(by_year.keys(), reverse=True):
        if args.year is not None and y != args.year:
            continue
        logger.info("  %s: %s", y, by_year[y])
    if args.year is not None and args.year not in by_year:
        logger.info("  %s: 0 (no rows in case_law)", args.year)

    # 3) By court_type
    r3 = client.table("case_law").select("court_type").execute()
    by_court: dict[str, int] = {}
    for row in r3.data or []:
        c = row["court_type"] or "?"
        by_court[c] = by_court.get(c, 0) + 1
    logger.info("Cases by court_type: %s", by_court)

    # 4) Chunks (searchable sections)
    r4 = client.table("case_law_sections").select("id", count="exact").execute()
    chunk_count = r4.count if hasattr(r4, "count") and r4.count is not None else len(r4.data or [])
    logger.info("Total chunks (case_law_sections): %s", chunk_count)

    # 5) Ingestion tracking: per-year total, processed, failed, remaining, status
    try:
        q = client.table("case_law_ingestion_tracking").select("*").order("year", desc=True)
        if args.year is not None:
            q = q.eq("year", args.year)
        r5 = q.execute()

        if r5.data:
            logger.info("")
            logger.info(
                "Ingestion tracking: total=expected for year, processed=in Supabase, failed=failed this run, remaining=total−processed"
            )
            logger.info("  [court_type | decision_type | year | status | processed | total | failed | remaining]")
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

    logger.info("")
    logger.info(
        "To run the same per-year view in Supabase SQL editor, use docs/SUPABASE_QUERIES.sql (ingestion status query)."
    )


if __name__ == "__main__":
    main()
