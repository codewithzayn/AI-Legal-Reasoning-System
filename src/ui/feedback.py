"""
Thumbs up/down feedback for LexAI assistant messages.

Stores feedback to a Supabase 'feedback' table and shows
thank-you confirmation after clicking.
"""

import streamlit as st

from src.config.logging_config import setup_logger
from src.config.translations import t
from src.ui.supabase_client import get_supabase_client

logger = setup_logger(__name__)


def store_feedback(message_content: str, query: str, rating: str, lang: str) -> bool:
    """Store feedback to Supabase. Returns True on success."""
    client = get_supabase_client()
    if client is None:
        return False
    try:
        row = {
            "message_content": message_content[:2000],
            "query": (query or "")[:2000],
            "rating": rating,
            "lang": lang,
        }
        user_id = st.session_state.get("user_id")
        if user_id:
            row["user_id"] = user_id
        conversation_id = st.session_state.get("current_conversation_id")
        if conversation_id:
            row["conversation_id"] = conversation_id
        client.table("feedback").insert(row).execute()
        return True
    except Exception as exc:
        logger.warning("Failed to store feedback: %s", exc)
        return False


def delete_feedback_for_conversation(conversation_id: str) -> bool:
    """Delete all feedback records linked to a conversation. Returns True on success."""
    client = get_supabase_client()
    user_id = st.session_state.get("user_id")
    if client is None or not user_id or not conversation_id:
        return False
    try:
        client.table("feedback").delete().eq("conversation_id", conversation_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.warning("Failed to delete feedback for conversation %s: %s", conversation_id, exc)
        return False


def render_feedback_buttons(message_content: str, query: str, lang: str, message_idx: int) -> None:
    """Render thumbs up/down buttons below an assistant message."""
    feedback_key = f"feedback_{message_idx}"

    if st.session_state.get(feedback_key):
        st.caption(f"\u2705 {t('feedback_thanks', lang)}")
        return

    col1, col2, _ = st.columns([1, 1, 6])
    with col1:
        if st.button(
            "\U0001f44d",
            key=f"fb_up_{message_idx}",
            help=t("feedback_helpful", lang),
        ):
            store_feedback(message_content, query, "up", lang)
            st.session_state[feedback_key] = "up"
            st.rerun()
    with col2:
        if st.button(
            "\U0001f44e",
            key=f"fb_down_{message_idx}",
            help=t("feedback_not_helpful", lang),
        ):
            store_feedback(message_content, query, "down", lang)
            st.session_state[feedback_key] = "down"
            st.rerun()
