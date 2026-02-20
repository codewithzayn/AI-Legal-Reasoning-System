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

import re

import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.stream import stream_query_response_sync
from src.config.prompt_templates import get_templates_for_lang
from src.config.settings import ASSISTANT_AVATAR, PAGE_CONFIG, USER_AVATAR, config, validate_env_for_app
from src.config.translations import LANGUAGE_OPTIONS, t
from src.utils.chat_helpers import add_message, clear_chat_history, get_chat_history, initialize_chat_history
from src.utils.query_context import resolve_query_with_context
from src.utils.year_llm import interpret_year_reply_sync

# Legal AI color palette — professional, trustworthy, interactive
THEME_PRIMARY = "#1e3a5f"
THEME_PRIMARY_LIGHT = "#2d4a73"
THEME_BG = "#ffffff"
THEME_SURFACE = "#f8fafc"
THEME_BORDER = "#e2e8f0"
THEME_TEXT = "#0f172a"
THEME_ACCENT = "#2563eb"
THEME_ACCENT_SOFT = "rgba(37, 99, 235, 0.12)"
THEME_SIDEBAR_ACCENT = "#7c3aed"


def _get_lang() -> str:
    return st.session_state.get("lang", "en")


def _markdown_to_safe_html(text: str) -> str:
    """Convert minimal markdown (links, bold, newlines) to HTML for fixed-size container. Sanitizes hrefs to http/https only."""
    if not text or not text.strip():
        return ""
    s = text.strip()
    # Escaping for HTML
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Links: [text](url) - only allow http/https
    def _link_repl(m):
        label, url = m.group(1), m.group(2)
        if url.startswith(("http://", "https://")):
            return f'<a href="{url}">{label}</a>'
        return label

    s = re.sub(r"\[([^\]]*)\]\((https?://[^\)]+)\)", _link_repl, s)
    # Bold: **text**
    s = re.sub(r"\*\*([^\*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^\*]+)\*", r"<em>\1</em>", s)
    # Paragraphs / newlines
    lines = [f"<p>{ln}</p>" if ln.strip() else "<br/>" for ln in s.split("\n")]
    return "\n".join(lines)


def _inject_scroll_to_bottom() -> None:
    """Scroll the main page to bottom (input area). Used after template click to avoid jumping to top."""
    st.markdown(
        '<div id="chat-input-anchor" style="height:0;overflow:hidden;margin:0;padding:0;"></div>',
        unsafe_allow_html=True,
    )
    components.html(
        """
        <script>
        (function() {
            try {
                var doc = window.parent.document;
                var el = doc.getElementById('chat-input-anchor');
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    var h = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
                    window.parent.scrollTo({ top: h, behavior: 'smooth' });
                }
            } catch (_) {}
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


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

            /* ── Chat bubbles: consistent width, height fits content ─── */
            [data-testid="stChatMessage"] {{
                padding: 0.875rem 1rem;
                border-radius: 14px;
                margin-bottom: 0.625rem;
                border: 1px solid {THEME_BORDER};
                border-left: 4px solid {THEME_ACCENT};
                background: {THEME_SURFACE} !important;
                transition: box-shadow 0.2s ease;
                min-width: min(100%, 680px);
                width: 100%;
                box-sizing: border-box;
            }}
            [data-testid="stChatMessage"]:hover {{
                box-shadow: 0 2px 12px rgba(37, 99, 235, 0.08);
            }}
            [data-testid="stChatMessage"] p {{
                font-size: 0.9375rem;
                line-height: 1.65;
            }}
            /* Assistant message content: markdown links and structure */
            [data-testid="stChatMessage"] a {{
                color: {THEME_ACCENT};
                text-decoration: none;
                border-bottom: 1px solid transparent;
            }}
            [data-testid="stChatMessage"] a:hover {{
                border-bottom-color: {THEME_ACCENT};
            }}
            [data-testid="stChatMessage"] ul, [data-testid="stChatMessage"] ol {{
                margin: 0.5rem 0 0.75rem 1.25rem;
                padding-left: 1rem;
            }}
            [data-testid="stChatMessage"] li {{
                margin-bottom: 0.25rem;
            }}
            /* Content area: width full, height fits content */
            .assistant-content-fixed {{
                min-width: 100%;
                width: 100%;
                display: block;
                padding: 0.25rem 0;
                box-sizing: border-box;
            }}
            /* Thinking/analyzing phase: compact, height fits text */
            .assistant-thinking {{
                color: #64748b;
                font-size: 0.9375rem;
                padding: 0.25rem 0;
            }}
            /* Rendered response (markdown-as-HTML) inside fixed container */
            .assistant-response {{
                font-size: 0.9375rem;
                line-height: 1.65;
            }}
            .assistant-response p {{ margin: 0.5rem 0 0.75rem 0; }}
            .assistant-response a {{
                color: {THEME_ACCENT};
                text-decoration: none;
                border-bottom: 1px solid transparent;
            }}
            .assistant-response a:hover {{ border-bottom-color: {THEME_ACCENT}; }}
            .assistant-response ul, .assistant-response ol {{
                margin: 0.5rem 0 0.75rem 1.25rem;
                padding-left: 1rem;
            }}
            .assistant-response li {{ margin-bottom: 0.25rem; }}

            /* ── Sticky bottom input bar ─────────────────────── */
            [data-testid="stBottom"] {{
                background: linear-gradient(to top, {THEME_BG} 0%, {THEME_SURFACE} 100%) !important;
                border-top: 1px solid {THEME_BORDER} !important;
                padding: 0.5rem 0.75rem !important;
                box-shadow: 0 -4px 12px rgba(0,0,0,0.04);
            }}
            [data-testid="stChatInput"] {{
                margin: 0 !important;
                padding: 0 !important;
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }}
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
                transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
            }}
            [data-testid="stChatInput"] textarea:focus {{
                border-color: {THEME_ACCENT} !important;
                box-shadow: 0 0 0 4px {THEME_ACCENT_SOFT} !important;
                outline: none !important;
            }}
            [data-testid="stChatInput"] textarea::placeholder {{
                color: #94a3b8;
                font-size: 0.9375rem;
            }}
            [data-testid="stChatInput"] button {{
                border-radius: 50% !important;
                width: 40px !important;
                height: 40px !important;
                min-width: 40px !important;
                padding: 0 !important;
                background: linear-gradient(135deg, {THEME_ACCENT} 0%, {THEME_PRIMARY} 100%) !important;
                border: none !important;
                transition: transform 0.15s ease, box-shadow 0.2s ease !important;
            }}
            [data-testid="stChatInput"] button:hover {{
                transform: scale(1.08) !important;
                box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35) !important;
            }}
            [data-testid="stChatInput"] button svg {{
                fill: white !important;
            }}

            /* ── Primary buttons ─────────────────────────────── */
            .stButton > button[kind="primary"] {{
                background: linear-gradient(135deg, {THEME_ACCENT} 0%, {THEME_PRIMARY} 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 10px !important;
                padding: 0.5rem 1.25rem !important;
                font-weight: 600 !important;
                transition: transform 0.15s ease, box-shadow 0.2s ease !important;
            }}
            .stButton > button[kind="primary"]:hover {{
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
            }}

            /* ── Secondary / template buttons: interactive ──────── */
            .stButton > button[kind="secondary"] {{
                border-radius: 10px !important;
                border: 1.5px solid {THEME_BORDER} !important;
                transition: all 0.2s ease !important;
            }}
            .stButton > button[kind="secondary"]:hover {{
                transform: translateY(-2px) !important;
                box-shadow: 0 4px 12px rgba(124, 58, 237, 0.15) !important;
                border-color: {THEME_SIDEBAR_ACCENT} !important;
                background: rgba(124, 58, 237, 0.06) !important;
            }}

            /* ── Header banner ───────────────────────────────── */
            .main-header {{
                background: linear-gradient(135deg, {THEME_PRIMARY} 0%, {THEME_PRIMARY_LIGHT} 50%, #3d5a80 100%);
                padding: 1.25rem 1.5rem;
                border-radius: 14px;
                margin-bottom: 0.875rem;
                box-shadow: 0 4px 16px rgba(30, 58, 95, 0.2);
            }}
            .main-header h1 {{
                color: white;
                margin: 0;
                font-size: 1.3125rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            }}
            .main-header .subtitle {{
                color: rgba(255,255,255,0.92);
                margin: 0.35rem 0 0 0;
                font-size: 0.875rem;
                line-height: 1.45;
            }}

            /* ── Welcome card ────────────────────────────────── */
            .welcome-card {{
                background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
                border: 1px solid {THEME_BORDER};
                border-left: 4px solid {THEME_ACCENT};
                border-radius: 14px;
                padding: 1.375rem 1.5rem 1.125rem;
                margin-bottom: 0.875rem;
                box-shadow: 0 2px 8px rgba(37, 99, 235, 0.06);
            }}
            .welcome-card strong {{ font-size: 1.0625rem; color: {THEME_PRIMARY}; }}
            .welcome-card p {{ color: #475569; font-size: 0.9375rem; line-height: 1.65; margin: 0.5rem 0 0 0; }}

            /* ── Quick-start template section ─────────────────── */
            .templates-section {{ margin-top: 0.5rem; }}

            /* ── Sidebar ─────────────────────────────────────── */
            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, {THEME_SURFACE} 0%, #f1f5f9 100%);
                border-right: 1px solid {THEME_BORDER};
            }}
            [data-testid="stSidebar"] > div {{
                padding-top: 0.75rem;
            }}
            [data-testid="stSidebar"] .stMarkdown strong {{
                color: {THEME_PRIMARY};
            }}

            /* ── Selectbox styling ───────────────────────────── */
            [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
                border-radius: 8px;
            }}
            /* ── Prompt guide expander ───────────────────────── */
            .prompt-guide {{
                color: {THEME_TEXT};
                font-size: 0.875rem;
            }}

            /* ── Mobile (< 640px) ────────────────────────────── */
            @media (max-width: 640px) {{
                .block-container {{ padding: 0.75rem 0.5rem 5rem 0.5rem; }}
                .main-header {{
                    padding: 1rem 1.125rem;
                    border-radius: 12px;
                    margin-bottom: 0.625rem;
                }}
                .main-header h1 {{ font-size: 1.125rem; }}
                .main-header .subtitle {{ font-size: 0.8125rem; }}
                [data-testid="stBottom"] {{ padding: 0.375rem 0.5rem !important; }}
                [data-testid="stChatInput"] textarea {{
                    min-height: 44px !important;
                    max-height: 120px !important;
                    padding: 0.625rem 0.875rem !important;
                    font-size: 1rem !important;
                    border-radius: 22px !important;
                    -webkit-text-size-adjust: 100%;
                }}
                [data-testid="stChatInput"] button {{
                    width: 36px !important;
                    height: 36px !important;
                    min-width: 36px !important;
                }}
                [data-testid="stChatMessage"] {{
                    padding: 0.75rem 0.875rem;
                    border-radius: 12px;
                }}
                [data-testid="stChatMessage"] p, .assistant-response {{ font-size: 0.875rem; }}
                .welcome-card {{ padding: 1.125rem 1rem; border-radius: 12px; }}
            }}

            /* ── Tablet+ (>= 768px) ─────────────────────────── */
            @media (min-width: 768px) {{
                .block-container {{ padding: 1.5rem 1.25rem 6rem 1.25rem; }}
            }}

            /* ── Desktop (>= 1024px) ────────────────────────── */
            @media (min-width: 1024px) {{
                .block-container {{ max-width: min(800px, 90vw); }}
            }}

            /* ── Hide Streamlit branding ─────────────────────── */
            #MainMenu {{ visibility: hidden; }}
            footer {{ visibility: hidden; }}
            header {{ visibility: hidden; }}
        </style>
    """,
        unsafe_allow_html=True,
    )


def _render_quick_start_templates(lang: str) -> None:
    """Show 2–3 quick-start template buttons in main area when chat is empty."""
    template_lang = "en" if lang == "auto" else lang
    templates = get_templates_for_lang(template_lang)[:3]
    if not templates:
        return
    st.markdown("")
    st.markdown(f"**{t('templates_heading', lang)}**")
    cols = st.columns(3)
    for i, tmpl in enumerate(templates):
        with cols[i]:
            if st.button(
                tmpl["label"],
                key=f"quick_{template_lang}_{i}",
                use_container_width=True,
                type="secondary",
            ):
                if len(tmpl["prompt"]) <= config.MAX_QUERY_LENGTH:
                    st.session_state.pending_template = tmpl["prompt"]
                    st.session_state.scroll_to_bottom = True
                else:
                    st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
                st.rerun()


def _is_year_clarification_message(msg: str, lang: str) -> bool:
    """True if msg is (or contains) the year clarification question (any language).

    Stored messages may include stream status prefixes like '🔍 Searching...\n\n'
    before the clarification text. We strip those before checking.
    """
    import re as _re

    content = (msg or "").strip()
    # Remove leading status lines (emoji + status word + ellipsis)
    content = _re.sub(
        r"^[\U0001F300-\U0001FFFF\U00002702-\U000027B0\U0001F004\U0001F0CF\u2600-\u26FF]+\s.*?\n+",
        "",
        content,
        flags=_re.DOTALL,
    ).strip()
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
            year_range = interpret_year_reply_sync(prompt)

    if original_query is None:
        effective_query, ctx_year = resolve_query_with_context(prompt, chat_history)
        if ctx_year is not None or effective_query != prompt:
            original_query = effective_query
            year_range = ctx_year

    add_message("user", prompt)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(prompt)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        placeholder = st.empty()
        accumulated: list[str] = []
        if original_query:
            yr = year_range if year_range is not None else (None, None)
            stream = stream_query_response_sync(
                prompt, lang=lang, original_query_for_year=original_query, year_range=yr, chat_history=chat_history
            )
        else:
            stream = stream_query_response_sync(prompt, lang=lang, chat_history=chat_history)
        for chunk in stream:
            accumulated.append(chunk)
            text = "".join(accumulated)
            with placeholder.container():
                is_status_only = (
                    len(text) < 120
                    and (
                        "Analyzing" in text
                        or "Searching" in text
                        or "Etsitään" in text
                        or "Analys" in text
                        or "Söker" in text
                    )
                    and "](http" not in text
                    and "**" not in text
                )
                if is_status_only:
                    st.markdown(
                        f'<div class="assistant-content-fixed"><div class="assistant-thinking">{" ".join(text.split())}</div></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    html_body = _markdown_to_safe_html(text)
                    st.markdown(
                        f'<div class="assistant-content-fixed"><div class="assistant-response">{html_body}</div></div>',
                        unsafe_allow_html=True,
                    )
        response = "".join(accumulated)
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

    if "pending_template" not in st.session_state:
        st.session_state.pending_template = None
    if "scroll_to_bottom" not in st.session_state:
        st.session_state.scroll_to_bottom = False

    initialize_chat_history()
    chat_history = get_chat_history()

    _render_chat_or_welcome(chat_history, lang)
    _render_input_area(lang)

    if st.session_state.scroll_to_bottom:
        _inject_scroll_to_bottom()
        st.session_state.scroll_to_bottom = False

    _render_sidebar(lang, chat_history)


def _render_chat_or_welcome(chat_history: list, lang: str) -> None:
    if chat_history:
        for message in chat_history:
            avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
            with st.chat_message(message["role"], avatar=avatar):
                content = message.get("content") or ""
                if message.get("role") == "assistant" and content:
                    st.markdown(content)
                else:
                    st.write(content)
    else:
        st.markdown(
            f"""<div class="welcome-card">
                <strong>{t("welcome_title", lang)}</strong>
                <p>{t("welcome_body", lang)}</p>
            </div>""",
            unsafe_allow_html=True,
        )
        _render_quick_start_templates(lang)


def _render_input_area(lang: str) -> None:
    if st.session_state.pending_template is not None:
        st.text_area(
            t("edit_template_label", lang),
            value=st.session_state.pending_template,
            height=120,
            key="pending_template_input",
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button(t("send", lang), key="pending_send", type="primary"):
                text = st.session_state.get("pending_template_input", st.session_state.pending_template) or ""
                text = text.strip()
                if text:
                    if len(text) <= config.MAX_QUERY_LENGTH:
                        _process_prompt(text)
                        st.session_state.pending_template = None
                        if "pending_template_input" in st.session_state:
                            del st.session_state["pending_template_input"]
                        st.session_state.scroll_to_bottom = True
                    else:
                        st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
                st.rerun()
        with col2:
            if st.button(t("cancel", lang), key="pending_cancel"):
                st.session_state.pending_template = None
                if "pending_template_input" in st.session_state:
                    del st.session_state["pending_template_input"]
                st.rerun()
    else:
        query = st.chat_input(t("placeholder", lang))

        if query and query.strip():
            q = query.strip()
            if len(q) > config.MAX_QUERY_LENGTH:
                st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
            else:
                _process_prompt(q)
                st.session_state.scroll_to_bottom = True
            st.rerun()


def _render_sidebar(lang: str, chat_history: list) -> None:
    with st.sidebar:
        st.markdown(f"**{t('sidebar_app_name', lang)}**")
        st.caption(t("sidebar_tagline", lang))
        st.markdown("---")

        with st.expander(t("prompt_guide_title", lang), expanded=False):
            st.markdown(
                f"""
                <div class="prompt-guide">
                <ul style="margin:0.25rem 0;padding-left:1.25rem;font-size:0.875rem;line-height:1.6;color:#475569;">
                <li>{t("prompt_guide_tip1", lang)}</li>
                <li>{t("prompt_guide_tip2", lang)}</li>
                <li>{t("prompt_guide_tip3", lang)}</li>
                <li>{t("prompt_guide_tip4", lang)}</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("---")

        st.markdown(f"**{t('templates_heading', lang)}**")
        st.caption(t("templates_hint", lang))
        template_lang = "en" if lang == "auto" else lang
        for i, tmpl in enumerate(get_templates_for_lang(template_lang)):
            if st.button(
                f"→ {tmpl['label']}",
                key=f"template_{template_lang}_{i}",
                use_container_width=True,
                type="secondary",
            ):
                if len(tmpl["prompt"]) <= config.MAX_QUERY_LENGTH:
                    st.session_state.pending_template = tmpl["prompt"]
                    st.session_state.scroll_to_bottom = True
                else:
                    st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
                st.rerun()
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
