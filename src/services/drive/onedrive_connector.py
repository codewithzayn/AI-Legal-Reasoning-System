"""
OneDrive connector using MSAL + Microsoft Graph API.
Reads files from OneDrive for Business or personal OneDrive.
"""

import os

import msal
import requests

from src.config.logging_config import setup_logger

from .base import BaseDriveConnector

logger = setup_logger(__name__)

_GRAPH_URL = "https://graph.microsoft.com/v1.0"
_SCOPES = ["Files.Read.All"]
_AUTHORITY = "https://login.microsoftonline.com/common"

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class OneDriveConnector(BaseDriveConnector):
    """OneDrive connector using MSAL and Microsoft Graph API."""

    def __init__(self) -> None:
        self._client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
        self._client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
        self._authority = os.getenv("MICROSOFT_AUTHORITY", _AUTHORITY).strip()
        self._app: msal.ConfidentialClientApplication | None = None

    def _get_app(self) -> msal.ConfidentialClientApplication:
        if self._app is None:
            if not self._client_id or not self._client_secret:
                raise ValueError("Microsoft OAuth client ID/secret not configured")
            self._app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=self._authority,
                client_credential=self._client_secret,
            )
        return self._app

    def get_auth_url(self, redirect_uri: str) -> str:
        app = self._get_app()
        result = app.get_authorization_request_url(
            scopes=_SCOPES,
            redirect_uri=redirect_uri,
            state="onedrive",
        )
        return result

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        app = self._get_app()
        result = app.acquire_token_by_authorization_code(
            code,
            scopes=_SCOPES,
            redirect_uri=redirect_uri,
        )
        if "error" in result:
            raise ValueError(f"Token exchange failed: {result.get('error_description', result['error'])}")
        return {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
            "expires_in": result.get("expires_in", 3600),
        }

    def list_files(self, access_token: str, folder_id: str | None = None) -> list[dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        if folder_id:
            url = f"{_GRAPH_URL}/me/drive/items/{folder_id}/children"
        else:
            url = f"{_GRAPH_URL}/me/drive/root/children"

        resp = requests.get(
            url,
            headers=headers,
            params={"$top": 100, "$select": "id,name,file,size"},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])

        files = []
        for item in items:
            if "file" not in item:
                continue  # skip folders
            name = item.get("name", "")
            ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            if ext not in _SUPPORTED_EXTENSIONS:
                continue
            files.append(
                {
                    "id": item["id"],
                    "name": name,
                    "mime_type": item.get("file", {}).get("mimeType", ""),
                    "size": item.get("size", 0),
                }
            )
        return files

    def download_file(self, access_token: str, file_id: str) -> bytes:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{_GRAPH_URL}/me/drive/items/{file_id}/content"
        resp = requests.get(url, headers=headers, timeout=120, allow_redirects=True)
        resp.raise_for_status()
        return resp.content

    def list_folders(self, access_token: str, parent_id: str | None = None) -> list[dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        if parent_id:
            url = f"{_GRAPH_URL}/me/drive/items/{parent_id}/children"
        else:
            url = f"{_GRAPH_URL}/me/drive/root/children"

        resp = requests.get(
            url,
            headers=headers,
            params={"$top": 100, "$select": "id,name,folder"},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return [{"id": item["id"], "name": item["name"]} for item in items if "folder" in item]
