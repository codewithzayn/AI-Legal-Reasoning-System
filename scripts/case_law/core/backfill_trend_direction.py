"""Backfill trend_direction for all KKO cases."""

import asyncio
import sys
from argparse import ArgumentParser

from scripts.case_law.core.shared import get_supabase_client
from src.config.logging_config import setup_logger
from src.services.case_law.regex_extractor import extract_trend_direction_from_case

logger = setup_logger(__name__)


async def backfill_trend(court_code: str = "KKO", dry_run: bool = False) -> None:
    """Backfill trend_direction for cases."""
    sb = get_supabase_client()
    logger.info(f"🔄 Backfilling trend_direction for {court_code} (dry_run={dry_run})")

    stats = {"total": 0, "updated": 0, "failed": 0}

    page_size = 1000
    offset = 0
    page_num = 0

    while True:
        page_num += 1
        logger.info(f"Page {page_num}: Offset {offset}...")

        try:
            response = (
                sb.table("case_law")
                .select("id, case_id, ruling_instruction, legal_domains, case_year")
                .eq("court_code", court_code)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            cases = response.data if response.data else []
        except Exception as e:
            logger.error(f"Fetch error page {page_num}: {e}")
            break

        if not cases:
            logger.info(f"Page {page_num}: Done")
            break

        logger.info(f"Page {page_num}: Processing {len(cases)} cases")

        for case in cases:
            case_id = case.get("case_id", "")
            case_uuid = case.get("id", "")
            ruling = case.get("ruling_instruction", "")
            domains = case.get("legal_domains", [])
            year = case.get("case_year", 0)
            stats["total"] += 1

            try:
                trend = extract_trend_direction_from_case(case_id, ruling, domains, year)
                if trend and not dry_run:
                    sb.table("case_law").update({"trend_direction": trend}).eq("id", case_uuid).execute()
                    stats["updated"] += 1
            except Exception as e:
                logger.error(f"{case_id}: {e}")
                stats["failed"] += 1

        offset += page_size

    logger.info("=" * 70)
    logger.info(f"Total: {stats['total']} | Updated: {stats['updated']} | Failed: {stats['failed']}")
    logger.info("=" * 70)


async def main() -> None:
    parser = ArgumentParser(description="Backfill trend_direction")
    parser.add_argument("--court", default="KKO", help="Court code (KKO or KHO)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    await backfill_trend(court_code=args.court, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)
