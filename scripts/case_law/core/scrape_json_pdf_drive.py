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
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, message=".*Python version.*3\\.10.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.case_law.pdf_export import doc_to_pdf, get_pdf_filename
from src.services.case_law.scraper import CaseLawDocument, CaseLawScraper
from src.services.drive import credentials_file_exists
from src.services.drive.uploader import GoogleDriveUploader

logger = setup_logger(__name__)

COURT = "supreme_court"
SUBTYPE_DIR_MAP = {
    "precedent": "precedents",
    "ruling": "rulings",
    "leave_to_appeal": "leaves_to_appeal",
}
TYPE_LABEL_MAP = {
    "precedent": "Supreme Court Precedents",
    "ruling": "Supreme Court Rulings",
    "leave_to_appeal": "Supreme Court Leaves to Appeal",
}


def _write_local_enabled() -> bool:
    raw = getattr(config, "CASE_LAW_EXPORT_LOCAL", "1") or "1"
    return str(raw).strip().lower() in ("1", "true", "yes")


def _save_to_json(documents: list[CaseLawDocument], path: Path) -> None:
    """Save documents to JSON (same format as ingestion cache)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    output = []
    for doc in documents:
        d = doc.to_dict()
        d["references"] = [vars(r) for r in doc.references]
        output.append(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Saved JSON: %s (%s documents)", path.name, len(documents))


def _upload_to_drive(
    drive_uploader,
    pdf_bytes: bytes,
    local_path: Path | None,
    type_label: str,
    year: int,
    pdf_name: str,
    content_hash: str | None = None,
):
    import contextlib
    import tempfile

    write_local = _write_local_enabled()
    if write_local and local_path and local_path.exists():
        upload_path = local_path
        is_temp = False
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
        upload_path = Path(tmp.name)
        is_temp = True
    try:
        fid = drive_uploader.upload_file(
            upload_path, type_folder_name=type_label, year=str(year), drive_filename=pdf_name, content_hash=content_hash
        )
        return bool(fid)
    finally:
        if is_temp and upload_path.exists():
            with contextlib.suppress(OSError):
                upload_path.unlink(missing_ok=True)


def _init_drive_uploader():
    root_folder_id = (config.GOOGLE_DRIVE_ROOT_FOLDER_ID or os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")).strip()
    if not root_folder_id:
        logger.info("GOOGLE_DRIVE_ROOT_FOLDER_ID not set; PDFs written locally only.")
        return None
    if not credentials_file_exists(PROJECT_ROOT):
        logger.warning("Google Drive credentials not found. PDFs written locally only.")
        return None
    try:
        uploader = GoogleDriveUploader(root_folder_id, project_root=PROJECT_ROOT)
        logger.info("Google Drive upload enabled (root=%s...)", root_folder_id[:16])
        return uploader
    except Exception as e:
        logger.warning("Google Drive upload disabled: %s", e)
        return None


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
    """Generate PDF from scraped full_text (ditto copy of website) and upload to Drive. Returns (success, fail, skipped, failed_ids)."""
    type_label = TYPE_LABEL_MAP.get(subtype, subtype)
    write_local = _write_local_enabled()
    if write_local:
        out_dir = export_root / type_label / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
    success = fail = skipped = 0
    failed_ids: list[str] = []
    for i, doc in enumerate(documents, 1):
        full_text_val = (getattr(doc, "full_text", None) or "").strip()
        if not full_text_val:
            logger.warning(
                "[%s/%s] %s SKIP — no full_text; not exported, not uploaded",
                i,
                len(documents),
                getattr(doc, "case_id", "?"),
            )
            skipped += 1
            continue
        pdf_name = get_pdf_filename(getattr(doc, "case_id", None) or "unknown")
        try:
            pdf_bytes = doc_to_pdf(doc)
        except Exception as e:
            logger.exception("[%s/%s] %s PDF failed: %s", i, len(documents), doc.case_id, e)
            fail += 1
            failed_ids.append(f"{doc.case_id} (PDF error)")
            continue
        local_path = None
        if write_local:
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
            if not _upload_to_drive(
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
    drive_uploader = _init_drive_uploader()

    if not _write_local_enabled() and not drive_uploader:
        logger.error("Nothing to do: set CASE_LAW_EXPORT_LOCAL=1 or configure Google Drive.")
        return 1

    total_ok = total_fail = total_skipped = 0
    all_failed: list[str] = []

    for year in years:
        logger.info("Scraping %s %s %s...", COURT, subtype, year)
        documents = asyncio.run(_scrape_year(COURT, year, subtype))
        if not documents:
            logger.warning("No documents for %s %s", year, subtype)
            continue
        json_path = json_dir / f"{year}.json"
        _save_to_json(documents, json_path)
        logger.info("Generating PDFs (ditto copy of website text) and uploading to Drive...")
        ok, f, sk, failed_ids = _pdf_and_upload(documents, year, subtype, export_root, drive_uploader)
        total_ok += ok
        total_fail += f
        total_skipped += sk
        all_failed.extend(failed_ids)

    logger.info(
        "Done. PDFs exported (ditto): %s ok, %s skipped (no full_text), %s failed.", total_ok, total_skipped, total_fail
    )
    if all_failed:
        for fid in all_failed:
            logger.error("  - %s", fid)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
