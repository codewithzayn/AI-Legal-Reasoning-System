# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Single command: Scrape case law from website → save JSON → generate PDF (ditto copy of website text) → upload to Google Drive.
No extraction, no Supabase. PDF content is the same as the scraped full_text (1:1 with website).

Usage:
  python scripts/case_law/core/scrape_json_pdf_drive.py --year 2025
  python scripts/case_law/core/scrape_json_pdf_drive.py --year 2025 --type precedent
  python scripts/case_law/core/scrape_json_pdf_drive.py --start 2020 --end 2023
"""

import argparse
import asyncio
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, message=".*Python version.*3\\.10.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")

from scripts.case_law.core.shared import (
    COURT,
    SUBTYPE_DIR_MAP,
    TYPE_LABEL_MAP,
    init_drive_uploader,
    save_documents_to_json,
    upload_to_drive,
    write_local_enabled,
)
from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.case_law.models import CaseLawDocument
from src.services.case_law.pdf_export import doc_to_pdf, doc_to_placeholder_pdf, get_pdf_filename
from src.services.case_law.scraper import CaseLawScraper
from src.services.drive.uploader import GoogleDriveUploader

logger = setup_logger(__name__)


async def _scrape_year(court: str, year: int, subtype: str) -> list[CaseLawDocument]:
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year(court, year, subtype=subtype)


def _pdf_and_upload(
    documents: list[CaseLawDocument],
    year: int,
    subtype: str,
    export_root: Path,
    drive_uploader,
) -> tuple[int, int, int, list[str]]:
    """Generate PDF from scraped full_text (or placeholder if empty) and upload to Drive. Returns (success, fail, skipped, failed_ids). skipped is always 0 (placeholders uploaded instead)."""
    type_label = TYPE_LABEL_MAP.get(subtype, subtype)
    _write_local = write_local_enabled()
    if _write_local:
        out_dir = export_root / type_label / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
    success = fail = 0
    skipped = 0  # No longer skip empty full_text; we export placeholder PDF and upload
    failed_ids: list[str] = []
    for i, doc in enumerate(documents, 1):
        full_text_val = (getattr(doc, "full_text", None) or "").strip()
        pdf_name = get_pdf_filename(getattr(doc, "case_id", None) or "unknown")
        try:
            if full_text_val:
                pdf_bytes = doc_to_pdf(doc)
            else:
                logger.warning(
                    "[%s/%s] %s — no full_text; exporting placeholder PDF and uploading to Drive",
                    i,
                    len(documents),
                    getattr(doc, "case_id", "?"),
                )
                pdf_bytes = doc_to_placeholder_pdf(doc)
        except Exception as e:
            logger.exception("[%s/%s] %s PDF failed: %s", i, len(documents), doc.case_id, e)
            fail += 1
            failed_ids.append(f"{doc.case_id} (PDF error)")
            continue
        local_path = None
        if _write_local:
            local_path = export_root / type_label / str(year) / pdf_name
            try:
                local_path.write_bytes(pdf_bytes)
            except OSError as e:
                logger.exception("[%s/%s] %s write failed: %s", i, len(documents), doc.case_id, e)
                fail += 1
                failed_ids.append(f"{doc.case_id} (write error)")
                continue
        if drive_uploader:
            source_content = (getattr(doc, "case_id", "") or "") + (getattr(doc, "full_text", "") or "")
            content_hash = GoogleDriveUploader.compute_content_hash(source_content)
            if not upload_to_drive(
                drive_uploader, pdf_bytes, local_path, type_label, year, pdf_name, content_hash=content_hash
            ):
                fail += 1
                failed_ids.append(f"{doc.case_id} (Drive upload error)")
                continue
        success += 1
        if i % 10 == 0 or i == len(documents):
            logger.info("[%s/%s] %s/%s PDF exported (ditto copy) + Drive", type_label, year, i, len(documents))
    return success, fail, skipped, failed_ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape case law from website → save JSON → PDF (ditto copy) → upload to Google Drive. No extraction, no Supabase."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year (e.g. 2025)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type", choices=list(SUBTYPE_DIR_MAP), default="precedent", help="Subtype (default: precedent)"
    )
    args = parser.parse_args()

    if args.year is not None:
        years = [args.year]
    else:
        if args.end is None:
            parser.error("--end required when using --start")
        if args.start > args.end:
            parser.error("--start must be <= --end")
        years = list(range(args.start, args.end + 1))

    subtype = args.type
    subdir = SUBTYPE_DIR_MAP[subtype]
    json_dir = PROJECT_ROOT / "data" / "case_law" / COURT / subdir
    export_root_raw = (
        getattr(config, "CASE_LAW_EXPORT_ROOT", None) or os.getenv("CASE_LAW_EXPORT_ROOT", "data/case_law_export")
    ).strip()
    export_root = (PROJECT_ROOT / export_root_raw).resolve()
    export_root.mkdir(parents=True, exist_ok=True)
    drive_uploader = init_drive_uploader(PROJECT_ROOT)

    if not write_local_enabled() and not drive_uploader:
        logger.error("Nothing to do: set CASE_LAW_EXPORT_LOCAL=1 or configure Google Drive.")
        return 1

    total_ok = total_fail = 0
    all_failed: list[str] = []

    for year in years:
        logger.info("Scraping %s %s %s...", COURT, subtype, year)
        documents = asyncio.run(_scrape_year(COURT, year, subtype))
        if not documents:
            logger.warning("No documents for %s %s", year, subtype)
            continue
        json_path = json_dir / f"{year}.json"
        save_documents_to_json(documents, json_path)
        logger.info("Generating PDFs (ditto copy of website text) and uploading to Drive...")
        ok, f, _sk, failed_ids = _pdf_and_upload(documents, year, subtype, export_root, drive_uploader)
        total_ok += ok
        total_fail += f
        all_failed.extend(failed_ids)

    logger.info(
        "Done. PDFs exported: %s ok, %s failed. (Documents with no full_text were exported as placeholders and uploaded.)",
        total_ok,
        total_fail,
    )
    if all_failed:
        for fid in all_failed:
            logger.error("  - %s", fid)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
