"""
Persistence layer for tenant drive connections (OAuth tokens + folder config).
Uses Supabase `tenant_drive_connections` table.
"""

import os
from datetime import datetime, timezone

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)


class DriveSettingsService:
    """CRUD operations for tenant_drive_connections via Supabase."""

    _TABLE = "tenant_drive_connections"

    def __init__(self) -> None:
        from supabase import Client, create_client

        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY required")
        self._client: Client = create_client(url, key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_connection(
        self,
        tenant_id: str,
        provider: str,
        access_token: str,
        refresh_token: str = "",
        token_expiry: int = 3600,
        folder_id: str | None = None,
    ) -> dict:
        """Upsert a drive connection for a tenant + provider pair."""
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "tenant_id": tenant_id,
            "provider": provider,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": token_expiry,
            "folder_id": folder_id,
            "updated_at": now,
        }
        try:
            # Try update first
            existing = (
                self._client.table(self._TABLE)
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("provider", provider)
                .execute()
            )
            if existing.data:
                result = (
                    self._client.table(self._TABLE)
                    .update(row)
                    .eq("tenant_id", tenant_id)
                    .eq("provider", provider)
                    .execute()
                )
            else:
                row["created_at"] = now
                result = self._client.table(self._TABLE).insert(row).execute()
            logger.info("Saved drive connection: tenant=%s provider=%s", tenant_id, provider)
            return result.data[0] if result.data else row
        except Exception as e:
            logger.error("Failed to save drive connection: %s", e)
            raise

    def get_connection(self, tenant_id: str, provider: str) -> dict | None:
        """Load a saved drive connection. Returns dict or None."""
        try:
            result = (
                self._client.table(self._TABLE)
                .select("*")
                .eq("tenant_id", tenant_id)
                .eq("provider", provider)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Failed to load drive connection: %s", e)
            return None

    def update_folder(self, tenant_id: str, provider: str, folder_id: str | None) -> None:
        """Update just the folder_id for an existing connection."""
        try:
            self._client.table(self._TABLE).update(
                {
                    "folder_id": folder_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("tenant_id", tenant_id).eq("provider", provider).execute()
            logger.info(
                "Updated folder: tenant=%s provider=%s folder=%s",
                tenant_id,
                provider,
                folder_id,
            )
        except Exception as e:
            logger.error("Failed to update folder: %s", e)
            raise

    def delete_connection(self, tenant_id: str, provider: str) -> None:
        """Remove a drive connection (disconnect)."""
        try:
            self._client.table(self._TABLE).delete().eq("tenant_id", tenant_id).eq("provider", provider).execute()
            logger.info("Deleted drive connection: tenant=%s provider=%s", tenant_id, provider)
        except Exception as e:
            logger.error("Failed to delete drive connection: %s", e)
            raise
