"""
Google Drive read-only connector for client document ingestion.
Uses OAuth2 web flow suitable for Streamlit apps.
"""

import json
import os
from pathlib import Path

import requests

from src.config.logging_config import setup_logger

from .base import BaseDriveConnector

logger = setup_logger(__name__)

_SCOPES = "https://www.googleapis.com/auth/drive.readonly"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"

_SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


class GoogleDriveConnector(BaseDriveConnector):
    """Google Drive read-only connector using OAuth2 web flow."""

    def __init__(self) -> None:
        self._client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "").strip()
        if not self._client_id or not self._client_secret:
            # Try loading from GOOGLE_OAUTH_CLIENT_SECRET JSON file
            secret_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
            if secret_path and Path(secret_path).exists():
                with open(secret_path) as f:
                    data = json.load(f)
                    # Handle both "web" and "installed" app types
                    creds = data.get("web") or data.get("installed") or {}
                    self._client_id = creds.get("client_id", "")
                    self._client_secret = creds.get("client_secret", "")

    def get_auth_url(self, redirect_uri: str) -> str:
        if not self._client_id:
            raise ValueError("Google Drive OAuth client ID not configured")
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": "google_drive",
        }
        qs = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"{_AUTH_URL}?{qs}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": data.get("expires_in", 3600),
        }

    def list_files(self, access_token: str, folder_id: str | None = None) -> list[dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        query_parts = ["trashed = false"]
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")
        # Filter for supported file types
        mime_clauses = " or ".join(f"mimeType = '{m}'" for m in _SUPPORTED_MIMES)
        query_parts.append(f"({mime_clauses})")

        params = {
            "q": " and ".join(query_parts),
            "fields": "files(id,name,mimeType,size)",
            "pageSize": 100,
        }
        resp = requests.get(_FILES_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        files = resp.json().get("files", [])
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "mime_type": f.get("mimeType", ""),
                "size": int(f.get("size", 0)),
            }
            for f in files
        ]

    def download_file(self, access_token: str, file_id: str) -> bytes:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{_FILES_URL}/{file_id}?alt=media"
        resp = requests.get(url, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.content

    def list_folders(self, access_token: str, parent_id: str | None = None) -> list[dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        query_parts = [
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false",
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")

        params = {
            "q": " and ".join(query_parts),
            "fields": "files(id,name)",
            "pageSize": 100,
        }
        resp = requests.get(_FILES_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return [{"id": f["id"], "name": f["name"]} for f in resp.json().get("files", [])]
