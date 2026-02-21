"""
Re-scrape all cases in case_law_ingestion_errors from Finlex.

Pulls every case_id from the errors table, groups by court/year,
re-scrapes from Finlex, updates the local JSON cache + Supabase,
and clears resolved error rows.

Usage:
    python scripts/case_law/core/rescrape_errors.py
    python scripts/case_law/core/rescrape_errors.py --dry-run   # preview only
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from scripts.case_law.core.ingestion_manager import IngestionManager
from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

COURT_PREFIX_MAP = {
    "KKO": ("supreme_court", "precedent"),
    "KHO": ("supreme_administrative_court", "precedent"),
}


def _parse_court_year(case_id: str) -> tuple[str, str, int] | None:
    """Parse 'KHO:2000:48' -> (court, subtype, year) or None."""
    parts = case_id.split(":")
    if len(parts) < 3:
        return None
    prefix = parts[0].upper()
    mapping = COURT_PREFIX_MAP.get(prefix)
    if not mapping:
        logger.warning("Unknown court prefix in case_id=%s", case_id)
        return None
    try:
        year = int(parts[1])
    except ValueError:
        return None
    return mapping[0], mapping[1], year


def fetch_error_case_ids(sb_client) -> list[dict]:
    """Return all rows from case_law_ingestion_errors."""
    response = sb_client.table("case_law_ingestion_errors").select("id, case_id, error_type").order("case_id").execute()
    return response.data or []


def clear_resolved_errors(sb_client, error_row_ids: list[str]) -> int:
    """Delete resolved error rows by their primary key. Returns count deleted."""
    if not error_row_ids:
        return 0
    deleted = 0
    batch_size = 50
    for i in range(0, len(error_row_ids), batch_size):
        batch = error_row_ids[i : i + batch_size]
        try:
            sb_client.table("case_law_ingestion_errors").delete().in_("id", batch).execute()
            deleted += len(batch)
        except Exception as exc:
            logger.error("Failed to clear error rows batch %s: %s", i, exc)
    return deleted


async def rescrape_all_errors(dry_run: bool = False, json_only: bool = False) -> None:
    sb_client = get_supabase_client()
    errors = fetch_error_case_ids(sb_client)

    if not errors:
        logger.info("No ingestion errors found. Nothing to re-scrape.")
        return

    logger.info("Found %s ingestion errors to fix.", len(errors))

    groups: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    skipped = []
    for row in errors:
        parsed = _parse_court_year(row["case_id"])
        if parsed:
            court, subtype, year = parsed
            groups[(court, subtype, year)].append(row)
        else:
            skipped.append(row["case_id"])

    if skipped:
        logger.warning("Skipping %s unparseable case_ids: %s", len(skipped), skipped)

    logger.info("Grouped into %s court/year batches:", len(groups))
    for (court, subtype, year), rows in sorted(groups.items()):
        case_ids = [r["case_id"] for r in rows]
        logger.info("  %s %s %s: %s cases %s", court, subtype, year, len(case_ids), case_ids)

    if dry_run:
        logger.info("DRY RUN — no changes made.")
        return

    mode_label = "JSON-only (no Supabase)" if json_only else "JSON + Supabase"
    logger.info("Mode: %s", mode_label)

    total_fixed = 0
    total_still_empty = 0

    for (court, subtype, year), rows in sorted(groups.items()):
        case_ids = [r["case_id"] for r in rows]

        logger.info("Re-scraping %s %s %s: %s cases...", court, subtype, year, len(case_ids))

        manager = IngestionManager(court)
        failed = await manager.ingest_case_ids(
            year=year,
            subtype=subtype,
            case_ids=case_ids,
            use_ai=False,
            update_json_cache=True,
            json_only=json_only,
        )

        succeeded_ids = set(case_ids) - {f.split(" ")[0] for f in failed}
        resolved_row_ids = [r["id"] for r in rows if r["case_id"] in succeeded_ids]

        if resolved_row_ids and not json_only:
            cleared = clear_resolved_errors(sb_client, resolved_row_ids)
            logger.info("Cleared %s old error rows for %s %s.", cleared, court, year)
            total_fixed += cleared
        elif resolved_row_ids and json_only:
            total_fixed += len(resolved_row_ids)
            logger.info("JSON updated for %s cases in %s %s.", len(resolved_row_ids), court, year)

        still_failed = len(case_ids) - len(succeeded_ids)
        if still_failed:
            total_still_empty += still_failed
            logger.warning(
                "%s cases still empty after re-scrape for %s %s (Finlex may not have full text for these old cases).",
                still_failed,
                court,
                year,
            )

    logger.info(
        "DONE: %s errors resolved, %s still have empty full_text (Finlex source missing).",
        total_fixed,
        total_still_empty,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-scrape all cases with ingestion errors")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no re-scraping")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Re-scrape and update JSON files only (no Supabase). Use before running full ingestion.",
    )
    args = parser.parse_args()
    asyncio.run(rescrape_all_errors(dry_run=args.dry_run, json_only=args.json_only))
