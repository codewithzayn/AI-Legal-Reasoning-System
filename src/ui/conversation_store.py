"""
Conversation persistence for LexAI.

CRUD operations for the 'conversations' Supabase table.
Auto-saves after each message exchange, supports load/delete from sidebar.
"""

import json
import os

import streamlit as st


def _get_supabase_client():
    """Lazy-load synchronous Supabase client for conversations."""
    if "conv_supabase" not in st.session_state:
        try:
            from supabase import create_client

            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_KEY", "")
            if url and key:
                st.session_state.conv_supabase = create_client(url, key)
            else:
                st.session_state.conv_supabase = None
        except Exception:
            st.session_state.conv_supabase = None
    return st.session_state.conv_supabase


def save_conversation(messages: list[dict], lang: str, conversation_id: str | None = None) -> str | None:
    """Save or update a conversation. Returns the conversation ID or None on failure."""
    client = _get_supabase_client()
    if client is None or not messages:
        return None

    # Generate title from first user message
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
                    "updated_at": "now()",
                }
            ).eq("id", conversation_id).execute()
            return conversation_id
        result = (
            client.table("conversations")
            .insert(
                {
                    "title": title,
                    "messages_json": json.dumps(messages, ensure_ascii=False),
                    "lang": lang,
                }
            )
            .execute()
        )
        if result.data:
            return result.data[0]["id"]
    except Exception:
        pass
    return None


def list_conversations(limit: int = 20) -> list[dict]:
    """List recent conversations, newest first."""
    client = _get_supabase_client()
    if client is None:
        return []
    try:
        result = (
            client.table("conversations")
            .select("id, title, lang, created_at, updated_at")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def load_conversation(conversation_id: str) -> list[dict] | None:
    """Load messages for a conversation. Returns list of message dicts or None."""
    client = _get_supabase_client()
    if client is None:
        return None
    try:
        result = client.table("conversations").select("messages_json").eq("id", conversation_id).limit(1).execute()
        if result.data:
            raw = result.data[0]["messages_json"]
            if isinstance(raw, str):
                return json.loads(raw)
            return raw
    except Exception:
        pass
    return None


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation. Returns True on success."""
    client = _get_supabase_client()
    if client is None:
        return False
    try:
        client.table("conversations").delete().eq("id", conversation_id).execute()
        return True
    except Exception:
        return False
