# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Standalone backup pipeline: load case law from JSON cache, convert each document to PDF,
write to local export root, and upload to Google Drive. No scraping. Run per year or range.

Supports both courts via --court flag (default: supreme_court for backward compatibility).

Usage – KKO (Supreme Court):
  python scripts/case_law/core/export_pdf_to_drive.py --year 2025
  python scripts/case_law/core/export_pdf_to_drive.py --start 2020 --end 2026
  python scripts/case_law/core/export_pdf_to_drive.py --type precedent --year 2025

Usage – KHO (Supreme Administrative Court):
  python scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --year 2025
  python scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --start 2020 --end 2026
  python scripts/case_law/core/export_pdf_to_drive.py --court supreme_administrative_court --type precedent --year 2025
"""

import argparse
import os
import sys
import warnings
from pathlib import Path

# Suppress Google lib Python 3.10 EOL warning (no impact on Drive upload)
warnings.filterwarnings("ignore", category=FutureWarning, message=".*Python version.*3\\.10.*")

# Project root: scripts/case_law/core/export_pdf_to_drive.py → 3 levels up to repo root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("LOG_FORMAT", "simple")  # human-readable logs like ingest pipeline

from scripts.case_law.core.shared import (
    COURT,  # legacy default = "supreme_court"
    get_subtype_dir_map,
    get_type_label_map,
    init_drive_uploader,
    load_documents_from_json,
    resolve_json_path,
    upload_to_drive,
    write_local_enabled,
)
from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.case_law.pdf_export import doc_to_pdf, get_pdf_filename
from src.services.drive.uploader import GoogleDriveUploader

logger = setup_logger(__name__)

# All supported courts
SUPPORTED_COURTS = ["supreme_court", "supreme_administrative_court"]


def run_export(  # noqa: PLR0915
    year: int,
    subtype: str,
    export_root: Path,
    court: str = COURT,
    drive_uploader=None,
    project_root: Path | None = None,
) -> tuple[int, int, int, list[str]]:
    """Export one (court, year, subtype) from existing JSON → PDF → Drive.

    Returns (success_count, fail_count, skipped_count, failed_case_ids).
    """
    project_root = project_root or PROJECT_ROOT
    type_label_map = get_type_label_map(court)
    type_label = type_label_map.get(subtype, subtype)
    json_path = resolve_json_path(court, year, subtype, project_root=project_root)

    if not json_path.exists():
        logger.debug("Skip %s %s (no JSON at %s)", type_label, year, json_path)
        return 0, 0, 0, []

    documents = load_documents_from_json(json_path)
    if not documents:
        logger.debug("Skip %s %s (no documents)", type_label, year)
        return 0, 0, 0, []

    _write_local = write_local_enabled()
    if _write_local:
        out_dir = export_root / type_label / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    fail = 0
    skipped = 0
    failed_ids: list[str] = []
    for i, doc in enumerate(documents, 1):
        full_text_val = (getattr(doc, "full_text", None) or "").strip()
        if not doc or not full_text_val:
            case_id = getattr(doc, "case_id", "?") if doc else "?"
            logger.warning(
                "[%s/%s] %s SKIP — no full_text; document not exported and not uploaded to Drive (safe skip)",
                i,
                len(documents),
                case_id,
            )
            skipped += 1
            continue
        pdf_name = get_pdf_filename(getattr(doc, "case_id", None) or "unknown")
        try:
            pdf_bytes = doc_to_pdf(doc)
        except ValueError as e:
            if "full_text is empty" in str(e) or "cannot generate PDF" in str(e):
                case_id = getattr(doc, "case_id", "?")
                logger.warning(
                    "[%s/%s] %s SKIP — %s; not uploaded to Drive",
                    i,
                    len(documents),
                    case_id,
                    e,
                )
                skipped += 1
            else:
                logger.exception("[%s/%s] %s PDF failed: %s", i, len(documents), doc.case_id, e)
                fail += 1
                failed_ids.append(f"{doc.case_id} (PDF generation error)")
            continue
        except Exception as e:
            logger.exception("[%s/%s] %s PDF failed: %s", i, len(documents), doc.case_id, e)
            fail += 1
            failed_ids.append(f"{doc.case_id} (PDF generation error)")
            continue
        local_path = None
        if _write_local:
            local_path = export_root / type_label / str(year) / pdf_name
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(pdf_bytes)
            except OSError as e:
                logger.exception("[%s/%s] %s write failed: %s", i, len(documents), doc.case_id, e)
                fail += 1
                failed_ids.append(f"{doc.case_id} (write error)")
                continue
        if drive_uploader:
            # Safety: never upload to Drive when full_text is empty
            if not (getattr(doc, "full_text", None) or "").strip():
                logger.warning(
                    "[%s/%s] %s SKIP upload — full_text empty; PDF not uploaded to Drive",
                    i,
                    len(documents),
                    doc.case_id,
                )
                skipped += 1
                continue
            # Compute stable hash from source content (not PDF bytes, which have timestamps)
            source_content = (getattr(doc, "case_id", "") or "") + (getattr(doc, "full_text", "") or "")
            content_hash = GoogleDriveUploader.compute_content_hash(source_content)
            result = upload_to_drive(
                drive_uploader, pdf_bytes, local_path, type_label, year, pdf_name, content_hash=content_hash
            )
            if not result:
                fail += 1
                failed_ids.append(f"{doc.case_id} (Drive upload error)")
                continue
        success += 1
        if i % 10 == 0 or i == len(documents):
            logger.info("[%s/%s] %s/%s exported", type_label, year, i, len(documents))

    return success, fail, skipped, failed_ids


def _parse_years(args) -> list[int]:
    """Parse year/start/end args into a list of years."""
    if args.year is not None:
        return [args.year]
    if args.end is None:
        raise SystemExit("--end required when using --start")
    if args.start > args.end:
        raise SystemExit("--start must be <= --end")
    return list(range(args.start, args.end + 1))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export case law JSON cache to PDF and upload to Google Drive (no scrape). "
            "Supports both KKO and KHO via --court flag."
        )
    )
    parser.add_argument(
        "--court",
        choices=SUPPORTED_COURTS,
        default=COURT,  # "supreme_court" — backward-compatible default
        help="Court to export (default: supreme_court)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year", type=int, help="Single year to export (e.g. 2025)")
    group.add_argument("--start", type=int, help="Start year (use with --end)")
    parser.add_argument("--end", type=int, help="End year (use with --start)")
    parser.add_argument(
        "--type",
        default=None,
        help=(
            "Limit to one subtype. KKO: precedent, ruling, leave_to_appeal. "
            "KHO: precedent, other, brief. Omit to process all subtypes for the chosen court."
        ),
    )
    args = parser.parse_args()
    court = args.court
    subtype_dir_map = get_subtype_dir_map(court)

    # Validate --type for the chosen court
    if args.type and args.type not in subtype_dir_map:
        valid = [k for k in subtype_dir_map if k is not None]
        parser.error(f"--type {args.type!r} is not valid for court {court!r}. Valid choices: {valid}")

    years = _parse_years(args)

    if args.type:
        subtypes = [args.type]
    elif court == "supreme_court":
        subtypes = ["precedent"]  # KKO backward-compat default
    else:
        subtypes = [k for k in subtype_dir_map if k is not None]

    export_root_raw = (config.CASE_LAW_EXPORT_ROOT or "").strip()
    export_root = (PROJECT_ROOT / (export_root_raw or "data/case_law_export")).resolve()
    project_root_resolved = PROJECT_ROOT.resolve()
    if not str(export_root).startswith(str(project_root_resolved)):
        logger.error(
            "CASE_LAW_EXPORT_ROOT must resolve to a path under the project root. Resolved to %s; project root is %s.",
            export_root,
            project_root_resolved,
        )
        return 1
    if write_local_enabled():
        export_root.mkdir(parents=True, exist_ok=True)
    else:
        logger.info("CASE_LAW_EXPORT_LOCAL=0: PDFs will not be written to disk (Drive only).")

    drive_uploader = init_drive_uploader(PROJECT_ROOT)

    if not write_local_enabled() and not drive_uploader:
        logger.error(
            "Nothing to do: CASE_LAW_EXPORT_LOCAL=0 and Google Drive upload is not available. "
            "Set GOOGLE_DRIVE_ROOT_FOLDER_ID + GOOGLE_OAUTH_CLIENT_SECRET, or CASE_LAW_EXPORT_LOCAL=1."
        )
        return 1

    total_ok = 0
    total_fail = 0
    total_skipped = 0
    all_failed_ids: list[str] = []
    for subtype in subtypes:
        for year in years:
            ok, fail, skipped, failed_ids = run_export(
                year,
                subtype,
                export_root,
                court=court,
                drive_uploader=drive_uploader,
                project_root=project_root_resolved,
            )
            total_ok += ok
            total_fail += fail
            total_skipped += skipped
            all_failed_ids.extend(failed_ids)

    logger.info(
        "Done. Exported %s PDFs, %s skipped (no full_text), %s failed.",
        total_ok,
        total_skipped,
        total_fail,
    )

    if all_failed_ids:
        logger.error("⚠️  FAILED DOCUMENTS (%s):", len(all_failed_ids))
        for fid in all_failed_ids:
            logger.error("  - %s", fid)

    # Exit 0 when only skips (no full_text); exit 1 only on real failures (PDF/write/upload).
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
