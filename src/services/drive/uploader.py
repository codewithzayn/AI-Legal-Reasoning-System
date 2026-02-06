# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Google Drive uploader: service account auth, create folders by name, upload file.
Used by case law PDF backup pipeline only.
"""

import os
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def credentials_file_exists(project_root: Optional[Path] = None) -> bool:
    """
    Return True if GOOGLE_APPLICATION_CREDENTIALS is set and points to an existing file.
    Resolves relative paths against project_root (default cwd). Does not mutate env.
    """
    cred_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not cred_path:
        return False
    if os.path.isabs(cred_path):
        return Path(cred_path).exists()
    root = project_root or Path.cwd()
    return (root / cred_path).resolve().exists()


def _resolve_credentials_path(project_root: Optional[Path] = None) -> Optional[Path]:
    """
    If GOOGLE_APPLICATION_CREDENTIALS is set and is a relative path,
    resolve it against project_root (default cwd) and set the env to the absolute path.
    Returns the resolved Path if file exists, else None (env may still be set for downstream to fail clearly).
    """
    cred_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not cred_path:
        return None
    if os.path.isabs(cred_path):
        return Path(cred_path) if Path(cred_path).exists() else None
    root = project_root or Path.cwd()
    resolved = (root / cred_path).resolve()
    if resolved.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(resolved)
        logger.debug("Resolved credentials path to %s", resolved)
        return resolved
    return None


class GoogleDriveUploader:
    """
    Upload files to Google Drive under a root folder. Creates folder hierarchy by name.
    Uses service account; root folder must be shared with the service account email (Editor).
    """

    def __init__(self, root_folder_id: str, project_root: Optional[Path] = None):
        if not (root_folder_id or "").strip():
            raise ValueError(
                "GOOGLE_DRIVE_ROOT_FOLDER_ID must be set and non-empty to upload to Drive."
            )
        self._root_id = (root_folder_id or "").strip()
        resolved = _resolve_credentials_path(project_root)
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not cred_path or not (Path(cred_path).exists()):
            looked = f" (looked at: {Path(cred_path).resolve()})" if cred_path else ""
            raise FileNotFoundError(
                "GOOGLE_APPLICATION_CREDENTIALS must point to an existing service account JSON file."
                " Set it in .env (e.g. filename in project root). File not found" + looked
            )
        try:
            credentials = service_account.Credentials.from_service_account_file(
                cred_path, scopes=SCOPES
            )
        except Exception as e:
            raise ValueError(
                "Invalid Google service account JSON at GOOGLE_APPLICATION_CREDENTIALS. "
                "Check that the file is valid JSON and contains type, project_id, private_key_id, private_key, client_email."
            ) from e
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._folder_cache: dict = {}  # (parent_id, name) -> folder_id

    @staticmethod
    def _escape_query_string(s: str) -> str:
        """Escape single quotes for Drive API q parameter."""
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def _get_or_create_folder(self, parent_id: str, name: str) -> str:
        """Get existing folder ID by name under parent, or create it."""
        cache_key = (parent_id, name)
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]
        safe_name = self._escape_query_string(name)
        q = f"name = '{safe_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        resp = self._service.files().list(q=q, fields="files(id,name)", spaces="drive").execute()
        files = resp.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            body = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            folder = self._service.files().create(body=body, fields="id").execute()
            folder_id = folder["id"]
            logger.info("Created Drive folder: %s (id=%s)", name, folder_id)
        self._folder_cache[cache_key] = folder_id
        return folder_id

    def upload_file(
        self,
        local_path: Path,
        type_folder_name: str,
        year: str,
        drive_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        Upload a file to Drive under root / type_folder_name / year / drive_filename.
        If drive_filename is None, use local_path.name.
        Returns the file ID if successful, else None.
        """
        if not local_path.exists():
            logger.warning("Upload skipped (file not found): %s", local_path)
            return None
        type_name = (type_folder_name or "").strip() or "unknown"
        year_str = (str(year) if year is not None else "").strip() or "unknown"
        type_id = self._get_or_create_folder(self._root_id, type_name)
        year_id = self._get_or_create_folder(type_id, year_str)
        name = drive_filename or local_path.name
        mime = "application/pdf" if local_path.suffix.lower() == ".pdf" else "application/octet-stream"
        try:
            safe_name = self._escape_query_string(name)
            existing = (
                self._service.files()
                .list(
                    q=f"name = '{safe_name}' and '{year_id}' in parents and trashed = false",
                    fields="files(id)",
                    spaces="drive",
                )
                .execute()
            )
            files = existing.get("files", [])
            media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)
            if files:
                file_id = files[0]["id"]
                self._service.files().update(fileId=file_id, media_body=media).execute()
                logger.debug("Updated Drive file: %s", name)
                return file_id
            body = {"name": name, "parents": [year_id]}
            f = self._service.files().create(body=body, media_body=media, fields="id").execute()
            logger.debug("Uploaded Drive file: %s", name)
            return f["id"]
        except Exception as e:
            logger.exception("Drive upload failed for %s: %s", local_path, e)
            return None
