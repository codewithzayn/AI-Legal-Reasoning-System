"""
Supabase Auth integration for LexAI.

Provides login/signup UI and session management.
Each authenticated user gets an isolated workspace
(conversations, documents, tenant scope).

Session tokens are persisted in the browser's localStorage so that
a page reload does not force re-authentication.
"""

import contextlib
import json
import os
import time

import streamlit as st
import streamlit.components.v1 as components

from src.config.logging_config import setup_logger
from src.config.translations import t

logger = setup_logger(__name__)

_AUTH_SESSION_KEY = "auth_session"
_AUTH_USER_KEY = "auth_user"
_PASSWORD_PLACEHOLDER = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
_EMAIL_NOT_CONFIRMED = "__EMAIL_NOT_CONFIRMED__"
_UNVERIFIED_EMAIL_KEY = "auth_unverified_email"

_STORAGE_KEY_AT = "lexai_at"
_STORAGE_KEY_RT = "lexai_rt"
_COOKIE_AT = "lexai_at"
_COOKIE_RT = "lexai_rt"
_COOKIE_EXP = "lexai_exp"
_RESTORE_PARAM_AT = "_sat"
_RESTORE_PARAM_RT = "_srt"

# Append "; Secure" to cookie writes when APP_BASE_URL is HTTPS (production)
_SECURE_FLAG = "; Secure" if os.getenv("APP_BASE_URL", "").strip().startswith("https") else ""

SESSION_LIFETIME_SECONDS = int(os.getenv("SESSION_LIFETIME_SECONDS", "3600"))


def _run_iframe_js(js_code: str) -> None:
    """Execute JavaScript inside a same-origin iframe.

    The iframe shares the parent's origin (``allow-same-origin`` sandbox),
    so ``document.cookie`` and ``localStorage`` operate on the real page's
    storage.  Use this for save/clear operations that do NOT require
    navigating the parent page.
    """
    components.html(f"<script>{js_code}</script>", height=0)


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


def _get_app_base_url() -> str:
    """Return the application base URL for email confirmation redirects."""
    return os.getenv("APP_BASE_URL", "http://localhost:8501").strip().rstrip("/")


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
    """Sign out the current user, clear session state and browser storage."""
    client = _get_auth_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as exc:
            logger.warning("Sign-out API call failed (session cleared locally): %s", exc)

    for key in [
        _AUTH_SESSION_KEY,
        _AUTH_USER_KEY,
        "auth_supabase",
        "tenant_id",
        "user_id",
        "_lexai_session_expires_at",
    ]:
        st.session_state.pop(key, None)

    st.session_state["_clear_storage"] = True


def _store_auth_session(user, access_token: str, refresh_token: str = "") -> None:
    """Persist authenticated user into Streamlit session state."""
    st.session_state[_AUTH_USER_KEY] = {
        "id": user.id,
        "email": user.email,
    }
    st.session_state[_AUTH_SESSION_KEY] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    st.session_state["tenant_id"] = user.id


# ---------------------------------------------------------------------------
#  Cookie + localStorage persistence — survive page reloads
# ---------------------------------------------------------------------------


def sync_session_to_storage() -> None:
    """Save session tokens to browser cookies AND localStorage.

    Cookies are the primary persistence mechanism because Python can read
    them instantly via ``st.context.cookies`` on the next page load —
    no JavaScript redirect needed and zero "flash" of the sign-in page.

    localStorage is kept as a secondary backup.

    The expiry timestamp is set once at login and preserved across reloads
    so the session actually expires after SESSION_LIFETIME_SECONDS.
    """
    if not is_authenticated():
        return
    session = st.session_state.get(_AUTH_SESSION_KEY, {})
    at = session.get("access_token", "")
    rt = session.get("refresh_token", "")
    if not at:
        return

    _SESSION_EXP_KEY = "_lexai_session_expires_at"
    if _SESSION_EXP_KEY not in st.session_state:
        st.session_state[_SESSION_EXP_KEY] = int(time.time()) + SESSION_LIFETIME_SECONDS
    expires_at = st.session_state[_SESSION_EXP_KEY]

    remaining_seconds = max(0, expires_at - int(time.time()))
    if remaining_seconds <= 0:
        sign_out()
        return

    at_js = json.dumps(at)
    rt_js = json.dumps(rt)
    _run_iframe_js(
        f"document.cookie='{_COOKIE_AT}='+encodeURIComponent({at_js})"
        f"+';path=/;max-age={remaining_seconds};SameSite=Lax{_SECURE_FLAG}';"
        f"document.cookie='{_COOKIE_RT}='+encodeURIComponent({rt_js})"
        f"+';path=/;max-age={remaining_seconds};SameSite=Lax{_SECURE_FLAG}';"
        f"document.cookie='{_COOKIE_EXP}={expires_at}"
        f";path=/;max-age={remaining_seconds};SameSite=Lax{_SECURE_FLAG}';"
        f"try{{localStorage.setItem('{_STORAGE_KEY_AT}',{at_js});"
        f"localStorage.setItem('{_STORAGE_KEY_RT}',{rt_js})}}catch(e){{}}"
    )


def _validate_and_restore_tokens(at: str, rt: str) -> bool:
    """Validate tokens with Supabase and restore the session if valid."""
    client = _get_auth_client()
    if not client:
        return False

    try:
        response = client.auth.set_session(at, rt or "")
        if response and response.user:
            new_at = response.session.access_token if response.session else at
            new_rt = response.session.refresh_token if response.session else (rt or "")
            _store_auth_session(response.user, new_at, new_rt)
            return True
    except Exception as exc:
        logger.warning("set_session failed, trying get_user: %s", exc)

    try:
        user_response = client.auth.get_user(at)
        if user_response and user_response.user:
            _store_auth_session(user_response.user, at, rt or "")
            return True
    except Exception as exc:
        logger.debug("Token validation failed (token expired): %s", exc)

    return False


def _is_session_expired(exp_str: str) -> bool:
    """Check whether the session cookie expiry timestamp has passed."""
    if not exp_str:
        return False
    try:
        return time.time() > float(exp_str)
    except ValueError:
        return False


def try_restore_from_cookies() -> bool:
    """Restore session from browser cookies (server-side, instant).

    Reads ``st.context.cookies`` which reflects cookies sent with the
    current HTTP request.  No JavaScript needed — the session is restored
    before any page content renders, eliminating the "flash" of the
    sign-in page on reload.

    Returns True if session was successfully restored.
    """
    if is_authenticated():
        return False

    try:
        cookies = st.context.cookies
    except Exception:
        return False

    at = cookies.get(_COOKIE_AT, "")
    rt = cookies.get(_COOKIE_RT, "")

    if not at:
        return False

    exp_str = cookies.get(_COOKIE_EXP, "")
    if _is_session_expired(exp_str):
        logger.debug("Session cookie expired, clearing")
        _inject_clear_storage()
        return False

    if _validate_and_restore_tokens(at, rt):
        if exp_str:
            with contextlib.suppress(ValueError):
                st.session_state["_lexai_session_expires_at"] = int(float(exp_str))
        return True

    _inject_clear_storage()
    return False


def _try_restore_from_query_params() -> bool:
    """Restore session from query params (email confirmation or hash redirect)."""
    at = st.query_params.get(_RESTORE_PARAM_AT)
    rt = st.query_params.get(_RESTORE_PARAM_RT)
    if not at:
        return False

    st.query_params.clear()
    return _validate_and_restore_tokens(at, rt)


def _inject_clear_storage() -> None:
    """Remove session tokens from both cookies and localStorage."""
    _run_iframe_js(
        f"document.cookie='{_COOKIE_AT}=;path=/;max-age=0';"
        f"document.cookie='{_COOKIE_RT}=;path=/;max-age=0';"
        f"document.cookie='{_COOKIE_EXP}=;path=/;max-age=0';"
        f"try{{localStorage.removeItem('{_STORAGE_KEY_AT}');"
        f"localStorage.removeItem('{_STORAGE_KEY_RT}')}}catch(e){{}}"
    )


# ---------------------------------------------------------------------------
#  Sign-in / sign-up
# ---------------------------------------------------------------------------


def _sign_in(email: str, password: str) -> tuple[bool, str]:
    """Attempt sign-in. Returns (success, error_message)."""
    client = _get_auth_client()
    if not client:
        return False, "Supabase client not available."

    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if response.user:
            access_token = response.session.access_token if response.session else ""
            refresh_token = response.session.refresh_token if response.session else ""
            _store_auth_session(response.user, access_token, refresh_token)
            return True, ""
        return False, "Invalid credentials."
    except Exception as exc:
        error_msg = str(exc)
        if "Invalid login credentials" in error_msg:
            return False, "Invalid email or password."
        if "Email not confirmed" in error_msg:
            return False, _EMAIL_NOT_CONFIRMED
        logger.error("Sign-in failed: %s", exc)
        return False, f"Sign-in failed: {error_msg}"


def _sign_up(email: str, password: str) -> tuple[bool, str]:
    """Attempt sign-up with email confirmation redirect. Returns (success, message)."""
    client = _get_auth_client()
    if not client:
        return False, "Supabase client not available."

    redirect_url = _get_app_base_url()
    try:
        response = client.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {
                    "email_redirect_to": redirect_url,
                },
            }
        )
        if response.user:
            if response.user.identities and len(response.user.identities) > 0:
                return True, ""
            return False, "An account with this email already exists."
        return False, "Sign-up failed."
    except Exception as exc:
        error_msg = str(exc)
        if "already registered" in error_msg.lower():
            return False, "An account with this email already exists."
        logger.error("Sign-up failed: %s", exc)
        return False, f"Sign-up failed: {error_msg}"


def _resend_verification_email(email: str) -> bool:
    """Re-send the signup verification email for an unverified account."""
    client = _get_auth_client()
    if not client:
        return False

    redirect_url = _get_app_base_url()
    try:
        client.auth.resend(
            {
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": redirect_url,
                },
            }
        )
        return True
    except Exception as exc:
        logger.error("Failed to resend verification email to %s: %s", email, exc)
        return False


# ---------------------------------------------------------------------------
#  Email-confirmation callback
# ---------------------------------------------------------------------------


def _handle_email_confirmation_callback(lang: str) -> bool:
    """
    Process tokens delivered by the email-confirmation redirect.

    After email confirmation Supabase redirects with tokens in the URL hash.
    JavaScript (injected below) moves them to query-params so Python can read
    them.  This function exchanges those tokens for a session.
    """
    access_token = st.query_params.get("access_token")
    refresh_token = st.query_params.get("refresh_token")

    if not access_token:
        return False

    client = _get_auth_client()
    if not client:
        st.query_params.clear()
        return False

    try:
        response = client.auth.set_session(access_token, refresh_token or "")
        if response and response.user:
            new_at = response.session.access_token if response.session else access_token
            new_rt = response.session.refresh_token if response.session else (refresh_token or "")
            _store_auth_session(response.user, new_at, new_rt)
            st.query_params.clear()
            st.toast(t("auth_email_confirmed", lang), icon="\u2705")
            return True
    except Exception as exc:
        logger.warning("set_session failed, trying get_user fallback: %s", exc)

    try:
        user_response = client.auth.get_user(access_token)
        if user_response and user_response.user:
            _store_auth_session(user_response.user, access_token, refresh_token or "")
            st.query_params.clear()
            st.toast(t("auth_email_confirmed", lang), icon="\u2705")
            return True
    except Exception as exc:
        logger.error("Email confirmation callback failed: %s", exc)

    st.query_params.clear()
    st.toast(t("auth_callback_failed", lang), icon="\u274c")
    return False


def _inject_hash_fragment_handler() -> None:
    """Extract access-token from the URL hash, save to cookies, reload clean.

    Supabase email confirmation uses the implicit grant flow which puts
    tokens in the URL hash fragment (#access_token=...).  Streamlit cannot
    read hash fragments, so this script:

    1. Saves them into cookies (for ``try_restore_from_cookies()``).
    2. Cleans the address bar via ``history.replaceState`` (removes tokens).
    3. Attempts a page reload via a dynamically created link click so the
       server receives the new cookies on the next HTTP request.
    """
    exp = int(time.time()) + SESSION_LIFETIME_SECONDS
    pathname_url = _get_app_base_url()
    _run_iframe_js(
        "(function(){"
        "var h=window.parent.location.hash;"
        "if(!h||h.indexOf('access_token=')===-1)return;"
        "var p=new URLSearchParams(h.substring(1));"
        "var a=p.get('access_token');"
        "var r=p.get('refresh_token')||'';"
        "if(!a)return;"
        f"document.cookie='{_COOKIE_AT}='+encodeURIComponent(a)"
        f"+';path=/;max-age={SESSION_LIFETIME_SECONDS};SameSite=Lax{_SECURE_FLAG}';"
        f"document.cookie='{_COOKIE_RT}='+encodeURIComponent(r)"
        f"+';path=/;max-age={SESSION_LIFETIME_SECONDS};SameSite=Lax{_SECURE_FLAG}';"
        f"document.cookie='{_COOKIE_EXP}={exp}"
        f";path=/;max-age={SESSION_LIFETIME_SECONDS};SameSite=Lax{_SECURE_FLAG}';"
        "try{window.parent.history.replaceState(null,'',"
        "window.parent.location.pathname)}catch(e){}"
        "setTimeout(function(){"
        "var l=document.createElement('a');"
        f"l.href='{pathname_url}';"
        "l.target='_top';l.style.display='none';"
        "document.body.appendChild(l);l.click();"
        "},200)"
        "})()"
    )


# ---------------------------------------------------------------------------
#  CSS
# ---------------------------------------------------------------------------


def _inject_auth_css() -> None:
    """Inject all CSS for the authentication page."""
    st.markdown(
        """
        <style>
            /* ── Page background ── */
            .stApp {
                background: linear-gradient(160deg, #eef2f9 0%, #e3eaf4 40%, #dde5f0 100%) !important;
                min-height: 100vh;
            }

            /* ── Hide sidebar, header chrome, branding ── */
            [data-testid="stSidebar"],
            [data-testid="stSidebarCollapsedControl"] { display: none !important; }
            header[data-testid="stHeader"] { background: transparent !important; }
            #MainMenu { visibility: hidden; }
            footer { visibility: hidden; }

            /* ── Transparent wrappers so gradient shows ── */
            .main, .main > div,
            [data-testid="stAppViewContainer"],
            [data-testid="stAppViewContainer"] > div {
                background: transparent !important;
            }

            /* ── Auth card = block-container ── */
            .block-container {
                max-width: 460px !important;
                background: #ffffff !important;
                border-radius: 20px !important;
                box-shadow:
                    0 10px 40px rgba(30, 58, 95, 0.10),
                    0 2px 10px rgba(30, 58, 95, 0.05) !important;
                padding: 2.5rem 2.5rem 1.75rem !important;
                margin-top: 2.5rem !important;
                margin-bottom: 2rem !important;
                border: 1px solid rgba(226, 232, 240, 0.7) !important;
            }

            /* ── Logo & header section ── */
            .auth-brand {
                text-align: center;
                margin-bottom: 0.25rem;
            }
            .auth-brand svg {
                width: 44px; height: 44px;
                filter: drop-shadow(0 2px 6px rgba(37,99,235,0.25));
            }
            .auth-brand-name {
                text-align: center;
                font-size: 1.65rem;
                font-weight: 700;
                color: #1e3a5f;
                margin: 0.4rem 0 0.1rem;
                letter-spacing: -0.5px;
            }
            .auth-brand-sub {
                text-align: center;
                color: #64748b;
                font-size: 0.875rem;
                margin-bottom: 1.5rem;
                line-height: 1.4;
            }

            /* ── Pill-style mode selector (radio styled as tabs) ── */
            .stRadio > div[role="radiogroup"] {
                gap: 4px !important;
                background: #f1f5f9 !important;
                border-radius: 12px !important;
                padding: 4px !important;
                display: flex !important;
            }
            .stRadio > div[role="radiogroup"] > label {
                flex: 1 !important;
                display: flex !important;
                justify-content: center !important;
                align-items: center !important;
                border-radius: 10px !important;
                border: none !important;
                font-weight: 600 !important;
                color: #64748b !important;
                background: transparent !important;
                padding: 0.55rem 0.5rem !important;
                font-size: 0.9rem !important;
                white-space: nowrap !important;
                cursor: pointer !important;
                transition: all 0.2s ease !important;
                margin: 0 !important;
            }
            .stRadio > div[role="radiogroup"] > label:hover {
                color: #334155 !important;
            }
            .stRadio > div[role="radiogroup"] > label[data-checked="true"],
            .stRadio > div[role="radiogroup"] > label:has(input:checked) {
                background: #ffffff !important;
                color: #1e3a5f !important;
                box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
            }
            .stRadio > div[role="radiogroup"] > label > div:first-child {
                display: none !important;
            }

            /* ── Text inputs — uniform full-width ── */
            .stTextInput {
                margin-bottom: 0.15rem !important;
            }
            .stTextInput > div,
            .stTextInput > div > div {
                width: 100% !important;
            }
            .stTextInput > div > div > input {
                width: 100% !important;
                box-sizing: border-box !important;
                background: #f8fafc !important;
                color: #0f172a !important;
                border: 1.5px solid #e2e8f0 !important;
                border-radius: 10px !important;
                padding: 0.7rem 0.9rem !important;
                font-size: 0.95rem !important;
                transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
            }
            .stTextInput > div > div > input:focus {
                border-color: #2563eb !important;
                box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
                outline: none !important;
            }
            .stTextInput > div > div > input::placeholder {
                color: #94a3b8 !important;
            }
            .stTextInput label,
            .stTextInput [data-testid="stWidgetLabel"] {
                color: #475569 !important;
                font-weight: 500 !important;
                font-size: 0.875rem !important;
            }

            /* ── Form submit button ── */
            [data-testid="stFormSubmitButton"] button {
                width: 100% !important;
                background: linear-gradient(135deg, #2563eb 0%, #1e3a5f 100%) !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 10px !important;
                padding: 0.7rem 1rem !important;
                font-weight: 600 !important;
                font-size: 0.95rem !important;
                letter-spacing: 0.01em !important;
                transition: opacity 0.2s ease, transform 0.15s ease,
                            box-shadow 0.2s ease !important;
                margin-top: 0.5rem !important;
            }
            [data-testid="stFormSubmitButton"] button:hover {
                opacity: 0.92 !important;
                transform: translateY(-1px) !important;
                box-shadow: 0 4px 16px rgba(37,99,235,0.25) !important;
            }

            /* ── Language selector ── */
            [data-testid="stSelectbox"] {
                min-width: 140px !important;
            }
            [data-testid="stSelectbox"] label,
            [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] {
                color: #475569 !important;
                font-weight: 500 !important;
                font-size: 0.8rem !important;
            }
            [data-testid="stSelectbox"] > div > div,
            [data-testid="stSelectbox"] div[data-baseweb],
            [data-testid="stSelectbox"] div[data-baseweb] > div {
                background: #f8fafc !important;
                color: #0f172a !important;
                border-color: #e2e8f0 !important;
                border-radius: 8px !important;
                font-size: 0.9rem !important;
                min-height: 38px !important;
            }
            [data-testid="stSelectbox"] input {
                color: #0f172a !important;
                -webkit-text-fill-color: #0f172a !important;
            }
            [data-testid="stSelectbox"] svg { fill: #64748b !important; }
            [data-testid="stSelectbox"] span {
                color: #0f172a !important;
                overflow: visible !important;
                text-overflow: unset !important;
                white-space: nowrap !important;
            }

            /* ── Dropdown popup ── */
            [role="listbox"], [role="listbox"] > div,
            [data-baseweb="popover"], [data-baseweb="popover"] > div,
            [data-baseweb="popover"] > div > div,
            [data-baseweb="menu"], [data-baseweb="menu"] > div,
            ul[role="listbox"], ul[role="listbox"] > li {
                background-color: #ffffff !important;
                color: #0f172a !important;
            }
            [role="option"] {
                background-color: #ffffff !important;
                color: #0f172a !important;
                font-size: 0.9rem !important;
                padding: 0.5rem 0.75rem !important;
            }
            [role="option"]:hover, [role="option"][aria-selected="true"] {
                background-color: #eff6ff !important;
                color: #1e3a5f !important;
            }

            /* ── Hide "Press enter to submit form" instruction ── */
            [data-testid="InputInstructions"],
            .stForm [data-testid="InputInstructions"] {
                display: none !important;
            }

            /* ── Alert styling ── */
            .stAlert {
                border-radius: 10px !important;
                font-size: 0.875rem !important;
            }

            /* ── Footer ── */
            .auth-footer {
                text-align: center;
                color: #94a3b8;
                font-size: 0.72rem;
                margin-top: 1.75rem;
                padding-top: 1rem;
                border-top: 1px solid #f1f5f9;
            }

            /* ── Mobile ── */
            @media (max-width: 640px) {
                .block-container {
                    max-width: 100% !important;
                    margin: 1rem 0.75rem !important;
                    padding: 2rem 1.5rem 1.5rem !important;
                    border-radius: 16px !important;
                }
                .auth-brand-name { font-size: 1.45rem; }
                .stTabs [data-baseweb="tab"] {
                    padding: 0.5rem 0.25rem !important;
                    font-size: 0.85rem !important;
                }
            }

            /* ── Very small screens ── */
            @media (max-width: 420px) {
                .block-container {
                    margin: 0.5rem !important;
                    padding: 1.5rem 1.25rem 1.25rem !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
#  Page renderer
# ---------------------------------------------------------------------------


def render_auth_page(lang: str) -> None:
    """Render the login / signup page.  Blocks the main app until authenticated."""
    st.set_page_config(
        page_title="LexAI \u2014 Login",
        page_icon="\u2696\ufe0f",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    # 1. Restore session from query params (email confirmation or hash redirect)
    if _try_restore_from_query_params():
        st.rerun()

    # 2. Process email-confirmation tokens
    if _handle_email_confirmation_callback(lang):
        st.rerun()

    # 3. Clear browser storage when user just signed out
    if st.session_state.pop("_clear_storage", False):
        _inject_clear_storage()

    # 4. JS: extract hash-fragment tokens (email confirmation redirect)
    _inject_hash_fragment_handler()

    _inject_auth_css()

    # ── Language selector (top-right inside card) ──
    _AUTH_LANG_OPTIONS = {"English": "en", "Suomi": "fi", "Svenska": "sv"}

    def _on_auth_lang_change():
        label = st.session_state.auth_lang_selector
        st.session_state.lang = _AUTH_LANG_OPTIONS.get(label, "en")

    lang_labels = list(_AUTH_LANG_OPTIONS.keys())
    lang_values = list(_AUTH_LANG_OPTIONS.values())
    current_idx = lang_values.index(lang) if lang in lang_values else 0

    _, col_lang = st.columns([1, 1])
    with col_lang:
        st.selectbox(
            "\U0001f310 Language",
            lang_labels,
            index=current_idx,
            key="auth_lang_selector",
            on_change=_on_auth_lang_change,
            label_visibility="collapsed",
        )

    lang = st.session_state.get("lang", lang)

    # ── Brand header (inside the card) ──
    st.markdown(
        f"""
        <div class="auth-brand">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                      stroke="#2563eb" stroke-width="1.5"
                      stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="auth-brand-name">LexAI</div>
        <div class="auth-brand-sub">{t("auth_subtitle", lang)}</div>
        """,
        unsafe_allow_html=True,
    )

    # ── Mode selector: Sign In | Create Account ──
    # Uses st.radio instead of st.tabs so the selection persists when the
    # language changes (st.tabs resets when translated labels change).
    auth_mode = st.radio(
        "auth_mode",
        options=["login", "signup"],
        format_func=lambda x: t("auth_login", lang) if x == "login" else t("auth_signup", lang),
        horizontal=True,
        key="auth_mode",
        label_visibility="collapsed",
    )

    if auth_mode == "login":
        _render_login_form(lang)
    else:
        _render_signup_form(lang)

    st.markdown(
        f'<div class="auth-footer">\u00a9 {__import__("datetime").datetime.now().year} LexAI. All rights reserved.</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
#  Form renderers
# ---------------------------------------------------------------------------


def _render_login_form(lang: str) -> None:
    """Render the sign-in form with resend-verification support."""
    with st.form("login_form"):
        email = st.text_input(
            t("auth_email", lang),
            key="login_email",
            placeholder=t("auth_email", lang),
            label_visibility="collapsed",
        )
        password = st.text_input(
            t("auth_password", lang),
            type="password",
            key="login_password",
            placeholder=t("auth_password", lang),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            t("auth_login_button", lang),
            use_container_width=True,
            type="primary",
        )

        if submitted:
            if not email or not password:
                st.toast(t("auth_fields_required", lang), icon="\u274c")
                st.error(t("auth_fields_required", lang))
            else:
                success, message = _sign_in(email.strip(), password)
                if success:
                    st.session_state.pop(_UNVERIFIED_EMAIL_KEY, None)
                    st.rerun()
                elif message == _EMAIL_NOT_CONFIRMED:
                    st.session_state[_UNVERIFIED_EMAIL_KEY] = email.strip()
                    st.rerun()
                else:
                    st.session_state.pop(_UNVERIFIED_EMAIL_KEY, None)
                    st.toast(message, icon="\u274c")
                    st.error(message)

    _render_resend_verification_section(lang)


def _render_resend_verification_section(lang: str) -> None:
    """Show a warning + resend button when the user's email is unverified."""
    unverified_email = st.session_state.get(_UNVERIFIED_EMAIL_KEY)
    if not unverified_email:
        return

    st.warning(t("auth_email_not_verified", lang))
    if st.button(
        t("auth_resend_verification", lang),
        key="resend_verification_btn",
        use_container_width=True,
        type="primary",
    ):
        if _resend_verification_email(unverified_email):
            st.toast(t("auth_verification_resent", lang), icon="\u2709\ufe0f")
            st.session_state.pop(_UNVERIFIED_EMAIL_KEY, None)
            st.rerun()
        else:
            st.toast(t("auth_resend_failed", lang), icon="\u274c")
            st.error(t("auth_resend_failed", lang))


def _render_signup_form(lang: str) -> None:
    """Render the sign-up form."""
    with st.form("signup_form"):
        email = st.text_input(
            t("auth_email", lang),
            key="signup_email",
            placeholder=t("auth_email", lang),
            label_visibility="collapsed",
        )
        password = st.text_input(
            t("auth_password", lang),
            type="password",
            key="signup_password",
            placeholder=t("auth_password", lang),
            label_visibility="collapsed",
        )
        password_confirm = st.text_input(
            t("auth_confirm_password", lang),
            type="password",
            key="signup_password_confirm",
            placeholder=t("auth_confirm_password", lang),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            t("auth_signup_button", lang),
            use_container_width=True,
            type="primary",
        )

        if submitted:
            if not email or not password or not password_confirm:
                st.toast(t("auth_fields_required", lang), icon="\u274c")
                st.error(t("auth_fields_required", lang))
            elif len(password) < 8:
                st.toast(t("auth_password_min_length", lang), icon="\u274c")
                st.error(t("auth_password_min_length", lang))
            elif password != password_confirm:
                st.toast(t("auth_password_mismatch", lang), icon="\u274c")
                st.error(t("auth_password_mismatch", lang))
            else:
                success, message = _sign_up(email.strip(), password)
                if success:
                    st.toast(t("auth_check_email", lang), icon="\u2709\ufe0f")
                    st.info(t("auth_check_email", lang))
                else:
                    st.toast(message, icon="\u274c")
                    st.error(message)
