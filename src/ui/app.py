"""
Streamlit Chat Interface for AI Legal Reasoning System
"""

import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("LOG_FORMAT", "simple")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore", message=".*(PyTorch|TensorFlow|Flax).*")

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent.stream import stream_query_response
from src.config.settings import ASSISTANT_AVATAR, PAGE_CONFIG, USER_AVATAR  # noqa: F401
from src.config.translations import LANGUAGE_OPTIONS, t
from src.utils.chat_helpers import add_message, clear_chat_history, get_chat_history, initialize_chat_history

THEME_PRIMARY = "#0f172a"
THEME_PRIMARY_LIGHT = "#1e293b"
THEME_BG = "#ffffff"
THEME_SURFACE = "#f8fafc"
THEME_BORDER = "#e2e8f0"
THEME_TEXT = "#0f172a"
THEME_ACCENT = "#0ea5e9"


def _get_lang() -> str:
    return st.session_state.get("lang", "en")


def _inject_custom_css() -> None:
    st.markdown(
        f"""
        <style>
            .block-container {{ max-width: 44rem; margin-left: auto; margin-right: auto; padding-top: 1.5rem; padding-bottom: 3rem; }}
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
    """,
        unsafe_allow_html=True,
    )


def _process_prompt(prompt: str) -> None:
    lang = _get_lang()
    add_message("user", prompt)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(prompt)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR), st.spinner(t("spinner_searching", lang)):
        response = st.write_stream(stream_query_response(prompt, lang=lang))
    add_message("assistant", response)


def main():
    if "lang" not in st.session_state:
        st.session_state.lang = "en"
    lang = _get_lang()

    st.set_page_config(
        page_title=t("page_title", lang),
        page_icon=PAGE_CONFIG["page_icon"],
        layout=PAGE_CONFIG["layout"],
        initial_sidebar_state=PAGE_CONFIG["initial_sidebar_state"],
    )

    _inject_custom_css()

    st.markdown(
        f"""
        <div class="main-header-card">
            <h2 style='color: white; margin: 0; font-size: 1.25rem; font-weight: 600;'>
                {t("header_title", lang)}
            </h2>
            <p class="subtitle">{t("header_subtitle", lang)}</p>
        </div>
    """,
        unsafe_allow_html=True,
    )

    initialize_chat_history()

    for message in get_chat_history():
        avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            st.write(message["content"])

    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown(f"**{t('ask_question', lang)}**")
    with st.form("chat_form", clear_on_submit=True):
        query = st.text_area(
            "Query",
            value="",
            height=112,
            placeholder=t("placeholder", lang),
            label_visibility="collapsed",
            key="query_input",
        )
        col1, col2 = st.columns([1, 4])
        with col1:
            submitted = st.form_submit_button(t("send", lang))
        with col2:
            st.caption(t("input_hint", lang))
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted and query and query.strip():
        _process_prompt(query.strip())
        st.rerun()

    with st.sidebar:
        st.header(t("settings", lang))

        lang_labels = list(LANGUAGE_OPTIONS.keys())
        lang_values = list(LANGUAGE_OPTIONS.values())
        current_index = lang_values.index(lang) if lang in lang_values else 0
        selected_label = st.selectbox(
            t("language", lang),
            lang_labels,
            index=current_index,
            key="lang_selector",
        )
        new_lang = LANGUAGE_OPTIONS[selected_label]
        if new_lang != lang:
            st.session_state.lang = new_lang
            st.rerun()

        st.divider()

        if st.button(t("clear_chat", lang), use_container_width=True):
            clear_chat_history()
            st.rerun()
        st.divider()
        st.subheader(t("system", lang))
        st.info(t("messages_count", lang, count=len(get_chat_history())))


if __name__ == "__main__":
    main()
