"""
Google Drive service: upload files to Drive (case law PDF backup).
Uses OAuth2 user auth (recommended) or service account fallback.
"""

from .uploader import GoogleDriveUploader, credentials_file_exists

__all__ = ["GoogleDriveUploader", "credentials_file_exists"]
