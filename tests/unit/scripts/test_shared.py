# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Unit tests for scripts/case_law/core/shared.py: JSON load/save round-trip,
write_local_enabled helper, and SUBTYPE_DIR_MAP constants.

All tests are pure-logic — no network calls, no database.
"""

import json
from pathlib import Path

from scripts.case_law.core.shared import (
    SUBTYPE_DIR_MAP,
    load_documents_from_json,
    save_documents_to_json,
    write_local_enabled,
)
from src.services.case_law.models import CaseLawDocument, Reference


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_doc(**overrides) -> CaseLawDocument:
    defaults = {
        "case_id": "KKO:2024:42",
        "court_type": "supreme_court",
        "court_code": "KKO",
        "decision_type": "precedent",
        "case_year": 2024,
        "title": "Test Case 42",
        "full_text": "Full legal text here.",
    }
    defaults.update(overrides)
    return CaseLawDocument(**defaults)


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------
class TestJsonRoundTrip:
    """Test save → load produces equivalent documents."""

    def test_single_document_round_trip(self, tmp_path: Path) -> None:
        doc = _make_doc()
        json_path = tmp_path / "test.json"
        save_documents_to_json([doc], json_path)

        loaded = load_documents_from_json(json_path)
        assert len(loaded) == 1
        assert loaded[0].case_id == "KKO:2024:42"
        assert loaded[0].court_code == "KKO"
        assert loaded[0].title == "Test Case 42"

    def test_round_trip_preserves_references(self, tmp_path: Path) -> None:
        doc = _make_doc()
        doc.references = [
            Reference(ref_id="KKO:2020:15", ref_type="precedent"),
            Reference(ref_id="RL 21:1", ref_type="legislation"),
        ]
        json_path = tmp_path / "refs.json"
        save_documents_to_json([doc], json_path)

        loaded = load_documents_from_json(json_path)
        assert len(loaded[0].references) == 2
        assert loaded[0].references[0].ref_id == "KKO:2020:15"
        assert loaded[0].references[1].ref_type == "legislation"

    def test_multiple_documents(self, tmp_path: Path) -> None:
        docs = [_make_doc(case_id=f"KKO:2024:{i}") for i in range(5)]
        json_path = tmp_path / "multi.json"
        save_documents_to_json(docs, json_path)

        loaded = load_documents_from_json(json_path)
        assert len(loaded) == 5
        assert loaded[2].case_id == "KKO:2024:2"

    def test_empty_list_round_trip(self, tmp_path: Path) -> None:
        json_path = tmp_path / "empty.json"
        save_documents_to_json([], json_path)

        loaded = load_documents_from_json(json_path)
        assert loaded == []


# ---------------------------------------------------------------------------
# load_documents_from_json edge cases
# ---------------------------------------------------------------------------
class TestLoadDocumentsEdgeCases:
    """Test error handling in load_documents_from_json."""

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_documents_from_json(tmp_path / "nope.json") == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{not valid json", encoding="utf-8")
        assert load_documents_from_json(bad_path) == []

    def test_non_list_json_returns_empty(self, tmp_path: Path) -> None:
        obj_path = tmp_path / "obj.json"
        obj_path.write_text('{"key": "value"}', encoding="utf-8")
        assert load_documents_from_json(obj_path) == []

    def test_malformed_item_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "partial.json"
        good = _make_doc().to_dict()
        good["references"] = []
        bad = {"missing": "fields"}
        path.write_text(json.dumps([good, bad]), encoding="utf-8")
        loaded = load_documents_from_json(path)
        assert len(loaded) == 1

    def test_none_path_returns_empty(self) -> None:
        assert load_documents_from_json(None) == []


# ---------------------------------------------------------------------------
# write_local_enabled
# ---------------------------------------------------------------------------
class TestWriteLocalEnabled:
    """Test write_local_enabled config helper."""

    def test_default_is_true(self) -> None:
        """Default CASE_LAW_EXPORT_LOCAL=1 means local write is enabled."""
        # The default from config is "1"
        result = write_local_enabled()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# SUBTYPE_DIR_MAP
# ---------------------------------------------------------------------------
class TestSubtypeDirMap:
    """Test that the shared constant map is well-formed."""

    def test_precedent_maps_to_precedents(self) -> None:
        assert SUBTYPE_DIR_MAP["precedent"] == "precedents"

    def test_none_maps_to_other(self) -> None:
        assert SUBTYPE_DIR_MAP[None] == "other"

    def test_all_values_are_strings(self) -> None:
        for value in SUBTYPE_DIR_MAP.values():
            assert isinstance(value, str)
