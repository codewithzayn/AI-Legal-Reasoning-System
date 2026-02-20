"""
Abstract base class for cloud drive connectors.
Defines the interface for Google Drive, OneDrive, etc.
"""

from abc import ABC, abstractmethod


class BaseDriveConnector(ABC):
    """Interface for cloud drive read connectors."""

    @abstractmethod
    def get_auth_url(self, redirect_uri: str) -> str:
        """Return the OAuth authorization URL for the user to visit.

        Args:
            redirect_uri: The callback URL after auth.

        Returns:
            Authorization URL string.
        """

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange an authorization code for access/refresh tokens.

        Args:
            code: Authorization code from OAuth callback.
            redirect_uri: Must match the one used in get_auth_url.

        Returns:
            Dict with 'access_token', 'refresh_token', 'expires_at'.
        """

    @abstractmethod
    def list_files(self, access_token: str, folder_id: str | None = None) -> list[dict]:
        """List files in a folder (or root).

        Args:
            access_token: Valid OAuth access token.
            folder_id: Optional folder ID to list. None = root.

        Returns:
            List of dicts with 'id', 'name', 'mime_type', 'size'.
        """

    @abstractmethod
    def download_file(self, access_token: str, file_id: str) -> bytes:
        """Download a file's content as bytes.

        Args:
            access_token: Valid OAuth access token.
            file_id: The file ID to download.

        Returns:
            File content as bytes.
        """

    @abstractmethod
    def list_folders(self, access_token: str, parent_id: str | None = None) -> list[dict]:
        """List subfolders in a folder.

        Args:
            access_token: Valid OAuth access token.
            parent_id: Parent folder ID. None = root.

        Returns:
            List of dicts with 'id', 'name'.
        """
