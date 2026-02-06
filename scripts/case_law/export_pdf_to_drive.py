# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Standalone backup pipeline: load case law from JSON cache, convert each document to PDF,
write to local export root, and upload to Google Drive. No scraping. Run per year or range.

Usage:
  python scripts/case_law/export_pdf_to_drive.py --year 2025
  python scripts/case_law/export_pdf_to_drive.py --start 2020 --end 2026
  python scripts/case_law/export_pdf_to_drive.py --type precedent --year 2025
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Project root: when run as 'python scripts/case_law/export_pdf_to_drive.py' from repo root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from src.services.case_law.scraper import CaseLawDocument, Reference
from src.services.case_law.pdf_export import write_pdf_for_document, get_pdf_filename, doc_to_pdf
from src.config.settings import config
from src.config.logging_config import setup_logger

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


def load_documents_from_json(json_path: Path) -> list[CaseLawDocument]:
    """Load CaseLawDocument list from a year JSON file (same format as ingestion cache)."""
    if not json_path or not json_path.exists():
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", json_path, e)
        return []
    except OSError as e:
        logger.error("Cannot read %s: %s", json_path, e)
        return []
    if not isinstance(data, list):
        logger.warning("Expected list in %s, got %s", json_path, type(data).__name__)
        return []
    docs = []
    for i, d in enumerate(data):
        if not isinstance(d, dict):
            logger.warning("Skip non-dict item at index %s in %s", i, json_path)
            continue
        try:
            refs = [Reference(**r) for r in d.get("references", [])] if d.get("references") else []
            d_copy = {k: v for k, v in d.items() if k != "references"}
            doc = CaseLawDocument(**d_copy)
            doc.references = refs
            docs.append(doc)
        except (TypeError, ValueError) as e:
            logger.warning("Skip malformed document at index %s in %s: %s", i, json_path, e)
            continue
    return docs


def _write_local_enabled() -> bool:
    """True if we should write PDFs to local export root (CASE_LAW_EXPORT_LOCAL=1)."""
    raw = getattr(config, "CASE_LAW_EXPORT_LOCAL", "1") or "1"
    return str(raw).strip().lower() in ("1", "true", "yes")


def run_export(
    year: int,
    subtype: str,
    export_root: Path,
    drive_uploader=None,
    project_root: Optional[Path] = None,
) -> tuple[int, int]:
    """Export one (year, subtype). Returns (success_count, fail_count)."""
    project_root = project_root or PROJECT_ROOT
    subdir = SUBTYPE_DIR_MAP.get(subtype, "other")
    type_label = TYPE_LABEL_MAP.get(subtype, subtype)
    json_path = project_root / "data" / "case_law" / COURT / subdir / f"{year}.json"
    if not json_path.exists():
        logger.info("Skip %s %s (no JSON at %s)", type_label, year, json_path)
        return 0, 0

    documents = load_documents_from_json(json_path)
    if not documents:
        logger.info("Skip %s %s (no documents)", type_label, year)
        return 0, 0

    write_local = _write_local_enabled()
    if write_local:
        out_dir = export_root / type_label / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    fail = 0
    for i, doc in enumerate(documents, 1):
        if not doc or not (getattr(doc, "full_text", None) or "").strip():
            case_id = getattr(doc, "case_id", "?") if doc else "?"
            logger.warning("[%s/%s] %s has no full_text, skip", i, len(documents), case_id)
            fail += 1
            continue
        pdf_name = get_pdf_filename(getattr(doc, "case_id", None) or "unknown")
        try:
            pdf_bytes = doc_to_pdf(doc)
        except Exception as e:
            logger.exception("[%s/%s] %s PDF failed: %s", i, len(documents), doc.case_id, e)
            fail += 1
            continue
        local_path = None
        if write_local:
            local_path = export_root / type_label / str(year) / pdf_name
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(pdf_bytes)
            except OSError as e:
                logger.exception("[%s/%s] %s write failed: %s", i, len(documents), doc.case_id, e)
                fail += 1
                continue
        if drive_uploader:
            import tempfile
            if write_local and local_path and local_path.exists():
                upload_path = local_path
                is_temp = False
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(pdf_bytes)
                tmp.close()
                upload_path = Path(tmp.name)
                is_temp = True
            try:
                fid = drive_uploader.upload_file(
                    upload_path,
                    type_folder_name=type_label,
                    year=str(year),
                    drive_filename=pdf_name,
                )
                if not fid:
                    fail += 1
                    continue
            finally:
                if is_temp and upload_path.exists():
                    try:
                        upload_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        success += 1
        if i % 10 == 0 or i == len(documents):
            logger.info("[%s/%s] %s/%s exported", type_label, year, i, len(documents))

    return success, fail


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export case law JSON cache to PDF and upload to Google Drive (no scrape)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year to export (e.g. 2025)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type",
        choices=list(SUBTYPE_DIR_MAP),
        help="Limit to one subtype (precedent, ruling, leave_to_appeal)",
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

    subtypes = [args.type] if args.type else list(SUBTYPE_DIR_MAP)
    export_root_raw = (config.CASE_LAW_EXPORT_ROOT or "").strip()
    export_root = PROJECT_ROOT / (export_root_raw or "data/case_law_export")
    if _write_local_enabled():
        export_root.mkdir(parents=True, exist_ok=True)
    else:
        logger.info("CASE_LAW_EXPORT_LOCAL=0: PDFs will not be written to disk (Drive only).")

    drive_uploader = None
    root_folder_id = (config.GOOGLE_DRIVE_ROOT_FOLDER_ID or os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")).strip()
    if root_folder_id:
        from src.services.drive import GoogleDriveUploader, credentials_file_exists
        if not credentials_file_exists(PROJECT_ROOT):
            cred_env = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
            looked = (PROJECT_ROOT / cred_env).resolve() if cred_env and not os.path.isabs(cred_env) else (cred_env or "not set")
            logger.warning(
                "GOOGLE_DRIVE_ROOT_FOLDER_ID is set but credentials file not found at %s. "
                "PDFs will be written locally only (or skipped if CASE_LAW_EXPORT_LOCAL=0).",
                looked,
            )
        else:
            try:
                drive_uploader = GoogleDriveUploader(root_folder_id, project_root=PROJECT_ROOT)
                logger.info("Google Drive upload enabled (root=%s...)", root_folder_id[:16])
            except FileNotFoundError as e:
                logger.warning("Google Drive upload disabled: %s", e)
            except ValueError as e:
                logger.warning("Google Drive upload disabled: %s", e)
            except Exception as e:
                logger.warning("Google Drive upload disabled: %s", e)
    else:
        logger.info("GOOGLE_DRIVE_ROOT_FOLDER_ID not set; PDFs will be written locally only.")

    if not _write_local_enabled() and not drive_uploader:
        logger.error(
            "Nothing to do: CASE_LAW_EXPORT_LOCAL=0 (no local write) and Google Drive upload is not available. "
            "Set GOOGLE_DRIVE_ROOT_FOLDER_ID and GOOGLE_APPLICATION_CREDENTIALS to upload to Drive, or set CASE_LAW_EXPORT_LOCAL=1 to write PDFs locally."
        )
        return 1

    total_ok = 0
    total_fail = 0
    for subtype in subtypes:
        for year in years:
            ok, fail = run_export(year, subtype, export_root, drive_uploader=drive_uploader)
            total_ok += ok
            total_fail += fail

    logger.info("Done. Exported %s PDFs, %s failed.", total_ok, total_fail)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
