"""
Thumbs up/down feedback for LexAI assistant messages.

Stores feedback to a Supabase 'feedback' table and shows
thank-you confirmation after clicking.
"""

import os

import streamlit as st

from src.config.translations import t


def _get_supabase_client():
    """Lazy-load synchronous Supabase client for feedback storage."""
    if "feedback_supabase" not in st.session_state:
        try:
            from supabase import create_client

            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_KEY", "")
            if url and key:
                st.session_state.feedback_supabase = create_client(url, key)
            else:
                st.session_state.feedback_supabase = None
        except Exception:
            st.session_state.feedback_supabase = None
    return st.session_state.feedback_supabase


def store_feedback(message_content: str, query: str, rating: str, lang: str) -> bool:
    """Store feedback to Supabase. Returns True on success."""
    client = _get_supabase_client()
    if client is None:
        return False
    try:
        client.table("feedback").insert(
            {
                "message_content": message_content[:2000],
                "query": (query or "")[:2000],
                "rating": rating,
                "lang": lang,
            }
        ).execute()
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
