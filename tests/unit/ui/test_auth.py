"""
Unit tests for auth module: sign-in, sign-up, session persistence, sign-out.

Uses mocked Supabase client; no real database or Streamlit runtime.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st_mod

_TEST_USER_ID = "user-uuid-abc-123"
_TEST_EMAIL = "test@example.com"
_TEST_ACCESS_TOKEN = "eyJ.test.access_token"
_TEST_REFRESH_TOKEN = "refresh_abc123"


def _make_user(uid: str = _TEST_USER_ID, email: str = _TEST_EMAIL, identities: list | None = None):
    """Build a mock Supabase user object."""
    if identities is None:
        identities = [{"id": "1"}]
    return SimpleNamespace(id=uid, email=email, identities=identities)


def _make_session(access_token: str = _TEST_ACCESS_TOKEN, refresh_token: str = _TEST_REFRESH_TOKEN):
    """Build a mock Supabase session object."""
    return SimpleNamespace(access_token=access_token, refresh_token=refresh_token)


def _make_auth_response(user=None, session=None):
    """Build a mock Supabase auth response."""
    return SimpleNamespace(user=user, session=session)


@pytest.fixture(autouse=True)
def _session_state(monkeypatch):
    """Replace st.session_state with a plain dict for every test."""
    state = {}
    monkeypatch.setattr(st_mod, "session_state", state, raising=False)
    return state


@pytest.fixture()
def supabase_client():
    """A mock Supabase client wired into auth._get_auth_client."""
    client = MagicMock()
    with patch("src.ui.auth._get_auth_client", return_value=client):
        yield client


# ---------------------------------------------------------------------------
#  _sign_in
# ---------------------------------------------------------------------------


class TestSignIn:
    """Tests for the _sign_in function."""

    def test_should_authenticate_with_valid_credentials(self, supabase_client, _session_state):
        user = _make_user()
        session = _make_session()
        supabase_client.auth.sign_in_with_password.return_value = _make_auth_response(user, session)

        from src.ui.auth import _sign_in

        success, message = _sign_in(_TEST_EMAIL, "correct-password")

        assert success is True
        assert message == ""
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
        assert _session_state["auth_user"]["email"] == _TEST_EMAIL
        assert _session_state["auth_session"]["access_token"] == _TEST_ACCESS_TOKEN
        assert _session_state["auth_session"]["refresh_token"] == _TEST_REFRESH_TOKEN
        assert _session_state["tenant_id"] == _TEST_USER_ID

    def test_should_reject_invalid_credentials(self, supabase_client, _session_state):
        supabase_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

        from src.ui.auth import _sign_in

        success, message = _sign_in(_TEST_EMAIL, "wrong-password")

        assert success is False
        assert "Invalid email or password" in message
        assert "auth_user" not in _session_state

    def test_should_flag_unconfirmed_email(self, supabase_client):
        supabase_client.auth.sign_in_with_password.side_effect = Exception("Email not confirmed")

        from src.ui.auth import _EMAIL_NOT_CONFIRMED, _sign_in

        success, message = _sign_in(_TEST_EMAIL, "any-password")

        assert success is False
        assert message == _EMAIL_NOT_CONFIRMED

    def test_should_fail_when_client_unavailable(self):
        with patch("src.ui.auth._get_auth_client", return_value=None):
            from src.ui.auth import _sign_in

            success, message = _sign_in(_TEST_EMAIL, "password")

        assert success is False
        assert "not available" in message

    def test_should_fail_when_user_is_none(self, supabase_client, _session_state):
        supabase_client.auth.sign_in_with_password.return_value = _make_auth_response(user=None)

        from src.ui.auth import _sign_in

        success, _ = _sign_in(_TEST_EMAIL, "password")

        assert success is False
        assert "auth_user" not in _session_state


# ---------------------------------------------------------------------------
#  _sign_up
# ---------------------------------------------------------------------------


class TestSignUp:
    """Tests for the _sign_up function."""

    def test_should_create_account_successfully(self, supabase_client):
        user = _make_user(identities=[{"id": "1"}])
        supabase_client.auth.sign_up.return_value = _make_auth_response(user=user)

        from src.ui.auth import _sign_up

        success, message = _sign_up(_TEST_EMAIL, "strong-password-123")

        assert success is True
        assert message == ""

    def test_should_pass_redirect_url_in_options(self, supabase_client):
        user = _make_user(identities=[{"id": "1"}])
        supabase_client.auth.sign_up.return_value = _make_auth_response(user=user)

        with patch.dict("os.environ", {"APP_BASE_URL": "https://myapp.com"}):
            from src.ui.auth import _sign_up

            _sign_up(_TEST_EMAIL, "password123")

        call_args = supabase_client.auth.sign_up.call_args[0][0]
        assert call_args["options"]["email_redirect_to"] == "https://myapp.com"

    def test_should_reject_existing_email_via_empty_identities(self, supabase_client):
        user = _make_user(identities=[])
        supabase_client.auth.sign_up.return_value = _make_auth_response(user=user)

        from src.ui.auth import _sign_up

        success, message = _sign_up(_TEST_EMAIL, "password123")

        assert success is False
        assert "already exists" in message

    def test_should_handle_already_registered_exception(self, supabase_client):
        supabase_client.auth.sign_up.side_effect = Exception("User already registered")

        from src.ui.auth import _sign_up

        success, message = _sign_up(_TEST_EMAIL, "password123")

        assert success is False
        assert "already exists" in message

    def test_should_fail_when_client_unavailable(self):
        with patch("src.ui.auth._get_auth_client", return_value=None):
            from src.ui.auth import _sign_up

            success, message = _sign_up(_TEST_EMAIL, "password123")

        assert success is False
        assert "not available" in message


# ---------------------------------------------------------------------------
#  Session store / auth checks
# ---------------------------------------------------------------------------


class TestSessionManagement:
    """Tests for session state management."""

    def test_should_store_session_correctly(self, _session_state):
        user = _make_user()

        from src.ui.auth import _store_auth_session

        _store_auth_session(user, _TEST_ACCESS_TOKEN, _TEST_REFRESH_TOKEN)

        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
        assert _session_state["auth_user"]["email"] == _TEST_EMAIL
        assert _session_state["auth_session"]["access_token"] == _TEST_ACCESS_TOKEN
        assert _session_state["auth_session"]["refresh_token"] == _TEST_REFRESH_TOKEN
        assert _session_state["tenant_id"] == _TEST_USER_ID

    def test_is_authenticated_should_return_true_when_user_exists(self, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID, "email": _TEST_EMAIL}

        from src.ui.auth import is_authenticated

        assert is_authenticated() is True

    def test_is_authenticated_should_return_false_when_no_user(self):
        from src.ui.auth import is_authenticated

        assert is_authenticated() is False

    def test_is_authenticated_should_return_false_when_user_is_none(self, _session_state):
        _session_state["auth_user"] = None

        from src.ui.auth import is_authenticated

        assert is_authenticated() is False

    def test_get_current_user_id_should_return_id(self, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID, "email": _TEST_EMAIL}

        from src.ui.auth import get_current_user_id

        assert get_current_user_id() == _TEST_USER_ID

    def test_get_current_user_id_should_return_none_when_unauthenticated(self):
        from src.ui.auth import get_current_user_id

        assert get_current_user_id() is None

    def test_get_current_user_email_should_return_email(self, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID, "email": _TEST_EMAIL}

        from src.ui.auth import get_current_user_email

        assert get_current_user_email() == _TEST_EMAIL


# ---------------------------------------------------------------------------
#  sign_out
# ---------------------------------------------------------------------------


class TestSignOut:
    """Tests for the sign_out function."""

    def test_should_clear_session_state(self, supabase_client, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID}
        _session_state["auth_session"] = {"access_token": _TEST_ACCESS_TOKEN}
        _session_state["tenant_id"] = _TEST_USER_ID
        _session_state["user_id"] = _TEST_USER_ID

        from src.ui.auth import sign_out

        sign_out()

        assert "auth_user" not in _session_state
        assert "auth_session" not in _session_state
        assert "tenant_id" not in _session_state
        assert "user_id" not in _session_state

    def test_should_set_clear_storage_flag(self, supabase_client, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID}
        _session_state["auth_session"] = {}

        from src.ui.auth import sign_out

        sign_out()

        assert _session_state.get("_clear_storage") is True

    def test_should_call_supabase_sign_out(self, supabase_client, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID}
        _session_state["auth_session"] = {}

        from src.ui.auth import sign_out

        sign_out()

        supabase_client.auth.sign_out.assert_called_once()

    def test_should_survive_sign_out_api_failure(self, supabase_client, _session_state):
        supabase_client.auth.sign_out.side_effect = Exception("Network error")
        _session_state["auth_user"] = {"id": _TEST_USER_ID}
        _session_state["auth_session"] = {}

        from src.ui.auth import sign_out

        sign_out()

        assert "auth_user" not in _session_state


# ---------------------------------------------------------------------------
#  _try_restore_from_query_params
# ---------------------------------------------------------------------------


class TestQueryParamRestore:
    """Tests for session restore from query params."""

    def test_should_restore_session_from_valid_tokens(self, supabase_client, _session_state):
        user = _make_user()
        session = _make_session(access_token="new_at", refresh_token="new_rt")
        supabase_client.auth.set_session.return_value = _make_auth_response(user, session)

        mock_params = {"_sat": _TEST_ACCESS_TOKEN, "_srt": _TEST_REFRESH_TOKEN}

        with patch("src.ui.auth.st.query_params", mock_params):
            from src.ui.auth import _try_restore_from_query_params

            result = _try_restore_from_query_params()

        assert result is True
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
        assert _session_state["auth_session"]["access_token"] == "new_at"

    def test_should_return_false_when_no_restore_params(self):
        with patch("src.ui.auth.st.query_params", {}):
            from src.ui.auth import _try_restore_from_query_params

            assert _try_restore_from_query_params() is False

    def test_should_fallback_to_get_user_when_set_session_fails(self, supabase_client, _session_state):
        supabase_client.auth.set_session.side_effect = Exception("set_session failed")
        user = _make_user()
        supabase_client.auth.get_user.return_value = SimpleNamespace(user=user)

        mock_params = {"_sat": _TEST_ACCESS_TOKEN, "_srt": _TEST_REFRESH_TOKEN}

        with patch("src.ui.auth.st.query_params", mock_params):
            from src.ui.auth import _try_restore_from_query_params

            result = _try_restore_from_query_params()

        assert result is True
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID


# ---------------------------------------------------------------------------
#  try_restore_from_cookies
# ---------------------------------------------------------------------------


class TestCookieRestore:
    """Tests for session restore from browser cookies."""

    def test_should_restore_session_from_valid_cookies(self, supabase_client, _session_state):
        user = _make_user()
        session = _make_session(access_token="cookie_at", refresh_token="cookie_rt")
        supabase_client.auth.set_session.return_value = _make_auth_response(user, session)

        future_exp = str(int(__import__("time").time()) + 600)
        mock_cookies = {"lexai_at": _TEST_ACCESS_TOKEN, "lexai_rt": _TEST_REFRESH_TOKEN, "lexai_exp": future_exp}
        mock_context = SimpleNamespace(cookies=mock_cookies)

        with patch("src.ui.auth.st.context", mock_context):
            from src.ui.auth import try_restore_from_cookies

            result = try_restore_from_cookies()

        assert result is True
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
        assert _session_state["auth_session"]["access_token"] == "cookie_at"

    def test_should_return_false_when_no_cookies(self, _session_state):
        mock_context = SimpleNamespace(cookies={})

        with patch("src.ui.auth.st.context", mock_context):
            from src.ui.auth import try_restore_from_cookies

            assert try_restore_from_cookies() is False

    def test_should_reject_expired_cookies(self, supabase_client, _session_state):
        past_exp = str(int(__import__("time").time()) - 60)
        mock_cookies = {"lexai_at": _TEST_ACCESS_TOKEN, "lexai_rt": _TEST_REFRESH_TOKEN, "lexai_exp": past_exp}
        mock_context = SimpleNamespace(cookies=mock_cookies)

        with (
            patch("src.ui.auth.st.context", mock_context),
            patch("src.ui.auth._inject_clear_storage"),
        ):
            from src.ui.auth import try_restore_from_cookies

            assert try_restore_from_cookies() is False
        assert "auth_user" not in _session_state

    def test_should_skip_when_already_authenticated(self, _session_state):
        _session_state["auth_user"] = {"id": _TEST_USER_ID, "email": _TEST_EMAIL}

        from src.ui.auth import try_restore_from_cookies

        assert try_restore_from_cookies() is False


# ---------------------------------------------------------------------------
#  _resend_verification_email
# ---------------------------------------------------------------------------


class TestResendVerification:
    """Tests for resending the verification email."""

    def test_should_resend_successfully(self, supabase_client):
        from src.ui.auth import _resend_verification_email

        result = _resend_verification_email(_TEST_EMAIL)

        assert result is True
        call_args = supabase_client.auth.resend.call_args[0][0]
        assert call_args["type"] == "signup"
        assert call_args["email"] == _TEST_EMAIL
        assert "email_redirect_to" in call_args["options"]

    def test_should_return_false_on_api_failure(self, supabase_client):
        supabase_client.auth.resend.side_effect = Exception("Rate limited")

        from src.ui.auth import _resend_verification_email

        assert _resend_verification_email(_TEST_EMAIL) is False

    def test_should_return_false_when_client_unavailable(self):
        with patch("src.ui.auth._get_auth_client", return_value=None):
            from src.ui.auth import _resend_verification_email

            assert _resend_verification_email(_TEST_EMAIL) is False


# ---------------------------------------------------------------------------
#  _handle_email_confirmation_callback
# ---------------------------------------------------------------------------


class TestEmailConfirmationCallback:
    """Tests for processing the email confirmation redirect tokens."""

    def test_should_establish_session_from_callback_tokens(self, supabase_client, _session_state):
        user = _make_user()
        session = _make_session(access_token="fresh_at", refresh_token="fresh_rt")
        supabase_client.auth.set_session.return_value = _make_auth_response(user, session)

        mock_params = {"access_token": _TEST_ACCESS_TOKEN, "refresh_token": _TEST_REFRESH_TOKEN}

        with (
            patch("src.ui.auth.st.query_params", mock_params),
            patch("src.ui.auth.st.toast"),
        ):
            from src.ui.auth import _handle_email_confirmation_callback

            result = _handle_email_confirmation_callback("en")

        assert result is True
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
        assert _session_state["auth_session"]["access_token"] == "fresh_at"

    def test_should_return_false_when_no_access_token_in_params(self):
        with patch("src.ui.auth.st.query_params", {}):
            from src.ui.auth import _handle_email_confirmation_callback

            assert _handle_email_confirmation_callback("en") is False

    def test_should_fallback_to_get_user_on_set_session_failure(self, supabase_client, _session_state):
        supabase_client.auth.set_session.side_effect = Exception("set_session failed")
        user = _make_user()
        supabase_client.auth.get_user.return_value = SimpleNamespace(user=user)

        mock_params = {"access_token": _TEST_ACCESS_TOKEN, "refresh_token": ""}

        with (
            patch("src.ui.auth.st.query_params", mock_params),
            patch("src.ui.auth.st.toast"),
        ):
            from src.ui.auth import _handle_email_confirmation_callback

            result = _handle_email_confirmation_callback("en")

        assert result is True
        assert _session_state["auth_user"]["id"] == _TEST_USER_ID
