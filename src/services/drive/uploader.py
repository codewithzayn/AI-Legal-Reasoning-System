# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Google Drive uploader: OAuth2 user auth (recommended) or service account auth.
Creates folder hierarchy by name, uploads files.
Used by case law PDF backup pipeline only.

Auth priority:
  1. GOOGLE_OAUTH_CLIENT_SECRET (OAuth2 installed-app flow → files owned by *you*)
  2. GOOGLE_APPLICATION_CREDENTIALS (service account → only works with Shared Drives)
"""

import hashlib
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ---------------------------------------------------------------------------
#  Path helpers
# ---------------------------------------------------------------------------


def _path_under_root(resolved: Path, root: Path) -> bool:
    """True if resolved is under root (or equal). Prevents path traversal outside project."""
    try:
        resolved = resolved.resolve()
        root = root.resolve()
        return resolved == root or root in resolved.parents
    except Exception:
        return False


def _resolve_file_path(env_var: str, project_root: Path | None = None) -> Path | None:
    """Resolve an env-var file path relative to project_root. Returns Path if exists, else None."""
    raw = (os.getenv(env_var) or "").strip()
    if not raw:
        return None
    root = (project_root or Path.cwd()).resolve()
    resolved = Path(raw).resolve() if Path(raw).is_absolute() else (root / raw).resolve()
    if not resolved.exists():
        return None
    if project_root is not None and not _path_under_root(resolved, root):
        return None
    return resolved


def credentials_file_exists(project_root: Path | None = None) -> bool:
    """Return True if any supported credentials file is set and exists."""
    return (
        _resolve_file_path("GOOGLE_OAUTH_CLIENT_SECRET", project_root) is not None
        or _resolve_file_path("GOOGLE_APPLICATION_CREDENTIALS", project_root) is not None
    )


# ---------------------------------------------------------------------------
#  OAuth2 user credentials (installed-app / desktop flow)
# ---------------------------------------------------------------------------


def _get_oauth2_user_credentials(client_secret_path: Path, project_root: Path | None = None) -> Credentials:
    """
    Get OAuth2 user credentials via installed-app flow.
    First run opens browser for authorization; token is saved for reuse.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    root = (project_root or Path.cwd()).resolve()
    token_path = root / "token.json"

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            logger.debug("Could not load saved token; will re-authorize")
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            logger.debug("Refreshed OAuth2 token")
            return creds
        except Exception:
            logger.debug("Token refresh failed; will re-authorize")

    # Fresh authorization (opens browser)
    logger.info("Opening browser for Google Drive authorization (first-time setup)...")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    logger.info("OAuth2 token saved to %s", token_path)
    return creds


# ---------------------------------------------------------------------------
#  GoogleDriveUploader
# ---------------------------------------------------------------------------


class GoogleDriveUploader:
    """
    Upload files to Google Drive under a root folder. Creates folder hierarchy by name.

    Auth methods (checked in order):
      1. OAuth2 user flow (GOOGLE_OAUTH_CLIENT_SECRET) – files owned by you, works with personal Drive.
      2. Service account (GOOGLE_APPLICATION_CREDENTIALS) – files owned by SA, needs Shared Drive.
    """

    def __init__(self, root_folder_id: str, project_root: Path | None = None):
        if not (root_folder_id or "").strip():
            raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID must be set and non-empty to upload to Drive.")
        self._root_id = (root_folder_id or "").strip()
        self._folder_cache: dict = {}  # (parent_id, name) -> folder_id
        self._auth_method = "unknown"

        # --- Try OAuth2 user credentials first ---
        oauth_path = _resolve_file_path("GOOGLE_OAUTH_CLIENT_SECRET", project_root)
        if oauth_path:
            credentials = _get_oauth2_user_credentials(oauth_path, project_root)
            self._auth_method = "oauth2_user"
            logger.info("Using OAuth2 user credentials (files owned by you)")

        else:
            # --- Fall back to service account ---
            sa_path = _resolve_file_path("GOOGLE_APPLICATION_CREDENTIALS", project_root)
            if not sa_path:
                raise FileNotFoundError(
                    "No credentials found. Set GOOGLE_OAUTH_CLIENT_SECRET (recommended for personal Drive) "
                    "or GOOGLE_APPLICATION_CREDENTIALS (for Shared Drives) in .env."
                )
            # Also set absolute path in env (for google libs that read it)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)
            logger.debug("Resolved credentials path (under project root)")
            try:
                credentials = service_account.Credentials.from_service_account_file(str(sa_path), scopes=SCOPES)
            except Exception as e:
                raise ValueError(
                    "Invalid Google service account JSON. Check the file is valid and contains "
                    "type, project_id, private_key_id, private_key, client_email."
                ) from e
            self._auth_method = "service_account"
            sa_email = getattr(credentials, "service_account_email", "") or ""
            logger.info("Using service account: %s (files will be owned by SA – use Shared Drive)", sa_email)

        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._check_root_folder()

    def _check_root_folder(self) -> None:
        """Verify the root folder exists and is accessible."""
        try:
            self._service.files().get(fileId=self._root_id, fields="id").execute()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            try:
                body = (getattr(e, "content", None) or b"").decode("utf-8", errors="replace")
                err_info = json.loads(body) if body.strip() else {}
                err_detail = err_info.get("error", {})
                details = err_detail.get("errors", [{}])
                reason = details[0].get("reason", "") if details else ""
                message = err_detail.get("message", body[:200]) if err_detail else body[:200]
                logger.error(
                    "Drive API error: status=%s reason=%s message=%s folder_id=%s",
                    status,
                    reason,
                    message,
                    self._root_id,
                )
            except Exception:
                logger.exception("Drive API error (could not parse body): status=%s", status)
            if status in (403, 404):
                raise ValueError(
                    f"Cannot access Drive folder {self._root_id!r} (HTTP {status}). "
                    "Check GOOGLE_DRIVE_ROOT_FOLDER_ID and make sure the folder is accessible."
                ) from e
            raise

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
        q = (
            f"name = '{safe_name}' and '{parent_id}' in parents "
            f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
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

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute a stable SHA-256 hex digest from source content (not from PDF bytes).
        PDF bytes change every run due to embedded timestamps; hashing the source is stable."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def upload_file(
        self,
        local_path: Path,
        type_folder_name: str,
        year: str,
        drive_filename: str | None = None,
        content_hash: str | None = None,
    ) -> str | None:
        """
        Upload a file to Drive under root / type_folder_name / year / drive_filename.
        Idempotent: if content_hash is provided, stores it in appProperties and skips
        upload when the existing Drive file already has the same hash.
        Returns the file ID if successful (or already up-to-date), else None.
        """
        if not local_path.exists():
            logger.warning("Upload skipped (file not found): %s", local_path)
            return None
        type_name = (type_folder_name or "").strip() or "unknown"
        year_str = (str(year) if year is not None else "").strip() or "unknown"
        type_id = self._get_or_create_folder(self._root_id, type_name)
        year_id = self._get_or_create_folder(type_id, year_str)
        raw_name = drive_filename or local_path.name
        name = _sanitize_drive_filename(raw_name)
        mime = "application/pdf" if local_path.suffix.lower() == ".pdf" else "application/octet-stream"
        try:
            safe_name = self._escape_query_string(name)
            existing = (
                self._service.files()
                .list(
                    q=f"name = '{safe_name}' and '{year_id}' in parents and trashed = false",
                    fields="files(id,appProperties)",
                    spaces="drive",
                )
                .execute()
            )
            files = existing.get("files", [])

            # Idempotency: compare content hash stored in appProperties
            if files and content_hash:
                file_id = files[0]["id"]
                remote_hash = (files[0].get("appProperties") or {}).get("content_hash", "")
                if remote_hash == content_hash:
                    logger.debug("Skip (unchanged): %s", name)
                    return file_id

            # Build appProperties with content_hash for future comparisons
            app_props = {"content_hash": content_hash} if content_hash else {}
            media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)

            if files:
                file_id = files[0]["id"]
                update_body = {}
                if app_props:
                    update_body["appProperties"] = app_props
                self._service.files().update(fileId=file_id, body=update_body, media_body=media).execute()
                logger.debug("Updated Drive file: %s", name)
                return file_id

            create_body = {"name": name, "parents": [year_id]}
            if app_props:
                create_body["appProperties"] = app_props
            f = self._service.files().create(body=create_body, media_body=media, fields="id").execute()
            logger.debug("Uploaded Drive file: %s", name)
            return f["id"]
        except Exception as e:
            logger.exception("Drive upload failed for %s: %s", local_path, e)
            return None


def _sanitize_drive_filename(name: str) -> str:
    """Remove path components and control chars from Drive file name (no traversal)."""
    if not (name or "").strip():
        return "unknown.pdf"
    name = (name or "").strip()
    name = name.replace("\\", "/").lstrip("/")
    if "/" in name:
        name = name.split("/")[-1]
    name = "".join(c for c in name if c.isprintable() or c in ".-_")
    return name.strip() or "unknown.pdf"
