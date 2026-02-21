"""
Unit tests for conversation_store: save, list, load, delete.

Uses mocked Supabase client; no real database or Streamlit runtime.
All operations are scoped to user_id via _get_user_id().
"""

import json
from unittest.mock import MagicMock, patch

_TEST_USER_ID = "test-user-uuid-123"


def _mock_supabase_client():
    """Build a mock Supabase client with table().insert/update/select/delete chain."""
    client = MagicMock()
    table = MagicMock()
    client.table.return_value = table
    return client, table


def _patch_deps(client):
    """Return a combined context manager that patches both the Supabase client and user_id."""
    return (
        patch("src.ui.conversation_store.get_supabase_client", return_value=client),
        patch("src.ui.conversation_store._get_user_id", return_value=_TEST_USER_ID),
    )


# ---------------------------------------------------------------------------
# save_conversation
# ---------------------------------------------------------------------------
class TestSaveConversation:
    def test_returns_none_when_client_is_none(self) -> None:
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=None),
            patch("src.ui.conversation_store._get_user_id", return_value=_TEST_USER_ID),
        ):
            from src.ui.conversation_store import save_conversation

            assert save_conversation([], "fi") is None
            assert save_conversation([{"role": "user", "content": "Hi"}], "fi") is None

    def test_returns_none_when_no_user_id(self) -> None:
        client, _ = _mock_supabase_client()
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=client),
            patch("src.ui.conversation_store._get_user_id", return_value=None),
        ):
            from src.ui.conversation_store import save_conversation

            assert save_conversation([{"role": "user", "content": "Hi"}], "fi") is None

    def test_returns_none_when_messages_empty(self) -> None:
        client, _ = _mock_supabase_client()
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import save_conversation

            assert save_conversation([], "fi") is None

    def test_insert_sends_correct_payload_and_returns_id(self) -> None:
        client, table = _mock_supabase_client()
        insert_chain = MagicMock()
        table.insert.return_value = insert_chain
        insert_chain.execute.return_value = MagicMock(data=[{"id": "conv-uuid-123"}])
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import save_conversation

            out = save_conversation(
                [
                    {"role": "user", "content": "What is KKO:2024:1?"},
                    {"role": "assistant", "content": "It is a Supreme Court case."},
                ],
                "en",
                conversation_id=None,
            )
        assert out == "conv-uuid-123"
        table.insert.assert_called_once()
        payload = table.insert.call_args[0][0]
        assert payload["title"] == "What is KKO:2024:1?"
        assert payload["lang"] == "en"
        assert payload["user_id"] == _TEST_USER_ID
        assert json.loads(payload["messages_json"]) == [
            {"role": "user", "content": "What is KKO:2024:1?"},
            {"role": "assistant", "content": "It is a Supreme Court case."},
        ]

    def test_update_sends_correct_payload_and_returns_conversation_id(self) -> None:
        client, table = _mock_supabase_client()
        update_chain = MagicMock()
        table.update.return_value = update_chain
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = MagicMock()
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import save_conversation

            out = save_conversation(
                [
                    {"role": "user", "content": "First question"},
                    {"role": "assistant", "content": "First answer"},
                ],
                "fi",
                conversation_id="existing-uuid",
            )
        assert out == "existing-uuid"
        table.update.assert_called_once()
        payload = table.update.call_args[0][0]
        assert payload["title"] == "First question"
        assert payload["lang"] == "fi"
        assert "updated_at" in payload
        assert "T" in payload["updated_at"] and len(payload["updated_at"]) >= 20

    def test_title_from_first_user_message_truncated_to_80(self) -> None:
        client, table = _mock_supabase_client()
        table.insert.return_value.execute.return_value = MagicMock(data=[{"id": "id1"}])
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import save_conversation

            long_query = "x" * 120
            save_conversation([{"role": "user", "content": long_query}], "fi")
        payload = table.insert.call_args[0][0]
        assert len(payload["title"]) == 80
        assert payload["title"] == "x" * 80


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------
class TestListConversations:
    def test_returns_empty_when_client_none(self) -> None:
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=None),
            patch("src.ui.conversation_store._get_user_id", return_value=_TEST_USER_ID),
        ):
            from src.ui.conversation_store import list_conversations

            assert list_conversations() == []

    def test_returns_empty_when_no_user_id(self) -> None:
        client, _ = _mock_supabase_client()
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=client),
            patch("src.ui.conversation_store._get_user_id", return_value=None),
        ):
            from src.ui.conversation_store import list_conversations

            assert list_conversations() == []

    def test_returns_data_from_select(self) -> None:
        client, table = _mock_supabase_client()
        eq_chain = MagicMock()
        table.select.return_value = eq_chain
        eq_chain.eq.return_value = eq_chain
        eq_chain.order.return_value = eq_chain
        eq_chain.limit.return_value = eq_chain
        eq_chain.execute.return_value = MagicMock(
            data=[
                {"id": "a", "title": "Conv A", "lang": "fi", "created_at": "2025-01-01", "updated_at": "2025-01-02"},
                {"id": "b", "title": "Conv B", "lang": "en", "created_at": "2025-01-03", "updated_at": "2025-01-04"},
            ]
        )
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import list_conversations

            result = list_conversations(limit=10)
        assert len(result) == 2
        assert result[0]["id"] == "a" and result[0]["title"] == "Conv A"
        table.select.assert_called_once_with("id, title, lang, created_at, updated_at")
        eq_chain.eq.assert_called_once_with("user_id", _TEST_USER_ID)


# ---------------------------------------------------------------------------
# load_conversation
# ---------------------------------------------------------------------------
class TestLoadConversation:
    def test_returns_none_when_client_none(self) -> None:
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=None),
            patch("src.ui.conversation_store._get_user_id", return_value=_TEST_USER_ID),
        ):
            from src.ui.conversation_store import load_conversation

            assert load_conversation("any-id") is None

    def test_returns_messages_when_data_present(self) -> None:
        client, table = _mock_supabase_client()
        eq_chain = MagicMock()
        table.select.return_value = eq_chain
        eq_chain.eq.return_value = eq_chain
        eq_chain.limit.return_value = eq_chain
        messages = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
        eq_chain.execute.return_value = MagicMock(data=[{"messages_json": messages}])
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import load_conversation

            result = load_conversation("conv-123")
        assert result == messages

    def test_parses_json_string_messages_json(self) -> None:
        client, table = _mock_supabase_client()
        eq_chain = MagicMock()
        table.select.return_value = eq_chain
        eq_chain.eq.return_value = eq_chain
        eq_chain.limit.return_value = eq_chain
        eq_chain.execute.return_value = MagicMock(data=[{"messages_json": '[{"role":"user","content":"Test"}]'}])
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import load_conversation

            result = load_conversation("id")
        assert result == [{"role": "user", "content": "Test"}]


# ---------------------------------------------------------------------------
# delete_conversation
# ---------------------------------------------------------------------------
class TestDeleteConversation:
    def test_returns_false_when_client_none(self) -> None:
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=None),
            patch("src.ui.conversation_store._get_user_id", return_value=_TEST_USER_ID),
        ):
            from src.ui.conversation_store import delete_conversation

            assert delete_conversation("any-id") is False

    def test_returns_false_when_no_user_id(self) -> None:
        client, _ = _mock_supabase_client()
        with (
            patch("src.ui.conversation_store.get_supabase_client", return_value=client),
            patch("src.ui.conversation_store._get_user_id", return_value=None),
        ):
            from src.ui.conversation_store import delete_conversation

            assert delete_conversation("any-id") is False

    def test_returns_true_and_calls_delete(self) -> None:
        client, table = _mock_supabase_client()
        eq_chain = MagicMock()
        table.delete.return_value = eq_chain
        eq_chain.eq.return_value = eq_chain
        eq_chain.execute.return_value = MagicMock()
        p1, p2 = _patch_deps(client)
        with p1, p2:
            from src.ui.conversation_store import delete_conversation

            assert delete_conversation("conv-to-delete") is True
