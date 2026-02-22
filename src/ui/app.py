"""
Streamlit Chat Interface for LexAI — AI Legal Reasoning System
"""

import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("LOG_FORMAT", "simple")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore", message=".*(PyTorch|TensorFlow|Flax).*")
warnings.filterwarnings("ignore", category=FutureWarning, module=r"google\.api_core")

import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime as _dt

from src.agent.stream import stream_query_response
from src.config.prompt_templates import get_templates_for_lang, get_workflow_categories
from src.config.settings import ASSISTANT_AVATAR, PAGE_CONFIG, USER_AVATAR, config, validate_env_for_app
from src.config.translations import LANGUAGE_OPTIONS, t
from src.ui.auth import (
    get_current_user_email,
    get_current_user_id,
    is_authenticated,
    render_auth_page,
    sign_out,
    sync_session_to_storage,
    try_restore_from_cookies,
)
from src.ui.chat_pdf_export import generate_chat_pdf
from src.ui.citations import render_assistant_message
from src.ui.conversation_store import delete_conversation, list_conversations, load_conversation, save_conversation
from src.ui.feedback import delete_feedback_for_conversation, render_feedback_buttons
from src.ui.ingestion import render_ingestion_sidebar
from src.ui.suggestions import render_suggestions
from src.utils.chat_helpers import add_message, clear_chat_history, get_chat_history, initialize_chat_history
from src.utils.query_context import resolve_query_with_context
from src.utils.year_llm import interpret_year_reply_sync

_CURRENT_YEAR = _dt.now().year

# ---------------------------------------------------------------------------
#  Theme palettes — Light (default) + Dark
# ---------------------------------------------------------------------------

LIGHT_THEME = {
    "primary": "#1e3a5f",
    "primary_light": "#2d4a73",
    "bg": "#ffffff",
    "surface": "#f8fafc",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "accent": "#2563eb",
    "accent_soft": "rgba(37, 99, 235, 0.12)",
    "sidebar_accent": "#7c3aed",
    "welcome_bg": "linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)",
    "sidebar_bg": "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
    "input_bg": "#f8fafc",
    "shadow": "rgba(0,0,0,0.04)",
}

DARK_THEME = {
    "primary": "#60a5fa",
    "primary_light": "#3b82f6",
    "bg": "#0f172a",
    "surface": "#1e293b",
    "border": "#334155",
    "text": "#e2e8f0",
    "accent": "#60a5fa",
    "accent_soft": "rgba(96, 165, 250, 0.15)",
    "sidebar_accent": "#a78bfa",
    "welcome_bg": "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
    "sidebar_bg": "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
    "input_bg": "#1e293b",
    "shadow": "rgba(0,0,0,0.2)",
}

# Court type options for filter
COURT_TYPE_OPTIONS = {
    "KKO": "supreme_court",
    "KHO": "supreme_administrative_court",
    "CJEU": "cjeu",
    "ECHR": "echr",
    "GC": "general_court",
}

# Legal domain categories
LEGAL_DOMAIN_OPTIONS = [
    "Rikosasia",
    "Siviiliasia",
    "Hallintoasia",
    "Työrikos",
    "Seksuaalirikos",
    "Huumausainerikos",
    "Vahingonkorvaus",
    "Sopimus",
    "Konkurssi",
]


def _get_lang() -> str:
    return st.session_state.get("lang", "en")


def _build_pdf_filename(query: str, prefix: str = "lexai_analysis") -> str:
    """Build a descriptive PDF filename from the user's query."""
    import re
    from datetime import datetime as _dt

    slug = re.sub(r"[^\w\s-]", "", query[:60]).strip().replace(" ", "_")
    slug = re.sub(r"_+", "_", slug).strip("_").lower()
    date_str = _dt.now().strftime("%Y%m%d")
    if slug:
        return f"{prefix}_{slug}_{date_str}.pdf"
    return f"{prefix}_{date_str}.pdf"


def _get_theme() -> dict:
    """Return the active theme palette based on dark mode toggle."""
    if st.session_state.get("dark_mode", False):
        return DARK_THEME
    return LIGHT_THEME


def _inject_scroll_to_bottom() -> None:
    """Scroll the main page to bottom (input area)."""
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


def _inject_toggle_fix() -> None:
    """Force toggle visibility via JS with !important inline styles to beat CSS."""
    is_dark = st.session_state.get("dark_mode", False)
    track_off = "#475569" if is_dark else "#b0bec5"
    track_on = "#60a5fa" if is_dark else "#2563eb"
    thumb_color = "#e2e8f0" if is_dark else "#ffffff"
    components.html(
        f"""
        <script>
        (function() {{
            var doc = window.parent.document;
            function s(el, prop, val) {{ el.style.setProperty(prop, val, 'important'); }}
            function styleToggle(container) {{
                var el = container.querySelector('[role="checkbox"]')
                      || container.querySelector('label > div');
                if (!el) return;
                var on = el.getAttribute('aria-checked') === 'true';
                s(el, 'background', on ? '{track_on}' : '{track_off}');
                s(el, 'background-color', on ? '{track_on}' : '{track_off}');
                s(el, 'border', 'none');
                s(el, 'border-radius', '999px');
                s(el, 'min-width', '46px');
                s(el, 'width', '46px');
                s(el, 'height', '26px');
                s(el, 'position', 'relative');
                s(el, 'cursor', 'pointer');
                s(el, 'display', 'flex');
                s(el, 'align-items', 'center');
                s(el, 'padding', '3px');
                s(el, 'box-sizing', 'border-box');
                var ch = el.children;
                for (var i = 0; i < ch.length; i++) {{
                    s(ch[i], 'background', '{thumb_color}');
                    s(ch[i], 'background-color', '{thumb_color}');
                    s(ch[i], 'border-radius', '50%');
                    s(ch[i], 'width', '20px');
                    s(ch[i], 'height', '20px');
                    s(ch[i], 'min-width', '20px');
                    s(ch[i], 'min-height', '20px');
                    s(ch[i], 'box-shadow', '0 1px 4px rgba(0,0,0,0.4)');
                    s(ch[i], 'flex-shrink', '0');
                    s(ch[i], 'margin-left', on ? 'auto' : '0');
                }}
            }}
            function fixAll() {{
                doc.querySelectorAll('[data-testid="stToggle"]').forEach(styleToggle);
            }}
            fixAll();
            setTimeout(fixAll, 100);
            setTimeout(fixAll, 500);
            new MutationObserver(fixAll).observe(doc.body, {{
                childList: true, subtree: true, attributes: true
            }});
        }})();
        </script>
        """,
        height=0,
    )


def _inject_keyboard_shortcuts() -> None:
    """Inject Ctrl+L (clear chat) and Ctrl+K (focus input) keyboard shortcuts."""
    components.html(
        """
        <script>
        (function() {
            var doc = window.parent.document;
            if (doc._lexai_shortcuts) return;
            doc._lexai_shortcuts = true;
            doc.addEventListener('keydown', function(e) {
                // Ctrl+L: clear chat
                if (e.ctrlKey && e.key === 'l') {
                    e.preventDefault();
                    var clearBtn = doc.querySelectorAll('button');
                    for (var i = 0; i < clearBtn.length; i++) {
                        if (clearBtn[i].textContent.indexOf('Clear') !== -1 ||
                            clearBtn[i].textContent.indexOf('Tyhjenn') !== -1 ||
                            clearBtn[i].textContent.indexOf('Rensa') !== -1) {
                            clearBtn[i].click();
                            break;
                        }
                    }
                }
                // Ctrl+K: focus input
                if (e.ctrlKey && e.key === 'k') {
                    e.preventDefault();
                    var textarea = doc.querySelector('[data-testid="stChatInput"] textarea');
                    if (textarea) textarea.focus();
                }
            });
        })();
        </script>
        """,
        height=0,
    )


def _inject_custom_css() -> None:
    theme = _get_theme()
    is_dark = st.session_state.get("dark_mode", False)

    # Dark mode overrides for Streamlit internals
    dark_overrides = ""
    if is_dark:
        dark_overrides = f"""
            /* ── D1: Root app background ── */
            .stApp {{
                background-color: {theme["bg"]} !important;
                color: {theme["text"]} !important;
            }}

            /* ── D2: Layout wrappers → transparent (inherit dark bg from root) ── */
            .main, .main > div, .main > div > div, .main > div > div > div,
            [data-testid="stAppViewContainer"],
            [data-testid="stAppViewContainer"] > div,
            [data-testid="stAppViewContainer"] > div > div,
            [data-testid="stAppViewContainer"] > div > div > div,
            [data-testid="stMain"],
            [data-testid="stMain"] > div,
            [data-testid="stMainBlockContainer"],
            [data-testid="stMainBlockContainer"] > div,
            .block-container, .block-container > div,
            .block-container > div > div, .block-container > div > div > div,
            [data-testid="stVerticalBlock"],
            [data-testid="stVerticalBlock"] > div,
            [data-testid="stVerticalBlock"] > div > div,
            [data-testid="stVerticalBlockBorderWrapper"],
            [data-testid="stVerticalBlockBorderWrapper"] > div,
            [data-testid="stHorizontalBlock"],
            [data-testid="stHorizontalBlock"] > div,
            [data-testid="stHorizontalBlock"] > div > div,
            div[data-testid="column"],
            div[data-testid="column"] > div,
            div[data-testid="column"] > div > div,
            .element-container,
            .element-container > div,
            .element-container > div > div,
            .stMarkdown, .stMarkdown > div,
            .stButton, .stButton > div,
            header[data-testid="stHeader"],
            [data-testid="stForm"],
            [data-testid="stForm"] > div {{
                background-color: transparent !important;
                background: transparent !important;
            }}
            /* ── D2b: Bottom input bar wrappers ── */
            [data-testid="stBottom"],
            [data-testid="stBottom"] > div,
            [data-testid="stBottom"] > div > div,
            [data-testid="stBottom"] > div > div > div,
            [data-testid="stChatInput"],
            [data-testid="stChatInput"] > div {{
                background: {theme["bg"]} !important;
                background-color: {theme["bg"]} !important;
            }}

            /* ── D3: ALL text → light color ── */
            .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
            .stApp label, .stApp a,
            .stMarkdown, .stMarkdown p, .stMarkdown span,
            .stCaption, .stText,
            [data-testid="stWidgetLabel"],
            [data-testid="stWidgetLabel"] p {{
                color: {theme["text"]} !important;
            }}

            /* ── D4: Sidebar ── */
            [data-testid="stSidebar"] {{
                background: {theme["sidebar_bg"]} !important;
            }}
            [data-testid="stSidebar"] > div,
            [data-testid="stSidebar"] > div > div,
            [data-testid="stSidebar"] > div > div > div,
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div,
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div > div,
            [data-testid="stSidebar"] .element-container,
            [data-testid="stSidebar"] .element-container > div,
            [data-testid="stSidebar"] .element-container > div > div,
            [data-testid="stSidebar"] .stButton,
            [data-testid="stSidebar"] .stButton > div,
            [data-testid="stSidebar"] .stDownloadButton,
            [data-testid="stSidebar"] .stDownloadButton > div {{
                background: transparent !important;
                background-color: transparent !important;
            }}

            /* ── D5: Elements with own background ── */
            [data-testid="stChatMessage"] {{
                background: {theme["surface"]} !important;
            }}
            [data-testid="stChatMessage"] div,
            [data-testid="stChatMessage"] .stMarkdown,
            [data-testid="stChatMessage"] .stMarkdown div,
            [data-testid="stChatMessage"] .element-container,
            [data-testid="stChatMessage"] .element-container div,
            [data-testid="stChatMessage"] [data-testid="stVerticalBlock"],
            [data-testid="stChatMessage"] [data-testid="stVerticalBlock"] div,
            [data-testid="stChatMessage"] [data-testid="stHorizontalBlock"],
            [data-testid="stChatMessage"] [data-testid="stHorizontalBlock"] div,
            [data-testid="stChatMessage"] div[data-testid="column"],
            [data-testid="stChatMessage"] div[data-testid="column"] div {{
                background: transparent !important;
                background-color: transparent !important;
            }}
            /* Download buttons inside chat */
            [data-testid="stChatMessage"] .stDownloadButton,
            [data-testid="stChatMessage"] .stDownloadButton div,
            [data-testid="stChatMessage"] .stButton,
            [data-testid="stChatMessage"] .stButton div {{
                background: transparent !important;
                background-color: transparent !important;
            }}
            .stDownloadButton > button {{
                background: {theme["surface"]} !important;
                color: {theme["text"]} !important;
                border-color: {theme["border"]} !important;
            }}
            .welcome-card {{
                background: {theme["welcome_bg"]} !important;
            }}
            .main-header {{
                background: linear-gradient(135deg, #1e3a5f 0%, #2d4a73 50%, #3d5a80 100%) !important;
            }}
            [data-testid="stExpander"] {{
                background: {theme["surface"]} !important;
                border-color: {theme["border"]} !important;
            }}
            [data-testid="stBottom"] {{
                background: linear-gradient(to top, {theme["bg"]} 0%, {theme["surface"]} 100%) !important;
            }}

            /* ── D6: Buttons ── */
            .stButton > button[kind="secondary"] {{
                background: {theme["surface"]} !important;
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
                border: 1.5px solid {theme["border"]} !important;
            }}
            .stButton > button[kind="secondary"]:hover {{
                background: {theme["accent_soft"]} !important;
                background-color: {theme["accent_soft"]} !important;
                border-color: {theme["accent"]} !important;
            }}
            .stButton > button[kind="primary"] {{
                background: linear-gradient(135deg, {theme["accent"]} 0%, {theme["primary"]} 100%) !important;
            }}
            [data-testid="stFormSubmitButton"] button {{
                background: linear-gradient(135deg, {theme["accent"]} 0%, {theme["primary"]} 100%) !important;
                color: white !important;
            }}

            /* ── D7: Inputs ── */
            [data-testid="stChatInput"] textarea {{
                background: {theme["input_bg"]} !important;
                background-color: {theme["input_bg"]} !important;
                color: {theme["text"]} !important;
            }}
            [data-testid="stTextArea"] textarea, textarea {{
                background: {theme["input_bg"]} !important;
                background-color: {theme["input_bg"]} !important;
                color: {theme["text"]} !important;
                -webkit-text-fill-color: {theme["text"]} !important;
            }}

            /* ── D8: Selectbox / Dropdowns — fully styled ── */
            [data-testid="stSelectbox"] {{
                background: transparent !important;
            }}
            [data-testid="stSelectbox"] > div,
            [data-testid="stSelectbox"] > div > div,
            [data-testid="stSelectbox"] div[data-baseweb],
            [data-testid="stSelectbox"] div[data-baseweb] > div {{
                background: {theme["surface"]} !important;
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
                border-color: {theme["border"]} !important;
            }}
            [data-testid="stSelectbox"] input {{
                color: {theme["text"]} !important;
                -webkit-text-fill-color: {theme["text"]} !important;
            }}
            [data-testid="stSelectbox"] svg {{
                fill: {theme["text"]} !important;
            }}
            [data-testid="stSelectbox"] span {{
                color: {theme["text"]} !important;
            }}
            /* Dropdown popup (renders as portal outside widget tree) */
            [role="listbox"],
            [role="listbox"] > div,
            [data-baseweb="popover"],
            [data-baseweb="popover"] > div,
            [data-baseweb="popover"] > div > div,
            [data-baseweb="menu"],
            [data-baseweb="menu"] > div,
            ul[role="listbox"],
            ul[role="listbox"] > li {{
                background-color: {theme["surface"]} !important;
                background: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            [role="option"] {{
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            [role="option"]:hover, [role="option"][aria-selected="true"] {{
                background-color: {theme["accent_soft"]} !important;
            }}

            /* ── D9: Send button in chat input ── */
            [data-testid="stChatInput"] button {{
                background: linear-gradient(135deg, {theme["accent"]} 0%, {theme["primary"]} 100%) !important;
            }}

            /* ── D10: Forms, expanders, and tabs ── */
            .stForm, .stForm > div {{
                background: {theme["bg"]} !important;
                background-color: {theme["bg"]} !important;
            }}
            [data-testid="stExpander"] summary {{
                color: {theme["text"]} !important;
            }}
            [data-testid="stExpander"] > div > div {{
                background: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            .stTabs, .stTabs > div,
            [data-baseweb="tab-list"],
            [data-baseweb="tab-panel"] {{
                background: {theme["bg"]} !important;
                background-color: {theme["bg"]} !important;
            }}
            [data-baseweb="tab"] {{
                color: {theme["text"]} !important;
            }}

            /* ── D11: Remaining white-bg widgets ── */
            .stMultiSelect, .stMultiSelect > div,
            .stMultiSelect > div > div,
            .stTextInput > div > div > input,
            .stNumberInput > div > div > input {{
                background: {theme["input_bg"]} !important;
                background-color: {theme["input_bg"]} !important;
                color: {theme["text"]} !important;
            }}
            .stRadio > div[role="radiogroup"] {{
                background: {theme["surface"]} !important;
            }}
            .stCheckbox label span {{
                color: {theme["text"]} !important;
            }}

            /* ── D12: Code blocks and markdown containers ── */
            .stCodeBlock, pre, code {{
                background: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            .stAlert {{
                background: {theme["surface"]} !important;
            }}

            /* ── D13: File uploader, drag-drop zone ── */
            .stFileUploader, .stFileUploader > div,
            .stFileUploader section,
            .stFileUploader [data-testid="stFileUploaderDropzone"] {{
                background: {theme["surface"]} !important;
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
                border: 1.5px solid {theme["border"]} !important;
                border-radius: 10px !important;
            }}
            .stFileUploader label,
            .stFileUploader small,
            .stFileUploader span {{
                color: {theme["text"]} !important;
            }}
            .stFileUploader button {{
                background: {theme["surface"]} !important;
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
                border: 1.5px solid {theme["border"]} !important;
                border-radius: 8px !important;
            }}
            .stFileUploader button:hover {{
                border-color: {theme["accent"]} !important;
                background: {theme["accent_soft"]} !important;
            }}

            /* ── D14: Tabs (main + sidebar ingestion) ── */
            .stTabs > div,
            [data-baseweb="tab-list"],
            [data-baseweb="tab-panel"],
            [data-baseweb="tab-panel"] > div {{
                background: transparent !important;
                background-color: transparent !important;
            }}
            [data-baseweb="tab"] {{
                color: {theme["text"]} !important;
                background: transparent !important;
            }}
            [data-baseweb="tab"][aria-selected="true"] {{
                color: {theme["accent"]} !important;
            }}

            /* ── D15: Text input wrappers only (not buttons) ── */
            .stTextInput > div,
            .stTextInput > div > div {{
                background: transparent !important;
                background-color: transparent !important;
            }}

            /* ── D16: Catch remaining white-bg wrapper divs ── */
            [data-testid="stMainBlockContainer"],
            [data-testid="stMain"],
            [data-testid="stMainBlockContainer"] > div {{
                background: {theme["bg"]} !important;
                background-color: {theme["bg"]} !important;
            }}
        """

    st.markdown(
        f"""
        <style>
            {dark_overrides}

            /* ── Base layout ─────────────────────────────────── */
            .block-container {{
                max-width: min(1100px, 100vw);
                margin: 0 auto;
                padding: 1.25rem 1rem 6rem 1rem;
            }}

            /* ── Chat bubbles ────────────────────────────────── */
            [data-testid="stChatMessage"] {{
                padding: 0.875rem 1rem;
                border-radius: 14px;
                margin-bottom: 0.625rem;
                border: 1px solid {theme["border"]};
                border-left: 4px solid {theme["accent"]};
                background: {theme["surface"]} !important;
                transition: box-shadow 0.2s ease;
                min-height: 8rem;
            }}
            [data-testid="stChatMessage"]:hover {{
                box-shadow: 0 2px 12px {theme["accent_soft"]};
            }}
            [data-testid="stChatMessage"] p {{
                font-size: 0.9375rem;
                line-height: 1.65;
                color: {theme["text"]};
            }}

            /* ── Sticky bottom input bar ─────────────────────── */
            [data-testid="stBottom"] {{
                background: linear-gradient(to top, {theme["bg"]} 0%, {theme["surface"]} 100%) !important;
                border-top: 1px solid {theme["border"]} !important;
                padding: 0.5rem 0.75rem !important;
                box-shadow: 0 -4px 12px {theme["shadow"]};
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
                border: 2px solid {theme["border"]} !important;
                background: {theme["input_bg"]} !important;
                color: {theme["text"]} !important;
                font-size: 1rem !important;
                line-height: 1.5 !important;
                resize: none !important;
                transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
            }}
            [data-testid="stChatInput"] textarea:focus {{
                border-color: {theme["accent"]} !important;
                box-shadow: 0 0 0 4px {theme["accent_soft"]} !important;
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
                background: linear-gradient(135deg, {theme["accent"]} 0%, {theme["primary"]} 100%) !important;
                border: none !important;
                transition: transform 0.15s ease, box-shadow 0.2s ease !important;
            }}
            [data-testid="stChatInput"] button:hover {{
                transform: scale(1.08) !important;
                box-shadow: 0 4px 12px {theme["accent_soft"]} !important;
            }}
            [data-testid="stChatInput"] button svg {{
                fill: white !important;
            }}

            /* ── Primary buttons ─────────────────────────────── */
            .stButton > button[kind="primary"] {{
                background: linear-gradient(135deg, {theme["accent"]} 0%, {theme["primary"]} 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 10px !important;
                padding: 0.5rem 1.25rem !important;
                font-weight: 600 !important;
                transition: transform 0.15s ease, box-shadow 0.2s ease !important;
            }}
            .stButton > button[kind="primary"]:hover {{
                transform: translateY(-1px);
                box-shadow: 0 4px 12px {theme["accent_soft"]} !important;
            }}

            /* ── Secondary / template buttons ──────────────────── */
            .stButton > button[kind="secondary"] {{
                border-radius: 10px !important;
                border: 1.5px solid {theme["border"]} !important;
                color: {theme["text"]} !important;
                transition: all 0.2s ease !important;
            }}
            .stButton > button[kind="secondary"]:hover {{
                transform: translateY(-2px) !important;
                box-shadow: 0 4px 12px rgba(124, 58, 237, 0.15) !important;
                border-color: {theme["sidebar_accent"]} !important;
                background: rgba(124, 58, 237, 0.06) !important;
            }}

            /* ── Header banner ───────────────────────────────── */
            .main-header {{
                background: linear-gradient(135deg, #1e3a5f 0%, #2d4a73 50%, #3d5a80 100%);
                padding: 1.25rem 1.5rem;
                border-radius: 14px;
                margin-bottom: 0.875rem;
                box-shadow: 0 4px 16px rgba(30, 58, 95, 0.2);
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}
            .main-header .logo-icon {{
                width: 36px;
                height: 36px;
                flex-shrink: 0;
            }}
            .main-header .header-text h1 {{
                color: white;
                margin: 0;
                font-size: 1.3125rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            }}
            .main-header .header-text .subtitle {{
                color: rgba(255,255,255,0.92);
                margin: 0.35rem 0 0 0;
                font-size: 0.875rem;
                line-height: 1.45;
            }}
            .main-header .header-user {{
                margin-left: auto;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                flex-shrink: 0;
            }}
            .header-user-email {{
                color: rgba(255,255,255,0.85);
                font-size: 0.8rem;
                font-weight: 500;
                background: rgba(255,255,255,0.12);
                padding: 0.3rem 0.75rem;
                border-radius: 20px;
                white-space: nowrap;
                letter-spacing: 0.01em;
            }}

            /* ── Welcome card ────────────────────────────────── */
            .welcome-card {{
                background: {theme["welcome_bg"]};
                border: 1px solid {theme["border"]};
                border-left: 4px solid {theme["accent"]};
                border-radius: 14px;
                padding: 1.375rem 1.5rem 1.125rem;
                margin-bottom: 0.875rem;
                box-shadow: 0 2px 8px {theme["accent_soft"]};
            }}
            .welcome-card strong {{ font-size: 1.0625rem; color: {theme["primary"]}; }}
            .welcome-card p {{ color: {theme["text"]}; font-size: 0.9375rem; line-height: 1.65; margin: 0.5rem 0 0 0; }}

            /* ── Quick-start template section ─────────────────── */
            .templates-section {{ margin-top: 0.5rem; }}

            /* ── Sidebar ─────────────────────────────────────── */
            [data-testid="stSidebar"] {{
                background: {theme["sidebar_bg"]};
                border-right: 1px solid {theme["border"]};
            }}
            [data-testid="stSidebar"] > div {{
                padding-top: 0.75rem;
            }}
            [data-testid="stSidebar"] .stMarkdown strong {{
                color: {theme["primary"]};
            }}
            [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] .stMarkdown p {{
                color: {theme["text"]};
            }}

            /* ── Selectbox styling ───────────────────────────── */
            [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
                border-radius: 8px;
            }}

            /* ── Dropdown popup — always readable in both modes ── */
            [role="listbox"],
            [role="listbox"] > div,
            [data-baseweb="popover"],
            [data-baseweb="popover"] > div,
            [data-baseweb="popover"] > div > div,
            [data-baseweb="menu"],
            [data-baseweb="menu"] > div,
            ul[role="listbox"],
            ul[role="listbox"] > li {{
                background-color: {theme["surface"]} !important;
                background: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            [role="option"] {{
                background-color: {theme["surface"]} !important;
                color: {theme["text"]} !important;
            }}
            [role="option"]:hover,
            [role="option"][aria-selected="true"] {{
                background-color: {theme["accent_soft"]} !important;
                color: {theme["text"]} !important;
            }}

            /* ── Typing indicator animation ──────────────────── */
            @keyframes typing-dots {{
                0%, 80%, 100% {{ opacity: 0; }}
                40% {{ opacity: 1; }}
            }}
            .typing-dot {{
                display: inline-block;
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: {theme["accent"]};
                margin: 0 2px;
                animation: typing-dots 1.4s infinite ease-in-out both;
            }}
            .typing-dot:nth-child(1) {{ animation-delay: -0.32s; }}
            .typing-dot:nth-child(2) {{ animation-delay: -0.16s; }}
            .typing-dot:nth-child(3) {{ animation-delay: 0s; }}

            /* ── Mobile (< 640px) ────────────────────────────── */
            @media (max-width: 640px) {{
                .block-container {{ padding: 0.75rem 0.5rem 5rem 0.5rem; }}
                .main-header {{
                    padding: 1rem 1.125rem;
                    border-radius: 12px;
                    margin-bottom: 0.625rem;
                    flex-wrap: wrap;
                }}
                .header-user-email {{
                    font-size: 0.7rem;
                    padding: 0.2rem 0.5rem;
                }}
                .main-header .header-text h1 {{ font-size: 1.125rem; }}
                .main-header .header-text .subtitle {{ font-size: 0.8125rem; }}
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
                [data-testid="stChatMessage"] p {{ font-size: 0.875rem; }}
                .welcome-card {{ padding: 1.125rem 1rem; border-radius: 12px; }}
            }}

            /* ── Tablet+ (>= 768px) ─────────────────────────── */
            @media (min-width: 768px) {{
                .block-container {{ padding: 1.5rem 1.25rem 6rem 1.25rem; }}
            }}

            /* ── Desktop (>= 1024px) ────────────────────────── */
            @media (min-width: 1024px) {{
                .block-container {{ max-width: min(1100px, 90vw); }}
            }}

            /* ── Toggle switch — visible thumb in both modes ──── */
            [data-testid="stToggle"] label > div,
            [data-testid="stToggle"] [role="checkbox"],
            [data-testid="stToggle"] button {{
                background-color: {"#b0bec5" if not is_dark else "#475569"} !important;
                border: none !important;
                border-radius: 999px !important;
                min-width: 46px !important;
                width: 46px !important;
                height: 26px !important;
                position: relative !important;
                cursor: pointer !important;
                transition: background-color 0.2s ease !important;
            }}
            [data-testid="stToggle"] [aria-checked="true"],
            [data-testid="stToggle"] label > div[aria-checked="true"],
            [data-testid="stToggle"] button[aria-checked="true"] {{
                background-color: {theme["accent"]} !important;
            }}
            [data-testid="stToggle"] [role="checkbox"] > div,
            [data-testid="stToggle"] [role="checkbox"] > div > div,
            [data-testid="stToggle"] [role="checkbox"] span,
            [data-testid="stToggle"] label > div > div,
            [data-testid="stToggle"] label > div > div > div,
            [data-testid="stToggle"] label > div > span,
            [data-testid="stToggle"] button > div,
            [data-testid="stToggle"] button > div > div,
            [data-testid="stToggle"] button > span {{
                background: {"#e2e8f0" if is_dark else "#ffffff"} !important;
                background-color: {"#e2e8f0" if is_dark else "#ffffff"} !important;
                border-radius: 50% !important;
                width: 20px !important;
                height: 20px !important;
                min-width: 20px !important;
                min-height: 20px !important;
                box-shadow: 0 1px 4px rgba(0,0,0,0.35) !important;
            }}

            /* ── Sidebar caption readability ─────────────────── */
            [data-testid="stSidebar"] .stCaption {{
                opacity: 0.85 !important;
            }}

            /* ── Hide Streamlit branding ─────────────────────── */
            #MainMenu {{ visibility: hidden; }}
            footer {{ visibility: hidden; }}
            header[data-testid="stHeader"] {{ background: transparent; }}
        </style>
    """,
        unsafe_allow_html=True,
    )


def _render_workflow_cards(lang: str) -> None:
    """Show categorized workflow cards on the welcome screen."""
    template_lang = "en" if lang == "auto" else lang
    categories = get_workflow_categories(template_lang)
    if not categories:
        return

    theme = _get_theme()
    text_color = theme.get("text", "#0f172a")

    st.markdown(f"**{t('workflow_heading', lang)}**")

    for cat_idx, cat in enumerate(categories):
        st.markdown(
            f"<div style='margin-top:0.75rem;font-size:0.95rem;font-weight:600;"
            f"color:{text_color};'>{cat['icon']} {cat['category']}</div>",
            unsafe_allow_html=True,
        )
        templates = cat.get("templates", [])
        cols = st.columns(2)
        for i, tmpl in enumerate(templates):
            with cols[i % 2]:
                if st.button(
                    tmpl["label"],
                    key=f"wf_{template_lang}_{cat_idx}_{i}",
                    use_container_width=True,
                    type="secondary",
                    help=tmpl.get("description", ""),
                ):
                    if len(tmpl["prompt"]) <= config.MAX_QUERY_LENGTH:
                        st.session_state.pending_template = tmpl["prompt"]
                        st.session_state.scroll_to_bottom = True
                    else:
                        st.error(t("query_too_long", lang, max=config.MAX_QUERY_LENGTH))
                    st.rerun()


def _render_action_buttons(response: str, original_query: str, lang: str, message_idx: int) -> None:
    """Render Regenerate and Contrary Authority buttons below an assistant message."""
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button(
            f"\U0001f504 {t('regenerate', lang)}",
            key=f"regen_{message_idx}",
            type="secondary",
            use_container_width=True,
        ):
            # Remove last user+assistant pair and re-run with same query
            chat_history = get_chat_history()
            if len(chat_history) >= 2:
                # Pop the last assistant and user messages
                chat_history.pop()  # assistant
                chat_history.pop()  # user
                st.session_state.messages = chat_history
            st.session_state.regenerate_query = original_query
            st.rerun()
    with col2:
        if st.button(
            f"\u2696\ufe0f {t('contrary_authority', lang)}",
            key=f"contrary_{message_idx}",
            type="secondary",
            use_container_width=True,
        ):
            contrary_prompt = f"{original_query}\n\n{t('contrary_instruction', lang)}"
            st.session_state.pending_template = contrary_prompt
            st.session_state.scroll_to_bottom = True
            st.rerun()


def _is_year_clarification_message(msg: str, lang: str) -> bool:
    """True if msg is (or contains) the year clarification question (any language)."""
    content = (msg or "").strip()
    return any(t("year_clarification", code).strip() in content for code in ("en", "fi", "sv"))


_CLARIFICATION_MARKERS = (
    "clarif",
    "which years",
    "what specific",
    "could you",
    "please clarify",
    "tarkentaa",
    "förtydliga",
    "tarkenna",
    "vilka år",
    "miltä vuosi",
)


def _is_clarification_response(msg: str, lang: str) -> bool:
    """True if the assistant message is a clarification question, not a substantive answer."""
    if _is_year_clarification_message(msg, lang):
        return True
    content = (msg or "").strip().lower()
    if not content:
        return False
    short_with_question_mark = len(content) < 180 and "?" in content
    has_clarification_marker = any(m in content for m in _CLARIFICATION_MARKERS)
    return short_with_question_mark or has_clarification_marker


def _get_sidebar_filters() -> dict:
    """Read current sidebar filter values from session state."""
    filters = {}
    if st.session_state.get("filters_enabled", False):
        yr = st.session_state.get("filter_year_range")
        if yr and isinstance(yr, (list, tuple)) and len(yr) == 2:
            filters["year_range"] = (yr[0], yr[1])
        courts = st.session_state.get("filter_court_types")
        if courts:
            filters["court_types"] = list(courts)
        domains = st.session_state.get("filter_legal_domains")
        if domains:
            filters["legal_domains"] = list(domains)
    return filters


def _looks_like_year_reply(text: str) -> bool:
    """True if the user's message is a year-range answer or 'all', not a legal question."""
    stripped = text.strip().lower()
    _year_reply_markers = (
        "all",
        "all years",
        "any year",
        "no filter",
        "every year",
        "kaikki",
        "kaikki vuodet",
        "ei rajoitusta",
        "alla",
        "alla år",
        "allt",
    )
    if stripped in _year_reply_markers:
        return True
    from src.utils.year_filter import extract_year_range

    yr = extract_year_range(text)
    return bool(yr[0] is not None and len(stripped) < 40)


def _find_original_legal_question(chat_history: list[dict]) -> str | None:
    """Walk backwards through chat history to find the most recent user legal question."""
    for i in range(len(chat_history) - 1, -1, -1):
        msg = chat_history[i]
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if _looks_like_year_reply(content):
            continue
        if len(content) > 10:
            return content
    return None


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

    if original_query is None and _looks_like_year_reply(prompt):
        legal_question = _find_original_legal_question(chat_history)
        if legal_question:
            original_query = legal_question
            year_range = interpret_year_reply_sync(prompt)

    if original_query is None:
        effective_query, ctx_year = resolve_query_with_context(prompt, chat_history)
        if ctx_year is not None or effective_query != prompt:
            original_query = effective_query
            year_range = ctx_year

    # Get sidebar filters
    filters = _get_sidebar_filters()
    court_types = filters.get("court_types")
    legal_domains = filters.get("legal_domains")
    tenant_id = st.session_state.get("tenant_id")

    # Override year range from filters if set and no year clarification in progress
    if original_query is None and "year_range" in filters:
        yr_filter = filters["year_range"]
        if yr_filter[0] != 1926 or yr_filter[1] != _CURRENT_YEAR:
            year_range = yr_filter
            original_query = prompt

    add_message("user", prompt)
    msg_idx = len(get_chat_history())  # index for the upcoming assistant message

    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(prompt)

    # Typing indicator
    typing_placeholder = st.empty()
    typing_placeholder.markdown(
        f'<div style="padding: 0.5rem;"><span class="typing-dot"></span>'
        f'<span class="typing-dot"></span><span class="typing-dot"></span> '
        f"{t('typing_indicator', lang)}...</div>",
        unsafe_allow_html=True,
    )

    metadata_sink: dict = {}

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR), st.spinner(t("spinner_searching", lang)):
        typing_placeholder.empty()
        if original_query:
            yr = year_range if year_range is not None else (None, None)
            response = st.write_stream(
                stream_query_response(
                    prompt,
                    lang=lang,
                    original_query_for_year=original_query,
                    year_range=yr,
                    chat_history=chat_history,
                    court_types=court_types,
                    legal_domains=legal_domains,
                    tenant_id=tenant_id,
                    metadata_sink=metadata_sink,
                )
            )
        else:
            response = st.write_stream(
                stream_query_response(
                    prompt,
                    lang=lang,
                    chat_history=chat_history,
                    court_types=court_types,
                    legal_domains=legal_domains,
                    tenant_id=tenant_id,
                    metadata_sink=metadata_sink,
                )
            )
    add_message("assistant", response)

    # Store metadata for UI components (confidence badge, enriched source cards)
    if metadata_sink:
        st.session_state[f"msg_metadata_{msg_idx}"] = metadata_sink

    # Auto-save conversation
    _auto_save_conversation(lang)


def _auto_save_conversation(lang: str) -> None:
    """Auto-save current conversation to Supabase after each exchange."""
    messages = get_chat_history()
    if not messages:
        return
    conv_id = st.session_state.get("current_conversation_id")
    new_id = save_conversation(messages, lang, conversation_id=conv_id)
    if new_id:
        st.session_state.current_conversation_id = new_id


def _handle_oauth_callback() -> None:
    """Check query params for an OAuth callback and exchange the code for tokens."""
    code = st.query_params.get("code")
    state = st.query_params.get("state")  # "google_drive" or "onedrive"
    if not code or not state:
        return

    tenant_id = st.session_state.get("tenant_id")
    if not tenant_id:
        st.query_params.clear()
        return

    provider = state  # state param carries the provider name
    redirect_uri = st.session_state.get("oauth_redirect_uri", config.APP_BASE_URL)

    try:
        # Get the right connector and exchange code
        if provider == "google_drive":
            from src.services.drive.google_connector import GoogleDriveConnector

            connector = GoogleDriveConnector()
        elif provider == "onedrive":
            from src.services.drive.onedrive_connector import OneDriveConnector

            connector = OneDriveConnector()
        else:
            st.query_params.clear()
            return

        tokens = connector.exchange_code(code, redirect_uri)

        # Persist to database
        from src.services.drive.drive_settings import DriveSettingsService

        settings = DriveSettingsService()
        settings.save_connection(
            tenant_id=tenant_id,
            provider=provider,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            token_expiry=tokens.get("expires_in", 3600),
        )

        # Store in session state for immediate use
        token_key = "gdrive_access_token" if provider == "google_drive" else "onedrive_access_token"
        st.session_state[token_key] = tokens["access_token"]

        st.query_params.clear()
        st.toast(t("drive_connected", _get_lang()), icon="\u2705")
    except Exception as e:
        st.query_params.clear()
        st.error(f"OAuth error: {e}")


def main():
    validate_env_for_app()

    if "lang" not in st.session_state:
        st.session_state.lang = "fi"
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False

    # Restore session from cookies BEFORE rendering anything (no flash)
    if not is_authenticated():
        try_restore_from_cookies()

    # Auth gate: show login page if not authenticated
    if not is_authenticated():
        render_auth_page(st.session_state.lang)
        return

    # Page config must be the first Streamlit render command in the auth path.
    lang = _get_lang()
    st.set_page_config(
        page_title=t("page_title", lang),
        page_icon=PAGE_CONFIG["page_icon"],
        layout=PAGE_CONFIG["layout"],
        initial_sidebar_state=PAGE_CONFIG["initial_sidebar_state"],
    )

    # Set user_id and tenant_id from authenticated user
    user_id = get_current_user_id()
    st.session_state.user_id = user_id
    if "tenant_id" not in st.session_state or st.session_state.tenant_id is None:
        st.session_state.tenant_id = user_id

    # Persist session tokens to cookies + localStorage (survives page reloads)
    sync_session_to_storage()

    # Strip auth tokens from URL so they never stay visible in the address bar
    _token_params = {"access_token", "refresh_token", "expires_at", "expires_in", "token_type", "type", "_sat", "_srt"}
    if _token_params & set(st.query_params.keys()):
        st.query_params.clear()

    # Handle OAuth callback before any rendering (Drive/OneDrive)
    _handle_oauth_callback()

    _inject_custom_css()
    _inject_toggle_fix()
    _inject_keyboard_shortcuts()

    # Clean up any auth hash fragment that might still be in the address bar.
    # Also start an idle-session timer: when the cookie expires (SESSION_LIFETIME_SECONDS)
    # the page reloads automatically so the user gets the sign-in screen
    # without having to manually refresh.
    from src.ui.auth import SESSION_LIFETIME_SECONDS as _SLT

    components.html(
        "<script>"
        "if(window.parent.location.hash.indexOf('access_token')!==-1)"
        "{window.parent.history.replaceState(null,'',window.parent.location.pathname)}"
        "if(!window.parent._lexaiIdleTimer){"
        f"window.parent._lexaiIdleTimer=setTimeout(function(){{try{{window.parent.location.reload()}}catch(e){{}}}},{_SLT * 1000});"
        "window.parent.addEventListener('click',function(){"
        "clearTimeout(window.parent._lexaiIdleTimer);"
        f"window.parent._lexaiIdleTimer=setTimeout(function(){{try{{window.parent.location.reload()}}catch(e){{}}}},{_SLT * 1000})"
        "})}"
        "</script>",
        height=0,
    )

    # LexAI branded header with scales icon + user email top-right
    import html as _html

    user_email = get_current_user_email() or ""
    escaped_email = _html.escape(user_email)
    st.markdown(
        f"""
        <div class="main-header">
            <svg class="logo-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                      stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="header-text">
                <h1>{t("sidebar_app_name", lang)} — {t("header_title", lang)}</h1>
                <p class="subtitle">{t("header_subtitle", lang)}</p>
            </div>
            <div class="header-user">
                <span class="header-user-email">{escaped_email}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Language selector in main page (top-right aligned)
    def _on_main_lang_change():
        label = st.session_state.main_lang_selector
        st.session_state.lang = LANGUAGE_OPTIONS.get(label, st.session_state.lang)

    lang_labels = list(LANGUAGE_OPTIONS.keys())
    lang_values = list(LANGUAGE_OPTIONS.values())
    current_idx = lang_values.index(lang) if lang in lang_values else 0
    cols = st.columns([5, 1])
    with cols[1]:
        st.selectbox(
            t("language", lang),
            lang_labels,
            index=current_idx,
            key="main_lang_selector",
            label_visibility="collapsed",
            on_change=_on_main_lang_change,
        )

    if "pending_template" not in st.session_state:
        st.session_state.pending_template = None
    if "scroll_to_bottom" not in st.session_state:
        st.session_state.scroll_to_bottom = False

    initialize_chat_history()
    chat_history = get_chat_history()

    # Handle regeneration trigger
    if st.session_state.get("regenerate_query"):
        regen_query = st.session_state.pop("regenerate_query")
        _process_prompt(regen_query)
        st.session_state.scroll_to_bottom = True
        st.rerun()

    _render_chat_or_welcome(chat_history, lang)
    _render_input_area(lang)

    if st.session_state.scroll_to_bottom:
        _inject_scroll_to_bottom()
        st.session_state.scroll_to_bottom = False

    _render_sidebar(lang, chat_history)


def _render_chat_or_welcome(chat_history: list, lang: str) -> None:
    if chat_history:
        last_user_query = ""
        theme = _get_theme()
        for idx, message in enumerate(chat_history):
            is_last_assistant = message["role"] == "assistant" and idx == len(chat_history) - 1
            avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
            with st.chat_message(message["role"], avatar=avatar):
                if message["role"] == "user":
                    st.write(message["content"])
                    last_user_query = message["content"]
                elif is_last_assistant:
                    # Last assistant message: answer on left, source panel on right
                    from src.ui.citations import _render_source_cards, parse_response_and_sources

                    col_answer, col_sources = st.columns([3, 1])
                    with col_answer:
                        render_assistant_message(message["content"], lang, idx, theme=theme, render_sources=False)
                        _render_action_buttons(message["content"], last_user_query, lang, idx)
                    with col_sources:
                        _, sources = parse_response_and_sources(message["content"])
                        _render_source_cards(sources, idx, lang, theme)

                    if not _is_clarification_response(message["content"], lang):
                        response_pdf = generate_chat_pdf(
                            [
                                {"role": "user", "content": last_user_query},
                                {"role": "assistant", "content": message["content"]},
                            ],
                            title=t("export_pdf_title", lang),
                        )
                        pdf_filename = _build_pdf_filename(last_user_query)
                        st.download_button(
                            label=f"\U0001f4e5 {t('export_pdf', lang)}",
                            data=response_pdf,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            key=f"dl_pdf_{idx}",
                        )

                    render_feedback_buttons(message["content"], last_user_query, lang, idx)
                else:
                    # Older assistant messages: sources inline below
                    render_assistant_message(message["content"], lang, idx, theme=theme)

                    # Feedback buttons for all assistant messages
                    render_feedback_buttons(message["content"], last_user_query, lang, idx)

            # Related questions only for the LAST assistant message
            if is_last_assistant and last_user_query:
                render_suggestions(last_user_query, message["content"], lang, idx)
    else:
        st.markdown(
            f"""<div class="welcome-card">
                <strong>{t("welcome_title", lang)}</strong>
                <p>{t("welcome_body", lang)}</p>
            </div>""",
            unsafe_allow_html=True,
        )
        _render_workflow_cards(lang)


def _render_input_area(lang: str) -> None:
    if st.session_state.pending_template is not None:
        st.text_area(
            t("edit_template_label", lang),
            value=st.session_state.pending_template,
            height=120,
            key="pending_template_input",
            max_chars=config.MAX_QUERY_LENGTH,
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


def _render_sidebar_filters(lang: str) -> None:
    """Render search filter controls in the sidebar."""
    filters_enabled = st.toggle(
        t("filters_toggle", lang),
        value=st.session_state.get("filters_enabled", False),
        key="filters_toggle_key",
    )
    st.session_state.filters_enabled = filters_enabled

    if not filters_enabled:
        return

    st.markdown(f"**{t('filters_heading', lang)}**")
    st.slider(
        t("filter_year_range", lang),
        min_value=1926,
        max_value=_CURRENT_YEAR,
        value=st.session_state.get("filter_year_range", (1926, _CURRENT_YEAR)),
        key="filter_year_range",
    )
    st.multiselect(
        t("filter_court_type", lang),
        options=list(COURT_TYPE_OPTIONS.keys()),
        default=st.session_state.get("filter_court_types", []),
        key="filter_court_types",
    )
    st.multiselect(
        t("filter_legal_domain", lang),
        options=LEGAL_DOMAIN_OPTIONS,
        default=st.session_state.get("filter_legal_domains", []),
        key="filter_legal_domains",
    )


def _render_sidebar_conversations(lang: str) -> None:
    """Render conversation history list in the sidebar."""
    st.markdown(f"**{t('conversations_heading', lang)}**")
    conversations = list_conversations(limit=10)
    if not conversations:
        st.caption(t("no_conversations", lang))
        return

    for conv in conversations:
        conv_id = conv["id"]
        conv_title = conv.get("title", "Untitled")[:50]
        col_load, col_del = st.columns([3, 1])
        with col_load:
            if st.button(
                f"\U0001f4ac {conv_title}",
                key=f"load_conv_{conv_id}",
                use_container_width=True,
            ):
                loaded = load_conversation(conv_id)
                if loaded:
                    st.session_state.messages = loaded
                    st.session_state.current_conversation_id = conv_id
                    _clear_session_caches()
                    st.rerun()
        with col_del:
            if st.button("\U0001f5d1\ufe0f", key=f"del_conv_{conv_id}", help=t("delete", lang)):
                delete_feedback_for_conversation(conv_id)
                delete_conversation(conv_id)
                if st.session_state.get("current_conversation_id") == conv_id:
                    st.session_state.current_conversation_id = None
                    clear_chat_history()
                    _clear_session_caches()
                st.rerun()


def _clear_session_caches() -> None:
    """Clear suggestion, feedback, and metadata caches from session state."""
    keys_to_clear = [k for k in st.session_state if k.startswith(("suggestions_", "feedback_", "msg_metadata_"))]
    for k in keys_to_clear:
        del st.session_state[k]


def _render_sidebar_chat_actions(lang: str, chat_history: list) -> None:
    """Render PDF export, clear-chat, and new-conversation buttons."""
    if chat_history:
        first_user_query = next(
            (m["content"] for m in chat_history if m.get("role") == "user" and m.get("content")),
            "",
        )
        pdf_bytes = generate_chat_pdf(chat_history, title=t("export_pdf_title", lang))
        sidebar_pdf_name = _build_pdf_filename(first_user_query, prefix="lexai_chat")
        st.download_button(
            label=f"\U0001f4e5 {t('export_pdf', lang)}",
            data=pdf_bytes,
            file_name=sidebar_pdf_name,
            mime="application/pdf",
            use_container_width=True,
        )

    if st.button(t("clear_chat", lang), use_container_width=True, type="secondary"):
        clear_chat_history()
        st.session_state.current_conversation_id = None
        _clear_session_caches()
        st.rerun()

    if chat_history and st.button(f"\u2795 {t('new_conversation', lang)}", use_container_width=True, type="secondary"):
        clear_chat_history()
        st.session_state.current_conversation_id = None
        _clear_session_caches()
        st.rerun()


def _render_sidebar(lang: str, chat_history: list) -> None:
    with st.sidebar:
        st.markdown(f"**\u2696\ufe0f {t('sidebar_app_name', lang)}**")
        st.caption(t("sidebar_tagline", lang))

        user_email = get_current_user_email()
        if user_email:
            st.caption(t("auth_welcome_user", lang, email=user_email))
            if st.button(t("auth_logout", lang), key="logout_btn", use_container_width=True, type="secondary"):
                sign_out()
                st.rerun()
        st.markdown("---")

        dark_mode = st.toggle(
            t("dark_mode", lang),
            value=st.session_state.get("dark_mode", False),
            key="dark_mode_toggle",
        )
        if dark_mode != st.session_state.get("dark_mode", False):
            st.session_state.dark_mode = dark_mode
            st.rerun()

        verbose_mode = st.toggle(
            t("verbose_mode", lang),
            value=st.session_state.get("verbose_mode", False),
            key="verbose_mode_toggle",
        )
        if verbose_mode != st.session_state.get("verbose_mode", False):
            st.session_state.verbose_mode = verbose_mode
            st.rerun()

        st.markdown("---")

        st.markdown(f"**{t('templates_heading', lang)}**")
        st.caption(t("templates_hint", lang))
        template_lang = "en" if lang == "auto" else lang
        for i, tmpl in enumerate(get_templates_for_lang(template_lang)):
            if st.button(
                f"\u2192 {tmpl['label']}",
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

        render_ingestion_sidebar(lang, st.session_state.get("tenant_id"))
        _render_sidebar_filters(lang)
        st.markdown("---")

        st.markdown("---")

        _render_sidebar_chat_actions(lang, chat_history)

        st.markdown("---")
        _render_sidebar_conversations(lang)

        st.markdown("---")
        with st.expander(f"\u2328\ufe0f {t('shortcuts_heading', lang)}", expanded=False):
            st.caption(t("shortcut_clear", lang))
            st.caption(t("shortcut_focus", lang))

        st.markdown("---")
        user_count = sum(1 for m in chat_history if m.get("role") == "user")
        st.caption(t("messages_count", lang, count=user_count))
        st.caption(t("input_hint", lang))


if __name__ == "__main__":
    main()
