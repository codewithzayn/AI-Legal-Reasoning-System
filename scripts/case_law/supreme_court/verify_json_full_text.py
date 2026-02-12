"""
Verify supreme court precedent JSON files for documents with empty full_text.
Reports which case_ids need re-scraping before PDF export / Drive upload.

Run from project root: python3 scripts/case_law/supreme_court/verify_json_full_text.py
Or: make verify-json-full-text
"""

import json
import os
import sys
from pathlib import Path

# scripts/case_law/supreme_court/verify_json_full_text.py -> project root = 4 levels up
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("LOG_FORMAT", "simple")

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)
JSON_DIR = PROJECT_ROOT / "data" / "case_law" / "supreme_court" / "precedents"


def main() -> int:
    if not JSON_DIR.exists():
        logger.error("Directory not found: %s", JSON_DIR)
        return 1

    json_files = sorted(JSON_DIR.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    total_docs = 0
    total_empty = 0
    empty_by_year: dict[int, list[str]] = {}

    for jf in json_files:
        try:
            year = int(jf.stem)
        except ValueError:
            continue
        with open(jf, encoding="utf-8") as f:
            data = json.load(f)
        docs = data if isinstance(data, list) else []
        empty_ids = []
        for doc in docs:
            case_id = doc.get("case_id", "?")
            ft = doc.get("full_text")
            if ft is None or (isinstance(ft, str) and not ft.strip()):
                empty_ids.append(case_id)
        total_docs += len(docs)
        total_empty += len(empty_ids)
        if empty_ids:
            empty_by_year[year] = empty_ids

    logger.info("=" * 60)
    logger.info("Supreme Court Precedents – full_text verification")
    logger.info("=" * 60)
    logger.info("JSON files scanned: %s", len(json_files))
    logger.info("Total documents: %s", total_docs)
    logger.info("Documents with empty full_text: %s", total_empty)
    logger.info("")

    if empty_by_year:
        logger.info("Years with empty full_text (need re-scrape before Drive upload):")
        logger.info("-" * 60)
        for year in sorted(empty_by_year.keys()):
            ids = empty_by_year[year]
            logger.info("  %s: %s empty – %s%s", year, len(ids), ids[:5], "..." if len(ids) > 5 else "")
        logger.info("")
        logger.info("Case IDs with empty full_text (for ingest-precedents-case-ids):")
        logger.info("-" * 60)
        for year in sorted(empty_by_year.keys()):
            ids = empty_by_year[year]
            logger.info("  %s: %s", year, ",".join(ids))
        logger.info("")
        logger.info("Single command to re-ingest all empty (by year):")
        for year in sorted(empty_by_year.keys()):
            ids = empty_by_year[year]
            case_ids_str = ",".join(ids)
            logger.info('  make ingest-precedents-case-ids YEAR=%s CASE_IDS="%s"', year, case_ids_str)
    else:
        logger.info("All documents have full_text. Ready for PDF export and Drive upload.")
        logger.info("  make export-pdf-drive-range START=1926 END=2026")
        logger.info("")

    if total_empty > 0:
        logger.info("Next steps to fix empty full_text and upload to Drive:")
        logger.info("  1. Re-scrape the %s case(s) above (JSON only, no Supabase):", total_empty)
        for year in sorted(empty_by_year.keys()):
            ids = empty_by_year[year]
            case_ids_str = ",".join(ids)
            logger.info('     make fix-json-precedents YEAR=%s CASE_IDS="%s"', year, case_ids_str)
        logger.info("  2. Export PDFs and upload to Drive (will use updated JSON):")
        first_year = next(iter(sorted(empty_by_year.keys())))
        logger.info("     make export-pdf-drive YEAR=<year>  # e.g. YEAR=%s", first_year)
        logger.info("")

    return 0 if total_empty == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
