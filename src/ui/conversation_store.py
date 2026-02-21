"""
Conversation persistence for LexAI.

CRUD operations for the 'conversations' Supabase table.
Auto-saves after each message exchange, supports load/delete from sidebar.
All operations are scoped to the authenticated user via user_id.
"""

import json
from datetime import datetime, timezone

import streamlit as st

from src.config.logging_config import setup_logger
from src.ui.supabase_client import get_supabase_client

logger = setup_logger(__name__)


def _get_user_id() -> str | None:
    """Return the current authenticated user's ID from session state."""
    return st.session_state.get("user_id")


def save_conversation(messages: list[dict], lang: str, conversation_id: str | None = None) -> str | None:
    """Save or update a conversation. Returns the conversation ID or None on failure."""
    client = get_supabase_client()
    user_id = _get_user_id()
    if client is None or not messages or not user_id:
        return None

    title = "Untitled"
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            title = msg["content"][:80]
            break

    try:
        if conversation_id:
            client.table("conversations").update(
                {
                    "title": title,
                    "messages_json": json.dumps(messages, ensure_ascii=False),
                    "lang": lang,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", conversation_id).eq("user_id", user_id).execute()
            return conversation_id
        result = (
            client.table("conversations")
            .insert(
                {
                    "title": title,
                    "messages_json": json.dumps(messages, ensure_ascii=False),
                    "lang": lang,
                    "user_id": user_id,
                }
            )
            .execute()
        )
        if result.data:
            return result.data[0]["id"]
    except Exception as exc:
        logger.warning("Failed to save conversation: %s", exc)
    return None


def list_conversations(limit: int = 20) -> list[dict]:
    """List recent conversations for the current user, newest first."""
    client = get_supabase_client()
    user_id = _get_user_id()
    if client is None or not user_id:
        return []
    try:
        result = (
            client.table("conversations")
            .select("id, title, lang, created_at, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.warning("Failed to list conversations: %s", exc)
        return []


def load_conversation(conversation_id: str) -> list[dict] | None:
    """Load messages for a conversation owned by the current user."""
    client = get_supabase_client()
    user_id = _get_user_id()
    if client is None or not user_id:
        return None
    try:
        result = (
            client.table("conversations")
            .select("messages_json")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if result.data:
            raw = result.data[0]["messages_json"]
            if isinstance(raw, str):
                return json.loads(raw)
            return raw
    except Exception as exc:
        logger.warning("Failed to load conversation %s: %s", conversation_id, exc)
    return None


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation owned by the current user. Returns True on success."""
    client = get_supabase_client()
    user_id = _get_user_id()
    if client is None or not user_id:
        return False
    try:
        client.table("conversations").delete().eq("id", conversation_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.warning("Failed to delete conversation %s: %s", conversation_id, exc)
        return False
