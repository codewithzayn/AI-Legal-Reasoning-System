"""
Shared Supabase client for LexAI UI (feedback, conversations).

Lazy-loaded once per Streamlit session and reused by all UI modules.
"""

import os

import streamlit as st

SESSION_KEY = "ui_supabase"


def get_supabase_client():
    """Lazy-load synchronous Supabase client for UI (feedback, conversations)."""
    if SESSION_KEY not in st.session_state:
        try:
            from supabase import create_client

            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_KEY", "")
            if url and key:
                st.session_state[SESSION_KEY] = create_client(url, key)
            else:
                st.session_state[SESSION_KEY] = None
        except Exception:
            st.session_state[SESSION_KEY] = None
    return st.session_state[SESSION_KEY]
