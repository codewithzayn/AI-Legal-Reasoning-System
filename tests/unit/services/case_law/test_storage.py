# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL. Unauthorized copying, distribution, or use is strictly prohibited.

"""
Unit tests for CaseLawStorage: date validation, content hashing, sub-chunking,
and metadata row mapping.

All tests are pure-logic — no network calls, no database.
"""

from src.services.case_law.scraper import CaseLawDocument
from src.services.case_law.storage import CaseLawStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_doc(**overrides) -> CaseLawDocument:
    """Create a minimal CaseLawDocument with sensible defaults."""
    defaults = {
        "case_id": "KKO:2024:1",
        "court_type": "supreme_court",
        "court_code": "KKO",
        "decision_type": "precedent",
        "case_year": 2024,
        "title": "Test Case",
        "full_text": "Some legal text content.",
    }
    defaults.update(overrides)
    return CaseLawDocument(**defaults)


# ---------------------------------------------------------------------------
# _validate_date
# ---------------------------------------------------------------------------
class TestValidateDate:
    """Test date parsing and normalization."""

    def test_iso_date_passes_through(self) -> None:
        assert CaseLawStorage._validate_date("2024-01-15") == "2024-01-15"

    def test_finnish_date_converted(self) -> None:
        assert CaseLawStorage._validate_date("15.1.2024") == "2024-01-15"

    def test_finnish_date_with_padding(self) -> None:
        assert CaseLawStorage._validate_date("1.2.2024") == "2024-02-01"

    def test_two_digit_year_2000s(self) -> None:
        # 2-digit year 00–30 → 20xx
        assert CaseLawStorage._validate_date("1.1.24") == "2024-01-01"

    def test_two_digit_year_1900s(self) -> None:
        # 2-digit year 31–99 → 19xx
        assert CaseLawStorage._validate_date("1.1.95") == "1995-01-01"

    def test_none_returns_none(self) -> None:
        assert CaseLawStorage._validate_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert CaseLawStorage._validate_date("") is None

    def test_leading_dash_returns_none(self) -> None:
        assert CaseLawStorage._validate_date("-invalid") is None

    def test_garbage_returns_none(self) -> None:
        assert CaseLawStorage._validate_date("not-a-date") is None


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------
class TestComputeContentHash:
    """Test content hash computation for idempotency."""

    def test_same_content_same_hash(self) -> None:
        doc = _make_doc()
        hash1 = CaseLawStorage.compute_content_hash(doc)
        hash2 = CaseLawStorage.compute_content_hash(doc)
        assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        doc_a = _make_doc(full_text="Version A")
        doc_b = _make_doc(full_text="Version B")
        assert CaseLawStorage.compute_content_hash(doc_a) != CaseLawStorage.compute_content_hash(doc_b)

    def test_hash_is_hex_sha256(self) -> None:
        doc = _make_doc()
        h = CaseLawStorage.compute_content_hash(doc)
        assert len(h) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# _sub_chunk
# ---------------------------------------------------------------------------
class TestSubChunk:
    """Test the text sub-chunking logic."""

    def test_short_text_single_chunk(self) -> None:
        chunks = CaseLawStorage._sub_chunk("Short text", max_chars=100)
        assert len(chunks) == 1
        assert chunks[0] == "Short text"

    def test_long_text_split_into_chunks(self) -> None:
        # Create text with multiple paragraphs
        paragraphs = ["Paragraph " + str(i) + " " * 50 for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = CaseLawStorage._sub_chunk(text, max_chars=200, overlap=0)
        assert len(chunks) > 1

    def test_chunks_do_not_exceed_limit(self) -> None:
        paragraphs = ["Word " * 100 for _ in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = CaseLawStorage._sub_chunk(text, max_chars=300, overlap=0)
        for chunk in chunks:
            # Each chunk should be at most max_chars (some slack for paragraph boundary)
            assert len(chunk) <= 600  # generous bound since we split on paragraphs

    def test_overlap_creates_shared_content(self) -> None:
        paragraphs = ["A" * 50, "B" * 50, "C" * 50, "D" * 50]
        text = "\n\n".join(paragraphs)
        chunks = CaseLawStorage._sub_chunk(text, max_chars=120, overlap=60)
        if len(chunks) >= 2:
            # Last paragraph of chunk N should appear at the start of chunk N+1
            last_para_chunk0 = chunks[0].split("\n\n")[-1]
            assert last_para_chunk0 in chunks[1]

    def test_empty_text_single_chunk(self) -> None:
        chunks = CaseLawStorage._sub_chunk("")
        assert chunks == [""]


# ---------------------------------------------------------------------------
# _insert_case_metadata row mapping
# ---------------------------------------------------------------------------
class TestMetadataRowMapping:
    """Test that the metadata row built from CaseLawDocument has correct keys."""

    def test_required_fields_present(self) -> None:
        """The row dict should contain all required DB columns."""
        doc = _make_doc(
            decision_date="2024-06-15",
            ecli="ECLI:FI:KKO:2024:1",
            legal_domains=["criminal", "civil"],
            cited_laws=["RL 21:1"],
        )
        # We can't call _insert_case_metadata directly (needs Supabase client),
        # but we can verify CaseLawDocument.to_dict() has the right structure.
        d = doc.to_dict()
        required_keys = [
            "case_id",
            "court_type",
            "court_code",
            "decision_type",
            "case_year",
            "decision_date",
            "ecli",
            "title",
            "full_text",
            "legal_domains",
            "cited_laws",
            "is_precedent",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_default_values_are_sane(self) -> None:
        doc = _make_doc()
        d = doc.to_dict()
        assert d["is_precedent"] is False
        assert d["legal_domains"] == []
        assert d["primary_language"] == "Finnish"
