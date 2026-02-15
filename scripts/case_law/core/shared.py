# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Shared constants and helpers for case law scripts (scrape, export, ingestion).
Single source of truth – imported by scrape_json_pdf_drive.py, export_pdf_to_drive.py,
and ingestion_manager.py.
"""

import contextlib
import json
import os
import tempfile
from pathlib import Path

from src.config.logging_config import setup_logger
from src.config.settings import config
from src.services.case_law.models import CaseLawDocument, Reference
from src.services.drive import credentials_file_exists
from src.services.drive.uploader import GoogleDriveUploader

logger = setup_logger(__name__)

# ── Court constant ──────────────────────────────────────────────────
COURT = "supreme_court"

# ── Subtype → directory name mapping ────────────────────────────────
# Used by ingestion_manager, scrape_json_pdf_drive, export_pdf_to_drive.
SUBTYPE_DIR_MAP: dict[str | None, str] = {
    "precedent": "precedents",
    "ruling": "rulings",
    "leave_to_appeal": "leaves_to_appeal",
    "decision": "decisions",  # extra entry used by ingestion only
    None: "other",  # fallback for ingestion_manager
}

# ── Subtype → human-readable label (for Drive folder names) ────────
TYPE_LABEL_MAP: dict[str, str] = {
    "precedent": "Supreme Court Precedents",
    "ruling": "Supreme Court Rulings",
    "leave_to_appeal": "Supreme Court Leaves to Appeal",
}


# ── Helpers ─────────────────────────────────────────────────────────


def write_local_enabled() -> bool:
    """True if PDFs should be written to local export root (CASE_LAW_EXPORT_LOCAL=1)."""
    raw = getattr(config, "CASE_LAW_EXPORT_LOCAL", "1") or "1"
    return str(raw).strip().lower() in ("1", "true", "yes")


def upload_to_drive(
    drive_uploader: GoogleDriveUploader,
    pdf_bytes: bytes,
    local_path: Path | None,
    type_label: str,
    year: int,
    pdf_name: str,
    content_hash: str | None = None,
) -> bool:
    """Upload PDF bytes to Google Drive via a temp file (or local path if available).

    Returns True on success, False on failure.
    """
    if write_local_enabled() and local_path and local_path.exists():
        upload_path = local_path
        is_temp = False
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
        upload_path = Path(tmp.name)
        is_temp = True
    try:
        fid = drive_uploader.upload_file(
            upload_path,
            type_folder_name=type_label,
            year=str(year),
            drive_filename=pdf_name,
            content_hash=content_hash,
        )
        return bool(fid)
    finally:
        if is_temp and upload_path.exists():
            with contextlib.suppress(OSError):
                upload_path.unlink(missing_ok=True)


def init_drive_uploader(project_root: Path) -> GoogleDriveUploader | None:
    """Create a GoogleDriveUploader if credentials are available, else None."""
    root_folder_id = (config.GOOGLE_DRIVE_ROOT_FOLDER_ID or os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")).strip()
    if not root_folder_id:
        logger.info("GOOGLE_DRIVE_ROOT_FOLDER_ID not set; PDFs written locally only.")
        return None
    if not credentials_file_exists(project_root):
        logger.warning("Google Drive credentials not found. PDFs written locally only.")
        return None
    try:
        uploader = GoogleDriveUploader(root_folder_id, project_root=project_root)
        logger.info("Google Drive upload enabled (root=%s...)", root_folder_id[:16])
        return uploader
    except Exception as e:
        logger.warning("Google Drive upload disabled: %s", e)
        return None


# ── JSON serialization helpers ───────────────────────────────────────
# Single source of truth for load/save — used by ingestion_manager,
# export_pdf_to_drive, and scrape_json_pdf_drive.


def load_documents_from_json(json_path: Path) -> list[CaseLawDocument]:
    """Load CaseLawDocument list from a year JSON file (ingestion cache format)."""
    if not json_path or not json_path.exists():
        return []
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", json_path, exc)
        return []
    except OSError as exc:
        logger.error("Cannot read %s: %s", json_path, exc)
        return []
    if not isinstance(data, list):
        logger.warning("Expected list in %s, got %s", json_path, type(data).__name__)
        return []
    docs: list[CaseLawDocument] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning("Skip non-dict item at index %s in %s", i, json_path)
            continue
        try:
            refs = [Reference(**r) for r in item.get("references", [])] if item.get("references") else []
            item_copy = {k: v for k, v in item.items() if k != "references"}
            doc = CaseLawDocument(**item_copy)
            doc.references = refs
            docs.append(doc)
        except (TypeError, ValueError) as exc:
            logger.warning("Skip malformed document at index %s in %s: %s", i, json_path, exc)
            continue
    return docs


def save_documents_to_json(documents: list[CaseLawDocument], path: Path) -> None:
    """Save documents to JSON cache (ingestion cache format)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    output = []
    for doc in documents:
        d = doc.to_dict()
        d["references"] = [vars(r) for r in doc.references]
        output.append(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Saved JSON: %s (%s documents)", path.name, len(documents))


def get_supabase_client():
    """Create and return a Supabase client using env vars. Centralised for all scripts."""
    from supabase import create_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)
