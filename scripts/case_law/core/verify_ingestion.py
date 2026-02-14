"""
Verify Ingestion Completeness

Finds cases with 0 sections or 0 references in Supabase.
Optionally re-ingests specific case IDs for a given year.

Usage:
    # Check all years (1926-2026):
    python3 scripts/case_law/core/verify_ingestion.py

    # Check specific year:
    python3 scripts/case_law/core/verify_ingestion.py --year 1983

    # Check a range:
    python3 scripts/case_law/core/verify_ingestion.py --start 1926 --end 2000

    # Re-ingest cases with 0 sections for a specific year:
    python3 scripts/case_law/core/verify_ingestion.py --year 1983 --fix

    # Re-ingest specific case IDs:
    python3 scripts/case_law/core/verify_ingestion.py --year 1983 --fix --case-ids KKO:1983-II-124 KKO:1983-II-125
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")

from scripts.case_law.core.ingestion_manager import IngestionManager
from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


def get_client():
    try:
        return get_supabase_client()
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)


def find_incomplete_cases(
    client,
    start_year: int = 1926,
    end_year: int = 2026,
    court_type: str = "supreme_court",
    decision_type: str = "precedent",
) -> dict[int, list[dict]]:
    """Find cases with 0 sections or 0 references, grouped by year."""

    # Paginate through case_law for the range
    page_size = 1000
    all_cases = []
    offset = 0
    while True:
        resp = (
            client.table("case_law")
            .select("id, case_id, case_year, title")
            .eq("court_type", court_type)
            .eq("decision_type", decision_type)
            .gte("case_year", start_year)
            .lte("case_year", end_year)
            .order("case_year", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_cases.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size

    if not all_cases:
        logger.info("No cases found for %s %s (%s-%s)", court_type, decision_type, start_year, end_year)
        return {}

    logger.info(
        "Found %s cases in case_law (%s-%s). Checking sections and references...", len(all_cases), start_year, end_year
    )

    # Get section counts per case_law_id
    case_ids_uuid = [c["id"] for c in all_cases]

    # Query sections count per case
    section_counts: dict[str, int] = {}
    ref_counts: dict[str, int] = {}

    # Batch query sections (paginate)
    for i in range(0, len(case_ids_uuid), 200):
        batch = case_ids_uuid[i : i + 200]
        sec_resp = client.table("case_law_sections").select("case_law_id").in_("case_law_id", batch).execute()
        for row in sec_resp.data or []:
            cid = row["case_law_id"]
            section_counts[cid] = section_counts.get(cid, 0) + 1

        ref_resp = client.table("case_law_references").select("source_case_id").in_("source_case_id", batch).execute()
        for row in ref_resp.data or []:
            cid = row["source_case_id"]
            ref_counts[cid] = ref_counts.get(cid, 0) + 1

    # Find incomplete
    incomplete: dict[int, list[dict]] = {}
    for case in all_cases:
        uuid = case["id"]
        secs = section_counts.get(uuid, 0)
        refs = ref_counts.get(uuid, 0)
        if secs == 0 or refs == 0:
            year = case["case_year"]
            if year not in incomplete:
                incomplete[year] = []
            incomplete[year].append(
                {
                    "case_id": case["case_id"],
                    "title": case.get("title", ""),
                    "sections": secs,
                    "references": refs,
                }
            )

    return incomplete


def print_report(incomplete: dict[int, list[dict]]) -> None:
    """Print a summary of incomplete cases."""
    if not incomplete:
        logger.info("All cases have sections and references. Ingestion is complete.")
        return

    total_incomplete = sum(len(cases) for cases in incomplete.values())
    total_zero_sections = sum(1 for cases in incomplete.values() for c in cases if c["sections"] == 0)
    total_zero_refs = sum(1 for cases in incomplete.values() for c in cases if c["references"] == 0)

    logger.info("=" * 70)
    logger.info("INCOMPLETE CASES REPORT")
    logger.info("=" * 70)
    logger.info("Total incomplete: %s cases", total_incomplete)
    logger.info("  With 0 sections:   %s (cannot be found by search!)", total_zero_sections)
    logger.info("  With 0 references: %s (may be normal for some cases)", total_zero_refs)
    logger.info("")

    for year in sorted(incomplete.keys(), reverse=True):
        cases = incomplete[year]
        zero_sec = [c for c in cases if c["sections"] == 0]
        zero_ref = [c for c in cases if c["references"] == 0]
        logger.info(
            "Year %s: %s incomplete (%s with 0 sections, %s with 0 refs)",
            year,
            len(cases),
            len(zero_sec),
            len(zero_ref),
        )
        for c in cases:
            marker = ""
            if c["sections"] == 0:
                marker = " *** 0 SECTIONS (CRITICAL)"
            elif c["references"] == 0:
                marker = " (0 refs)"
            logger.info("  %s | sections=%s refs=%s%s", c["case_id"], c["sections"], c["references"], marker)

    logger.info("")
    logger.info("To fix cases with 0 sections (critical), re-run:")
    years_with_zero_sec = sorted(
        [y for y, cases in incomplete.items() if any(c["sections"] == 0 for c in cases)],
        reverse=True,
    )
    for y in years_with_zero_sec:
        zero_ids = [c["case_id"] for c in incomplete[y] if c["sections"] == 0]
        logger.info("  make verify-ingestion YEAR=%s FIX=1", y)
        logger.info("  # or specific case IDs:")
        logger.info("  make reingest-cases YEAR=%s CASE_IDS='%s'", y, " ".join(zero_ids[:5]))
        if len(zero_ids) > 5:
            logger.info("  # ... and %s more", len(zero_ids) - 5)


async def fix_cases(year: int, case_ids: list[str] | None, court: str = "supreme_court", subtype: str = "precedent"):
    """Re-ingest cases with 0 sections for a specific year."""
    client = get_client()

    if case_ids:
        ids_to_fix = case_ids
    else:
        # Find all cases with 0 sections for this year
        incomplete = find_incomplete_cases(client, start_year=year, end_year=year)
        if year not in incomplete:
            logger.info("Year %s: all cases have sections. Nothing to fix.", year)
            return
        ids_to_fix = [c["case_id"] for c in incomplete[year] if c["sections"] == 0]
        if not ids_to_fix:
            logger.info("Year %s: no cases with 0 sections. Nothing to fix.", year)
            return

    logger.info("Re-ingesting %s case(s) for year %s: %s", len(ids_to_fix), year, ids_to_fix)
    manager = IngestionManager(court)
    failed = await manager.ingest_case_ids(year, subtype, ids_to_fix)
    if failed:
        logger.error("Failed to re-ingest %s case(s): %s", len(failed), failed)
    else:
        logger.info("All %s case(s) re-ingested successfully.", len(ids_to_fix))


def main():
    parser = argparse.ArgumentParser(
        description="Verify ingestion completeness: find cases with 0 sections or 0 references"
    )
    parser.add_argument("--year", type=int, default=None, help="Check a specific year")
    parser.add_argument("--start", type=int, default=1926, help="Start year (default 1926)")
    parser.add_argument("--end", type=int, default=2026, help="End year (default 2026)")
    parser.add_argument("--court", type=str, default="supreme_court", help="Court type")
    parser.add_argument("--subtype", type=str, default="precedent", help="Decision type")
    parser.add_argument("--fix", action="store_true", help="Re-ingest cases with 0 sections for --year")
    parser.add_argument(
        "--case-ids", nargs="*", default=None, help="Specific case IDs to re-ingest (use with --fix --year)"
    )

    args = parser.parse_args()

    if args.fix:
        if not args.year:
            logger.error("--fix requires --year")
            sys.exit(1)
        asyncio.run(fix_cases(args.year, args.case_ids, args.court, args.subtype))
        return

    client = get_client()
    start = args.year if args.year else args.start
    end = args.year if args.year else args.end
    incomplete = find_incomplete_cases(client, start, end, args.court, args.subtype)
    print_report(incomplete)


if __name__ == "__main__":
    main()
