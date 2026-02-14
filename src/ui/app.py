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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.stream import stream_query_response
from src.config.settings import ASSISTANT_AVATAR, PAGE_CONFIG, USER_AVATAR, config, validate_env_for_app
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
            /* Production: optimized layout */
            .block-container {{
                max-width: min(720px, 100vw - 2rem);
                margin: 0 auto;
                padding: 1.25rem 1rem;
            }}
            [data-testid="stChatMessage"] {{
                padding: 0.875rem 1rem;
                border-radius: 10px;
                margin-bottom: 0.5rem;
                background: {THEME_BG};
                box-shadow: 0 1px 2px rgba(15,23,42,0.0);
                border: 1px solid {THEME_BORDER};
            }}
            /* Chat input: prominent, card-style (best practice: clear container, good contrast) */
            [data-testid="stChatInput"] {{
                margin-top: 1.5rem !important;
                padding: 1.25rem !important;
                background: {THEME_SURFACE} !important;
                border: 1px solid {THEME_BORDER} !important;
                border-radius: 12px !important;
                box-shadow: 0 1px 3px rgba(15,23,42,0.04) !important;
            }}
            [data-testid="stChatInput"] textarea {{
                min-height: 120px !important;
                padding: 1rem 1.25rem !important;
                border-radius: 12px !important;
                border: 1px solid {THEME_BORDER} !important;
                font-size: 1rem !important;
                line-height: 1.5 !important;
                outline: none !important;
            }}
            [data-testid="stChatInput"] textarea:focus {{
                border-color: #94a3b8 !important;
                box-shadow: none !important;
                outline: none !important;
            }}
            [data-testid="stChatInput"] textarea::placeholder {{
                color: #64748b;
            }}
            .stButton > button[kind="primary"] {{
                background: {THEME_PRIMARY} !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                padding: 0.5rem 1rem !important;
                font-weight: 600 !important;
            }}
            .main-header {{
                background: linear-gradient(135deg, {THEME_PRIMARY} 0%, {THEME_PRIMARY_LIGHT} 100%);
                padding: 1rem 1.25rem;
                border-radius: 10px;
                margin-bottom: 0.5rem;
                box-shadow: 0 1px 4px rgba(15,23,42,0.06);
            }}
            .main-header h1 {{
                color: white;
                margin: 0;
                font-size: 1.25rem;
                font-weight: 600;
                letter-spacing: -0.02em;
            }}
            .main-header .subtitle {{
                color: rgba(255,255,255,0.9);
                margin: 0.25rem 0 0 0;
                font-size: 0.8125rem;
                line-height: 1.4;
            }}
            .lang-row {{ margin-bottom: 1rem; }}
            [data-testid="stSidebar"] {{
                background: {THEME_SURFACE};
                border-right: 1px solid {THEME_BORDER};
            }}
            [data-testid="stSidebar"] > div {{
                padding-top: 0.75rem;
            }}
            @media (max-width: 640px) {{
                .block-container {{ padding: 1rem 0.75rem; }}
                .main-header {{
                    padding: 0.875rem 1rem;
                    margin-bottom: 1rem;
                }}
                .main-header h1 {{ font-size: 1.125rem; }}
                .main-header .subtitle {{ font-size: 0.75rem; }}
                [data-testid="stChatInput"] {{ padding: 1rem !important; margin-top: 1rem !important; }}
                [data-testid="stChatInput"] textarea {{
                    min-height: 100px !important;
                    padding: 0.875rem 1rem !important;
                }}
                [data-testid="stChatMessage"] {{ padding: 0.75rem 0.875rem; }}
            }}
            /* Responsive: tablet+ */
            @media (min-width: 768px) {{
                .block-container {{
                    padding: 1.5rem 1.25rem;
                }}
            }}
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
    validate_env_for_app()

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
        <div class="main-header">
            <h1>{t("header_title", lang)}</h1>
            <p class="subtitle">{t("header_subtitle", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    initialize_chat_history()
    chat_history = get_chat_history()

    if chat_history:
        for message in chat_history:
            avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
            with st.chat_message(message["role"], avatar=avatar):
                st.write(message["content"])
    else:
        with st.container():
            st.markdown(f"**{t('welcome_title', lang)}**")
            st.markdown(t("welcome_body", lang))
            st.markdown("---")

    st.markdown(f"**{t('ask_question', lang)}**")
    query = st.chat_input(t("placeholder", lang))

    if query and query.strip():
        q = query.strip()
        if len(q) > config.MAX_QUERY_LENGTH:
            st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
        else:
            _process_prompt(q)
        st.rerun()

    with st.sidebar:
        st.markdown(f"**{t('sidebar_app_name', lang)}**")
        st.caption(t("sidebar_tagline", lang))
        st.markdown("---")

        lang_labels = list(LANGUAGE_OPTIONS.keys())
        lang_values = list(LANGUAGE_OPTIONS.values())
        current_idx = lang_values.index(lang) if lang in lang_values else 0
        selected_label = st.selectbox(
            t("language", lang),
            lang_labels,
            index=current_idx,
            key="lang_selector",
        )
        new_lang = LANGUAGE_OPTIONS[selected_label]
        if new_lang != lang:
            st.session_state.lang = new_lang
            st.rerun()

        st.markdown("---")

        if st.button(t("clear_chat", lang), use_container_width=True, type="secondary"):
            clear_chat_history()
            st.rerun()

        st.markdown("---")
        user_count = sum(1 for m in chat_history if m.get("role") == "user")
        st.caption(t("messages_count", lang, count=user_count))
        st.caption(t("input_hint", lang))


if __name__ == "__main__":
    main()
