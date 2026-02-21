"""
List case_ids with empty full_text for a given court/year/subtype.
Use this before/after running the scrape pipeline manually to see which docs need re-scraping.

Usage:
  # KHO precedents for one year (default court/type)
  python3 scripts/case_law/core/list_empty_full_text.py --year 1944
  python3 scripts/case_law/core/list_empty_full_text.py --year 2026

  # All years from 1944 for KHO precedents
  python3 scripts/case_law/core/list_empty_full_text.py --start 1944 --end 2026

  # KKO precedent for one year
  python3 scripts/case_law/core/list_empty_full_text.py --court supreme_court --year 1985
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")

from scripts.case_law.core.shared import get_subtype_dir_map, resolve_json_path
from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

SUPPORTED_COURTS = ["supreme_court", "supreme_administrative_court"]


def list_empty_for_year(court: str, year: int, subtype: str, project_root: Path) -> tuple[int, int, list[str]]:
    """Return (total, empty_count, list of case_ids with empty full_text)."""
    json_path = resolve_json_path(court, year, subtype, project_root=project_root)
    if not json_path.exists():
        return 0, 0, []
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0, 0, []
    if not isinstance(data, list):
        return 0, 0, []
    total = len(data)
    empty_ids = [
        (d.get("case_id") or "?") for d in data if isinstance(d, dict) and not (d.get("full_text") or "").strip()
    ]
    return total, len(empty_ids), empty_ids


def _year_line(court: str, year: int, subtype: str) -> tuple[str | None, bool]:
    """Return (line to print or None to skip, has_empty)."""
    total, empty_count, empty_ids = list_empty_for_year(court, year, subtype, PROJECT_ROOT)
    json_path = resolve_json_path(court, year, subtype, project_root=PROJECT_ROOT)
    if total == 0:
        return (f"{year}: no documents in JSON" if json_path.exists() else None, False)
    if empty_count:
        return (f"{year}: total={total}  empty full_text={empty_count}  case_ids: {', '.join(empty_ids)}", True)
    return (f"{year}: total={total}  empty full_text=0", False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List case_ids with empty full_text for given court/year (and optionally year range)."
    )
    parser.add_argument(
        "--court",
        choices=SUPPORTED_COURTS,
        default="supreme_administrative_court",
        help="Court (default: supreme_administrative_court)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year (e.g. 1944 or 2026)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type",
        default="precedent",
        help="Subtype: KHO precedent, other, brief; KKO precedent (default: precedent)",
    )
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

    logger.info("Court: %s  Subtype: %s  Years: %s-%s (n=%s)", court, subtype, years[0], years[-1], len(years))
    logger.info("-" * 72)

    any_empty = False
    for year in years:
        line, has_empty = _year_line(court, year, subtype)
        if line:
            logger.info(line)
        if has_empty:
            any_empty = True

    if any_empty:
        logger.info(
            "Re-scrape that year to fill full_text:\n"
            "  python3 scripts/case_law/core/scrape_json_pdf_drive.py"
            " --court supreme_administrative_court --year YEAR --type precedent [--json-only]"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
