"""
Supabase Auth integration for LexAI.

Provides login/signup UI and session management.
Each authenticated user gets an isolated workspace
(conversations, documents, tenant scope).
"""

import os

import streamlit as st

from src.config.logging_config import setup_logger
from src.config.translations import t

logger = setup_logger(__name__)

_AUTH_SESSION_KEY = "auth_session"
_AUTH_USER_KEY = "auth_user"


def _get_auth_client():
    """Get or create a Supabase client for auth operations."""
    if "auth_supabase" not in st.session_state:
        try:
            from supabase import create_client

            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_KEY", "")
            if url and key:
                st.session_state["auth_supabase"] = create_client(url, key)
            else:
                st.session_state["auth_supabase"] = None
        except Exception as exc:
            logger.error("Failed to create auth Supabase client: %s", exc)
            st.session_state["auth_supabase"] = None
    return st.session_state["auth_supabase"]


def is_authenticated() -> bool:
    """Check if a user is currently authenticated."""
    return _AUTH_USER_KEY in st.session_state and st.session_state[_AUTH_USER_KEY] is not None


def get_current_user_id() -> str | None:
    """Return the authenticated user's ID, or None."""
    user = st.session_state.get(_AUTH_USER_KEY)
    if user and isinstance(user, dict):
        return user.get("id")
    return None


def get_current_user_email() -> str | None:
    """Return the authenticated user's email, or None."""
    user = st.session_state.get(_AUTH_USER_KEY)
    if user and isinstance(user, dict):
        return user.get("email")
    return None


def sign_out() -> None:
    """Sign out the current user and clear session."""
    client = _get_auth_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as exc:
            logger.warning("Sign-out API call failed (session cleared locally): %s", exc)

    for key in [_AUTH_SESSION_KEY, _AUTH_USER_KEY, "auth_supabase", "tenant_id", "user_id"]:
        st.session_state.pop(key, None)


def _sign_in(email: str, password: str) -> tuple[bool, str]:
    """Attempt sign-in. Returns (success, error_message)."""
    client = _get_auth_client()
    if not client:
        return False, "Supabase client not available."

    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if response.user:
            st.session_state[_AUTH_USER_KEY] = {
                "id": response.user.id,
                "email": response.user.email,
            }
            st.session_state[_AUTH_SESSION_KEY] = {
                "access_token": response.session.access_token if response.session else None,
            }
            st.session_state["tenant_id"] = response.user.id
            return True, ""
        return False, "Invalid credentials."
    except Exception as exc:
        error_msg = str(exc)
        if "Invalid login credentials" in error_msg:
            return False, "Invalid email or password."
        if "Email not confirmed" in error_msg:
            return False, "Please confirm your email before signing in."
        logger.error("Sign-in failed: %s", exc)
        return False, f"Sign-in failed: {error_msg}"


def _sign_up(email: str, password: str) -> tuple[bool, str]:
    """Attempt sign-up. Returns (success, message)."""
    client = _get_auth_client()
    if not client:
        return False, "Supabase client not available."

    try:
        response = client.auth.sign_up({"email": email, "password": password})
        if response.user:
            if response.user.identities and len(response.user.identities) > 0:
                return True, "Account created. Please check your email for confirmation."
            return False, "An account with this email already exists."
        return False, "Sign-up failed."
    except Exception as exc:
        error_msg = str(exc)
        if "already registered" in error_msg.lower():
            return False, "An account with this email already exists."
        logger.error("Sign-up failed: %s", exc)
        return False, f"Sign-up failed: {error_msg}"


def render_auth_page(lang: str) -> None:
    """Render the login/signup page. Blocks access to the main app until authenticated."""
    st.set_page_config(
        page_title="LexAI \u2014 Login",
        page_icon="\u2696\ufe0f",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
            /* Clean light background */
            .stApp {
                background: #f8fafc !important;
                min-height: 100vh;
            }

            /* Hide sidebar on auth page */
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarCollapsedControl"] { display: none !important; }

            /* Auth card — light mode with subtle shadow */
            .auth-card {
                max-width: 440px;
                margin: 3rem auto 0;
                padding: 2.5rem 2rem 2rem;
                border-radius: 16px;
                background: #ffffff;
                border: 1px solid #e2e8f0;
                box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            }
            .auth-logo { text-align: center; margin-bottom: 0.5rem; }
            .auth-logo svg {
                width: 48px; height: 48px;
                filter: drop-shadow(0 2px 6px rgba(37,99,235,0.3));
            }
            .auth-title {
                text-align: center; font-size: 1.75rem; font-weight: 700;
                color: #1e3a5f; margin: 0.5rem 0 0.15rem; letter-spacing: -0.5px;
            }
            .auth-subtitle {
                text-align: center; color: #64748b; font-size: 0.88rem;
                margin-bottom: 1.5rem;
            }

            /* Inputs */
            .stApp .stTextInput > div > div > input {
                background: #f8fafc !important; color: #0f172a !important;
                border: 1px solid #cbd5e1 !important; border-radius: 8px !important;
            }
            .stApp .stTextInput > div > div > input:focus {
                border-color: #2563eb !important;
                box-shadow: 0 0 0 2px rgba(37,99,235,0.2) !important;
            }
            .stApp .stTextInput label {
                color: #334155 !important; font-weight: 500 !important;
            }

            /* Submit button */
            .stApp [data-testid="stFormSubmitButton"] button {
                background: linear-gradient(135deg, #2563eb, #1e3a5f) !important;
                color: #ffffff !important; border: none !important;
                border-radius: 8px !important; padding: 0.6rem 1rem !important;
                font-weight: 600 !important; font-size: 0.95rem !important;
                transition: opacity 0.2s !important;
            }
            .stApp [data-testid="stFormSubmitButton"] button:hover { opacity: 0.9 !important; }

            /* Tabs */
            .stApp .stTabs [data-baseweb="tab-list"] {
                gap: 0 !important; background: transparent !important;
            }
            .stApp .stTabs [data-baseweb="tab"] {
                color: #64748b !important; font-weight: 500 !important;
                border-bottom: 2px solid transparent !important;
            }
            .stApp .stTabs [aria-selected="true"] {
                color: #2563eb !important; border-bottom-color: #2563eb !important;
            }
            .stApp .stTabs [data-baseweb="tab-panel"] { padding-top: 1.25rem !important; }

            /* Footer */
            .auth-footer {
                text-align: center; color: #94a3b8; font-size: 0.72rem;
                margin-top: 1.5rem;
            }

            /* Selectbox — light mode */
            .stApp [data-testid="stSelectbox"] > div > div,
            .stApp [data-testid="stSelectbox"] div[data-baseweb],
            .stApp [data-testid="stSelectbox"] div[data-baseweb] > div {
                background: #ffffff !important; color: #0f172a !important;
                border-color: #cbd5e1 !important; border-radius: 8px !important;
            }
            .stApp [data-testid="stSelectbox"] input {
                color: #0f172a !important; -webkit-text-fill-color: #0f172a !important;
            }
            .stApp [data-testid="stSelectbox"] svg { fill: #64748b !important; }
            .stApp [data-testid="stSelectbox"] span { color: #0f172a !important; }

            /* Dropdown popup — always readable */
            [role="listbox"], [role="listbox"] > div,
            [data-baseweb="popover"], [data-baseweb="popover"] > div,
            [data-baseweb="popover"] > div > div,
            [data-baseweb="menu"], [data-baseweb="menu"] > div,
            ul[role="listbox"], ul[role="listbox"] > li {
                background-color: #ffffff !important; color: #0f172a !important;
            }
            [role="option"] {
                background-color: #ffffff !important; color: #0f172a !important;
            }
            [role="option"]:hover, [role="option"][aria-selected="true"] {
                background-color: #eff6ff !important; color: #1e3a5f !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Language selector at the top
    _AUTH_LANG_OPTIONS = {"English": "en", "Suomi": "fi", "Svenska": "sv"}

    def _on_auth_lang_change():
        label = st.session_state.auth_lang_selector
        st.session_state.lang = _AUTH_LANG_OPTIONS.get(label, "en")

    lang_labels = list(_AUTH_LANG_OPTIONS.keys())
    lang_values = list(_AUTH_LANG_OPTIONS.values())
    current_idx = lang_values.index(lang) if lang in lang_values else 0

    _, col_lang = st.columns([3, 1])
    with col_lang:
        st.selectbox(
            "🌐",
            lang_labels,
            index=current_idx,
            key="auth_lang_selector",
            on_change=_on_auth_lang_change,
            label_visibility="collapsed",
        )

    # Re-read lang after potential change
    lang = st.session_state.get("lang", lang)

    st.markdown(
        f"""
        <div class="auth-card">
            <div class="auth-logo">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                          stroke="#2563eb" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <div class="auth-title">LexAI</div>
            <div class="auth-subtitle">{t("auth_subtitle", lang)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_login, tab_signup = st.tabs([t("auth_login", lang), t("auth_signup", lang)])

    with tab_login:
        _render_login_form(lang)

    with tab_signup:
        _render_signup_form(lang)

    st.markdown(
        '<div class="auth-footer">\u00a9 2026 LexAI. All rights reserved.</div>',
        unsafe_allow_html=True,
    )


def _render_login_form(lang: str) -> None:
    """Render the sign-in form."""
    with st.form("login_form"):
        email = st.text_input(t("auth_email", lang), key="login_email")
        password = st.text_input(t("auth_password", lang), type="password", key="login_password")
        submitted = st.form_submit_button(t("auth_login_button", lang), use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error(t("auth_fields_required", lang))
            else:
                success, message = _sign_in(email.strip(), password)
                if success:
                    st.rerun()
                else:
                    st.error(message)


def _render_signup_form(lang: str) -> None:
    """Render the sign-up form."""
    with st.form("signup_form"):
        email = st.text_input(t("auth_email", lang), key="signup_email")
        password = st.text_input(t("auth_password", lang), type="password", key="signup_password")
        password_confirm = st.text_input(
            t("auth_confirm_password", lang), type="password", key="signup_password_confirm"
        )
        submitted = st.form_submit_button(t("auth_signup_button", lang), use_container_width=True, type="primary")

        if submitted:
            if not email or not password or not password_confirm:
                st.error(t("auth_fields_required", lang))
            elif len(password) < 8:
                st.error(t("auth_password_min_length", lang))
            elif password != password_confirm:
                st.error(t("auth_password_mismatch", lang))
            else:
                success, message = _sign_up(email.strip(), password)
                if success:
                    st.success(message)
                else:
                    st.error(message)
