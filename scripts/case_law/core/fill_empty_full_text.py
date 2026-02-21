"""
Fetch only documents that have empty full_text and update them in the existing JSON.
Does not re-scrape the whole year — only hits Finlex for the specific cases that need full_text.

Usage:
  # One year, KHO precedents (default)
  python3 scripts/case_law/core/fill_empty_full_text.py --year 1950

  # Year range
  python3 scripts/case_law/core/fill_empty_full_text.py --start 1978 --end 1999 --type precedent

  # Dry run: only print what would be fetched, do not write JSON
  python3 scripts/case_law/core/fill_empty_full_text.py --year 2026 --dry-run
"""

import argparse
import asyncio
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, message=".*Python version.*3\\.10.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.case_law.core.shared import (
    get_subtype_dir_map,
    load_documents_from_json,
    resolve_json_path,
    save_documents_to_json,
)
from src.config.logging_config import setup_logger
from src.services.case_law.scraper import CaseLawScraper

logger = setup_logger(__name__)

SUPPORTED_COURTS = ["supreme_court", "supreme_administrative_court"]


def _indices_with_empty_full_text(documents: list) -> list[int]:
    """Return indices of documents that have empty full_text and a non-empty url."""
    out: list[int] = []
    for i, doc in enumerate(documents):
        if (getattr(doc, "full_text", None) or "").strip():
            continue
        if (getattr(doc, "url", None) or "").strip():
            out.append(i)
        else:
            logger.warning("%s has no url; cannot fetch full_text", getattr(doc, "case_id", "?"))
    return out


async def _fill_empty_for_file(
    court: str,
    year: int,
    json_path: Path,
    dry_run: bool,
) -> tuple[int, int]:
    """Load JSON, fetch only docs with empty full_text, update in place, save. Returns (filled_count, failed_count)."""
    documents = load_documents_from_json(json_path)
    if not documents:
        return 0, 0

    empty_indices = _indices_with_empty_full_text(documents)
    if not empty_indices:
        logger.info("%s: no documents with empty full_text", json_path.name)
        return 0, 0

    logger.info("%s: fetching full_text for %s document(s): %s", json_path.name, len(empty_indices), empty_indices)
    filled = 0
    failed = 0

    async with CaseLawScraper() as scraper:
        for i in empty_indices:
            doc = documents[i]
            case_id = getattr(doc, "case_id", "?")
            url = getattr(doc, "url", "")
            if dry_run:
                logger.info("[dry-run] would fetch %s <- %s", case_id, url)
                filled += 1
                continue
            fetched = await scraper.fetch_case_by_url(url, court, year)
            if fetched and (getattr(fetched, "full_text", None) or "").strip():
                doc.full_text = fetched.full_text
                filled += 1
                logger.info("Filled full_text for %s", case_id)
            else:
                failed += 1
                logger.warning("Could not fetch full_text for %s (%s)", case_id, url)

    if not dry_run and filled > 0:
        save_documents_to_json(documents, json_path)
        logger.info("Saved %s (%s updated, %s failed)", json_path, filled, failed)
    return filled, failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch full_text only for documents that have empty full_text; update JSON in place."
    )
    parser.add_argument(
        "--court",
        choices=SUPPORTED_COURTS,
        default="supreme_administrative_court",
        help="Court (default: supreme_administrative_court)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year (e.g. 1950)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type",
        default="precedent",
        help="Subtype: KHO precedent, other, brief; KKO precedent (default: precedent)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only list what would be fetched; do not write JSON")
    args = parser.parse_args()

    court = args.court
    subtype_dir_map = get_subtype_dir_map(court)
    if args.type not in subtype_dir_map:
        parser.error(f"--type {args.type!r} invalid for court {court!r}. Valid: {[k for k in subtype_dir_map if k]}")
    subtype = args.type

    if args.year is not None:
        years = [args.year]
    else:
        if args.end is None:
            parser.error("--end required when using --start")
        if args.start > args.end:
            parser.error("--start must be <= --end")
        years = list(range(args.start, args.end + 1))

    total_filled = 0
    total_failed = 0
    for year in years:
        json_path = resolve_json_path(court, year, subtype, project_root=PROJECT_ROOT)
        if not json_path.exists():
            logger.debug("Skip %s (no JSON)", json_path)
            continue
        filled, failed = asyncio.run(_fill_empty_for_file(court, year, json_path, args.dry_run))
        total_filled += filled
        total_failed += failed

    if args.dry_run:
        logger.info("Dry run: would update %s document(s)", total_filled)
    else:
        logger.info("Done. Filled %s, failed %s", total_filled, total_failed)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
