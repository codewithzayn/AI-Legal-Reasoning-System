# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Single command: Scrape case law from Finlex → save JSON → generate PDF (ditto copy) → upload to Google Drive.
No extraction, no Supabase. PDF content is the same as the scraped full_text (1:1 with website).

Supports both courts via --court flag (default: supreme_court for backward compatibility).

Usage – KKO (Supreme Court):
  python scripts/case_law/core/scrape_json_pdf_drive.py --year 2025
  python scripts/case_law/core/scrape_json_pdf_drive.py --year 2025 --type precedent
  python scripts/case_law/core/scrape_json_pdf_drive.py --start 2020 --end 2023

Usage – KHO (Supreme Administrative Court):
  python scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --year 2025
  python scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --year 2025 --type precedent
  python scripts/case_law/core/scrape_json_pdf_drive.py --court supreme_administrative_court --start 2020 --end 2023
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
    COURT,  # legacy default = "supreme_court"
    get_subtype_dir_map,
    get_type_label_map,
    init_drive_uploader,
    resolve_json_path,
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

# All supported courts
SUPPORTED_COURTS = ["supreme_court", "supreme_administrative_court"]


async def _scrape_year(court: str, year: int, subtype: str) -> list[CaseLawDocument]:
    async with CaseLawScraper() as scraper:
        return await scraper.fetch_year(court, year, subtype=subtype)


def _pdf_and_upload(
    documents: list[CaseLawDocument],
    year: int,
    subtype: str,
    export_root: Path,
    drive_uploader,
    type_label_map: dict,
) -> tuple[int, int, int, list[str]]:
    """Generate PDF from scraped full_text (or placeholder if empty) and upload to Drive.

    Returns (success, fail, skipped, failed_ids).
    skipped is always 0 — documents with no full_text get placeholder PDFs uploaded.
    """
    type_label = type_label_map.get(subtype, subtype)
    _write_local = write_local_enabled()
    if _write_local:
        out_dir = export_root / type_label / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
    success = fail = 0
    skipped = 0
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape case law from Finlex → save JSON → PDF (ditto copy) → upload to Google Drive. "
            "No extraction, no Supabase. Supports both KKO and KHO via --court flag."
        )
    )
    parser.add_argument(
        "--court",
        choices=SUPPORTED_COURTS,
        default=COURT,
        help="Court to scrape (default: supreme_court)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year (e.g. 2025)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type",
        default=None,
        help=(
            "Subtype to scrape. KKO: precedent, ruling, leave_to_appeal (default: precedent). "
            "KHO: precedent, other, brief (default: all three)."
        ),
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only scrape and save JSON; do not generate PDFs or upload to Google Drive.",
    )
    return parser


def _resolve_years(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[int]:
    if args.year is not None:
        return [args.year]
    if args.end is None:
        parser.error("--end required when using --start")
    if args.start > args.end:
        parser.error("--start must be <= --end")
    return list(range(args.start, args.end + 1))


def _resolve_subtypes(args: argparse.Namespace, court: str, subtype_dir_map: dict) -> list[str]:
    if args.type:
        return [args.type]
    if court == "supreme_court":
        return ["precedent"]
    return [k for k in subtype_dir_map if k is not None]


def _setup_export_and_drive(
    json_only: bool,
) -> tuple[Path | None, object]:
    if json_only:
        return None, None
    export_root_raw = (
        getattr(config, "CASE_LAW_EXPORT_ROOT", None) or os.getenv("CASE_LAW_EXPORT_ROOT", "data/case_law_export")
    ).strip()
    export_root = (PROJECT_ROOT / export_root_raw).resolve()
    export_root.mkdir(parents=True, exist_ok=True)
    drive_uploader = init_drive_uploader(PROJECT_ROOT)
    return export_root, drive_uploader


def _run_scrape_and_export(
    court: str,
    years: list[int],
    subtypes: list[str],
    json_only: bool,
    export_root: Path | None,
    drive_uploader: object,
    type_label_map: dict,
) -> tuple[int, int, list[str]]:
    total_ok = total_fail = 0
    all_failed: list[str] = []
    for year in years:
        for subtype in subtypes:
            logger.info("📡 Scraping %s %s %s...", court, subtype, year)
            documents = asyncio.run(_scrape_year(court, year, subtype))
            if not documents:
                logger.warning("No documents for %s %s %s", court, subtype, year)
                continue
            json_path = resolve_json_path(court, year, subtype, project_root=PROJECT_ROOT)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            save_documents_to_json(documents, json_path)
            logger.info("✅ JSON saved → %s (%s documents)", json_path, len(documents))
            if json_only:
                continue
            logger.info("📄 Generating PDFs (ditto copy) and uploading to Drive...")
            ok, f, _sk, failed_ids = _pdf_and_upload(
                documents, year, subtype, export_root, drive_uploader, type_label_map
            )
            total_ok += ok
            total_fail += f
            all_failed.extend(failed_ids)
    return total_ok, total_fail, all_failed


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    court = args.court
    subtype_dir_map = get_subtype_dir_map(court)
    type_label_map = get_type_label_map(court)

    if args.type and args.type not in subtype_dir_map:
        valid = [k for k in subtype_dir_map if k is not None]
        parser.error(f"--type {args.type!r} is not valid for court {court!r}. Valid choices: {valid}")

    years = _resolve_years(parser, args)
    subtypes = _resolve_subtypes(args, court, subtype_dir_map)
    json_only = getattr(args, "json_only", False)

    export_root, drive_uploader = _setup_export_and_drive(json_only)
    if not json_only and not write_local_enabled() and not drive_uploader:
        logger.error("Nothing to do: set CASE_LAW_EXPORT_LOCAL=1 or configure Google Drive.")
        return 1

    total_ok, total_fail, all_failed = _run_scrape_and_export(
        court, years, subtypes, json_only, export_root, drive_uploader, type_label_map
    )

    if json_only:
        logger.info("Done. JSON only (no PDFs or Drive upload).")
    else:
        logger.info(
            "Done. PDFs exported: %s ok, %s failed. "
            "(Documents with no full_text were exported as placeholders and uploaded.)",
            total_ok,
            total_fail,
        )
    for fid in all_failed:
        logger.error("  - %s", fid)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
