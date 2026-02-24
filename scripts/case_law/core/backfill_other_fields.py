"""Backfill distinctive_facts, weighted_factors, exceptions for all KKO cases."""

import asyncio
import sys
from argparse import ArgumentParser

from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger
from src.services.case_law.regex_extractor import (
    _extract_distinctive_facts_from_text,
    _extract_exceptions_from_text,
    _extract_reasoning_excerpt,
    _extract_ruling_instruction_from_text,
)

logger = setup_logger(__name__)


async def backfill_other_fields(court_code: str = "KKO", dry_run: bool = False) -> None:
    """Backfill distinctive_facts, weighted_factors, exceptions for cases."""
    sb = get_supabase_client()
    logger.info(f"🔄 Backfilling other fields for {court_code} (dry_run={dry_run})")

    stats = {
        "total": 0,
        "ruling_instruction_updated": 0,
        "distinctive_facts_updated": 0,
        "weighted_factors_updated": 0,
        "exceptions_updated": 0,
        "failed": 0,
    }

    page_size = 1000
    offset = 0
    page_num = 0

    while True:
        page_num += 1
        logger.info(f"Page {page_num}: Fetching offset {offset}...")

        try:
            response = (
                sb.table("case_law")
                .select("id, case_id, full_text")
                .eq("court_code", court_code)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            cases = response.data if response.data else []
        except Exception as e:
            logger.error(f"Failed to fetch page {page_num}: {e}")
            break

        if not cases:
            logger.info(f"Page {page_num}: No more cases")
            break

        logger.info(f"Page {page_num}: Processing {len(cases)} cases")

        for case in cases:
            case_id = case.get("case_id", "")
            case_uuid = case.get("id", "")
            full_text = case.get("full_text", "") or ""
            stats["total"] += 1

            try:
                ruling = _extract_ruling_instruction_from_text(full_text)
                df = _extract_distinctive_facts_from_text(full_text)
                wf = _extract_reasoning_excerpt(full_text)
                ex = _extract_exceptions_from_text(full_text)

                updates = {}
                if ruling:
                    updates["ruling_instruction"] = ruling
                    stats["ruling_instruction_updated"] += 1
                if df:
                    updates["distinctive_facts"] = df
                    stats["distinctive_facts_updated"] += 1
                if wf:
                    updates["weighted_factors"] = wf
                    stats["weighted_factors_updated"] += 1
                if ex:
                    updates["exceptions"] = ex
                    stats["exceptions_updated"] += 1

                if updates and not dry_run:
                    sb.table("case_law").update(updates).eq("id", case_uuid).execute()
            except Exception as e:
                logger.error(f"{case_id}: {e}")
                stats["failed"] += 1

        offset += page_size

    logger.info("=" * 70)
    logger.info(
        f"Total: {stats['total']} | RULING: {stats['ruling_instruction_updated']} | DF: {stats['distinctive_facts_updated']} | WF: {stats['weighted_factors_updated']} | EX: {stats['exceptions_updated']}"
    )
    logger.info("=" * 70)


async def main() -> None:
    parser = ArgumentParser(description="Backfill other fields")
    parser.add_argument("--court", default="KKO", help="Court code (KKO or KHO)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    await backfill_other_fields(court_code=args.court, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)
