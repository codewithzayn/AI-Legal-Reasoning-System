"""
Thumbs up/down feedback for LexAI assistant messages.

Stores feedback to a Supabase 'feedback' table and shows
thank-you confirmation after clicking.
"""

import streamlit as st

from src.config.translations import t
from src.ui.supabase_client import get_supabase_client


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
        client.table("feedback").insert(row).execute()
        return True
    except Exception:
        return False


def render_feedback_buttons(message_content: str, query: str, lang: str, message_idx: int) -> None:
    """Render thumbs up/down buttons below an assistant message."""
    feedback_key = f"feedback_{message_idx}"

    # Already gave feedback for this message
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
