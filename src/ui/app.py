"""
Streamlit Chat Interface for AI Legal Reasoning System
"""

import os
import sys
import warnings
from pathlib import Path

# Reduce terminal noise from dependencies (set before heavy imports)
os.environ.setdefault("LOG_FORMAT", "simple")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore", message=".*(PyTorch|TensorFlow|Flax).*")

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config.settings import PAGE_CONFIG, APP_TITLE, CHAT_WELCOME_MESSAGE, USER_AVATAR, ASSISTANT_AVATAR
from src.utils.chat_helpers import (
    initialize_chat_history,
    add_message,
    get_chat_history,
    clear_chat_history
)
from src.agent.stream import stream_query_response


# Theme tokens: single source for legal-AI look (aligned with .streamlit/config.toml)
THEME_PRIMARY = "#0f172a"
THEME_PRIMARY_LIGHT = "#1e293b"
THEME_BG = "#ffffff"
THEME_SURFACE = "#f8fafc"
THEME_BORDER = "#e2e8f0"
THEME_TEXT = "#0f172a"
THEME_ACCENT = "#0ea5e9"


def _inject_custom_css() -> None:
    """Inject CSS: aligned structure, single theme, legal-AI look."""
    st.markdown(f"""
        <style>
            /* Single column, readable width */
            .block-container {{ max-width: 44rem; margin-left: auto; margin-right: auto; padding-top: 1.5rem; padding-bottom: 3rem; }}
            /* Chat messages: one block per message, clear hierarchy */
            [data-testid="stChatMessage"] {{
                padding: 1rem 1.25rem;
                border-radius: 12px;
                margin-bottom: 0.75rem;
                background: {THEME_BG};
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
                border: 1px solid {THEME_BORDER};
            }}
            textarea {{ border-radius: 10px !important; min-height: 112px !important; border: 1px solid {THEME_BORDER} !important; }}
            textarea:focus {{ outline: 2px solid {THEME_ACCENT} !important; outline-offset: 2px !important; }}
            .stButton > button[kind="primary"] {{
                background: {THEME_PRIMARY} !important;
                color: white !important;
                border: none !important;
                border-radius: 10px !important;
                padding: 0.5rem 1.25rem !important;
                font-weight: 600 !important;
            }}
            .stButton > button[kind="primary"]:hover {{ box-shadow: 0 4px 12px rgba(15, 23, 42, 0.25) !important; }}
            .stSidebar .stButton > button {{ border-radius: 8px !important; }}
            .input-card {{
                border-radius: 12px;
                padding: 1.25rem;
                background: {THEME_SURFACE};
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
                border: 1px solid {THEME_BORDER};
                margin: 1rem 0;
            }}
            .main-header-card {{
                background: {THEME_PRIMARY};
                padding: 0.875rem 1.25rem;
                border-radius: 12px;
                margin-bottom: 1.25rem;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.1);
            }}
            .main-header-card .subtitle {{ color: rgba(255,255,255,0.88); margin: 0.25rem 0 0 0; font-size: 0.875rem; }}
        </style>
    """, unsafe_allow_html=True)


def _process_prompt(prompt: str) -> None:
    """Add user message, run agent, add assistant response."""
    add_message("user", prompt)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(prompt)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("🔍 Searching knowledge base..."):
            response = st.write_stream(stream_query_response(prompt))
    add_message("assistant", response)


def main():
    """Main Streamlit application"""
    st.set_page_config(
        page_title=PAGE_CONFIG["page_title"],
        page_icon=PAGE_CONFIG["page_icon"],
        layout=PAGE_CONFIG["layout"],
        initial_sidebar_state=PAGE_CONFIG["initial_sidebar_state"],
    )
    _inject_custom_css()
    
    # Header: product name + single-line purpose
    st.markdown("""
        <div class="main-header-card">
            <h2 style='color: white; margin: 0; font-size: 1.25rem; font-weight: 600;'>
                Finnish Legal Reasoning
            </h2>
            <p class="subtitle">Ask about statutes, case law, and regulations in Finnish or English.</p>
        </div>
    """, unsafe_allow_html=True)
    
    initialize_chat_history()
    
    # Chat: single responsibility — show conversation
    for message in get_chat_history():
        avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            st.write(message["content"])
    
    # Input: single entry point — ask here
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown("**Ask a question**")
    with st.form("chat_form", clear_on_submit=True):
        query = st.text_area(
            "Query",
            value="",
            height=112,
            placeholder=CHAT_WELCOME_MESSAGE,
            label_visibility="collapsed",
            key="query_input",
        )
        col1, col2 = st.columns([1, 4])
        with col1:
            submitted = st.form_submit_button("Send")
        with col2:
            st.caption("Ask about Finnish law in Finnish or English.")
    st.markdown("</div>", unsafe_allow_html=True)
    
    if submitted and query and query.strip():
        _process_prompt(query.strip())
        st.rerun()
    
    # Sidebar: settings and system info only
    with st.sidebar:
        st.header("Settings")
        if st.button("Clear Chat History", use_container_width=True):
            clear_chat_history()
            st.rerun()
        st.divider()
        st.subheader("System")
        st.info(f"Messages: {len(get_chat_history())}")


if __name__ == "__main__":
    main()
