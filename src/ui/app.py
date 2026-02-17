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
from src.utils.query_context import resolve_query_with_context
from src.utils.year_filter import parse_year_response

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
            /* ── Base layout ─────────────────────────────────── */
            .block-container {{
                max-width: min(720px, 100vw);
                margin: 0 auto;
                padding: 1.25rem 1rem 6rem 1rem;
            }}

            /* ── Chat bubbles ────────────────────────────────── */
            [data-testid="stChatMessage"] {{
                padding: 0.875rem 1rem;
                border-radius: 12px;
                margin-bottom: 0.5rem;
                background: {THEME_BG};
                border: 1px solid {THEME_BORDER};
            }}
            [data-testid="stChatMessage"] p {{
                font-size: 0.9375rem;
                line-height: 1.6;
            }}

            /* ── Sticky bottom input bar ─────────────────────── */
            [data-testid="stBottom"] {{
                background: {THEME_BG} !important;
                border-top: 1px solid {THEME_BORDER} !important;
                padding: 0.5rem 0.75rem !important;
            }}
            [data-testid="stChatInput"] {{
                margin: 0 !important;
                padding: 0 !important;
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }}
            /* The actual textarea inside the chat input */
            [data-testid="stChatInput"] textarea {{
                min-height: 48px !important;
                max-height: 160px !important;
                padding: 0.75rem 1rem !important;
                border-radius: 24px !important;
                border: 2px solid {THEME_BORDER} !important;
                background: {THEME_SURFACE} !important;
                font-size: 1rem !important;
                line-height: 1.5 !important;
                resize: none !important;
                transition: border-color 0.15s ease !important;
            }}
            [data-testid="stChatInput"] textarea:focus {{
                border-color: {THEME_ACCENT} !important;
                box-shadow: 0 0 0 3px rgba(14,165,233,0.12) !important;
                outline: none !important;
            }}
            [data-testid="stChatInput"] textarea::placeholder {{
                color: #94a3b8;
                font-size: 0.9375rem;
            }}
            /* Send button inside the chat input container */
            [data-testid="stChatInput"] button {{
                border-radius: 50% !important;
                width: 40px !important;
                height: 40px !important;
                min-width: 40px !important;
                padding: 0 !important;
                background: {THEME_PRIMARY} !important;
                border: none !important;
                transition: transform 0.1s ease !important;
            }}
            [data-testid="stChatInput"] button:hover {{
                transform: scale(1.05) !important;
            }}
            [data-testid="stChatInput"] button svg {{
                fill: white !important;
            }}

            /* ── Primary buttons ─────────────────────────────── */
            .stButton > button[kind="primary"] {{
                background: {THEME_PRIMARY} !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                padding: 0.5rem 1rem !important;
                font-weight: 600 !important;
            }}

            /* ── Header banner ───────────────────────────────── */
            .main-header {{
                background: linear-gradient(135deg, {THEME_PRIMARY} 0%, {THEME_PRIMARY_LIGHT} 100%);
                padding: 1.125rem 1.25rem;
                border-radius: 12px;
                margin-bottom: 0.75rem;
                box-shadow: 0 2px 8px rgba(15,23,42,0.08);
            }}
            .main-header h1 {{
                color: white;
                margin: 0;
                font-size: 1.25rem;
                font-weight: 700;
                letter-spacing: -0.02em;
            }}
            .main-header .subtitle {{
                color: rgba(255,255,255,0.88);
                margin: 0.25rem 0 0 0;
                font-size: 0.8125rem;
                line-height: 1.4;
            }}

            /* ── Welcome card ────────────────────────────────── */
            .welcome-card {{
                background: {THEME_SURFACE};
                border: 1px solid {THEME_BORDER};
                border-radius: 12px;
                padding: 1.25rem 1.25rem 1rem;
                margin-bottom: 0.75rem;
            }}
            .welcome-card strong {{ font-size: 1rem; }}
            .welcome-card p {{ color: #475569; font-size: 0.875rem; line-height: 1.6; margin: 0.5rem 0 0 0; }}

            /* ── Sidebar ─────────────────────────────────────── */
            [data-testid="stSidebar"] {{
                background: {THEME_SURFACE};
                border-right: 1px solid {THEME_BORDER};
            }}
            [data-testid="stSidebar"] > div {{
                padding-top: 0.75rem;
            }}

            /* ── Mobile (< 640px) ────────────────────────────── */
            @media (max-width: 640px) {{
                .block-container {{
                    padding: 0.75rem 0.5rem 5rem 0.5rem;
                }}
                .main-header {{
                    padding: 0.875rem 1rem;
                    border-radius: 10px;
                    margin-bottom: 0.5rem;
                }}
                .main-header h1 {{ font-size: 1.0625rem; }}
                .main-header .subtitle {{ font-size: 0.75rem; }}
                [data-testid="stBottom"] {{
                    padding: 0.375rem 0.5rem !important;
                }}
                [data-testid="stChatInput"] textarea {{
                    min-height: 44px !important;
                    max-height: 120px !important;
                    padding: 0.625rem 0.875rem !important;
                    font-size: 1rem !important;
                    border-radius: 22px !important;
                    /* Prevent iOS zoom-on-focus (font must be >= 16px) */
                    -webkit-text-size-adjust: 100%;
                }}
                [data-testid="stChatInput"] button {{
                    width: 36px !important;
                    height: 36px !important;
                    min-width: 36px !important;
                }}
                [data-testid="stChatMessage"] {{
                    padding: 0.625rem 0.75rem;
                    border-radius: 10px;
                }}
                [data-testid="stChatMessage"] p {{
                    font-size: 0.875rem;
                }}
                .welcome-card {{
                    padding: 1rem;
                }}
            }}

            /* ── Tablet+ (>= 768px) ─────────────────────────── */
            @media (min-width: 768px) {{
                .block-container {{
                    padding: 1.5rem 1.25rem 6rem 1.25rem;
                }}
            }}

            /* ── Hide Streamlit branding for cleaner mobile look ── */
            #MainMenu {{ visibility: hidden; }}
            footer {{ visibility: hidden; }}
            header {{ visibility: hidden; }}
        </style>
    """,
        unsafe_allow_html=True,
    )


def _is_year_clarification_message(msg: str, lang: str) -> bool:
    """True if msg is (or contains) the year clarification question (any language).

    Stored messages may include stream prefixes like 'Analyzing question...' before
    the clarification text, so we check for containment, not exact match.
    """
    content = (msg or "").strip()
    return any(t("year_clarification", code).strip() in content for code in ("en", "fi", "sv"))


def _process_prompt(prompt: str) -> None:
    lang = _get_lang()
    chat_history = get_chat_history()
    original_query = None
    year_range = None

    if len(chat_history) >= 2:
        last_msg = chat_history[-1]
        prev_msg = chat_history[-2]
        if (
            last_msg.get("role") == "assistant"
            and _is_year_clarification_message(last_msg.get("content", ""), lang)
            and prev_msg.get("role") == "user"
        ):
            original_query = prev_msg.get("content", "").strip()
            parsed = parse_year_response(prompt)
            year_range = parsed

    if original_query is None:
        effective_query, ctx_year = resolve_query_with_context(prompt, chat_history)
        if ctx_year is not None or effective_query != prompt:
            original_query = effective_query
            year_range = ctx_year

    add_message("user", prompt)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(prompt)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR), st.spinner(t("spinner_searching", lang)):
        if original_query:
            yr = year_range if year_range is not None else (None, None)
            response = st.write_stream(
                stream_query_response(
                    prompt, lang=lang, original_query_for_year=original_query, year_range=yr, chat_history=chat_history
                )
            )
        else:
            response = st.write_stream(stream_query_response(prompt, lang=lang, chat_history=chat_history))
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
        st.markdown(
            f"""<div class="welcome-card">
                <strong>{t("welcome_title", lang)}</strong>
                <p>{t("welcome_body", lang)}</p>
            </div>""",
            unsafe_allow_html=True,
        )

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
