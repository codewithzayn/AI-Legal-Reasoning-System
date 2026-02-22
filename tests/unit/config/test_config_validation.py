"""
Unit tests for config cross-field validation.

Verifies that validate_config_dependencies() catches misconfiguration
before it causes silent runtime failures.
"""

import os
from unittest.mock import patch


def _run_validation(**overrides):
    """Run validate_config_dependencies with specific config attribute overrides."""
    import importlib

    import src.config.settings as settings_mod

    # Reload settings to pick up env changes
    importlib.reload(settings_mod)

    # Patch individual config attributes for the test
    for attr, value in overrides.items():
        setattr(settings_mod.config, attr, value)

    return settings_mod.validate_config_dependencies()


class TestConditionalApiKeys:
    def test_no_errors_with_valid_defaults(self):
        env = {
            "OPENAI_API_KEY": "sk-test",
            "SUPABASE_URL": "http://localhost:54321",
            "SUPABASE_KEY": "test-key",
            "RERANK_ENABLED": "false",
            "USE_AI_EXTRACTION": "false",
            "EU_CASE_LAW_ENABLED": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            errors = _run_validation()
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_ai_extraction_requires_openai_key(self):
        env = {
            "OPENAI_API_KEY": "",
            "USE_AI_EXTRACTION": "true",
            "RERANK_ENABLED": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            errors = _run_validation(USE_AI_EXTRACTION=True)
        assert any("USE_AI_EXTRACTION" in e for e in errors)

    def test_rerank_enabled_requires_cohere_key(self):
        env = {
            "COHERE_API_KEY": "",
            "RERANK_ENABLED": "true",
            "USE_AI_EXTRACTION": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            errors = _run_validation(RERANK_ENABLED=True)
        assert any("COHERE_API_KEY" in e for e in errors)

    def test_rerank_disabled_does_not_require_cohere_key(self):
        env = {
            "COHERE_API_KEY": "",
            "RERANK_ENABLED": "false",
            "USE_AI_EXTRACTION": "false",
            "OPENAI_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=False):
            errors = _run_validation(RERANK_ENABLED=False)
        cohere_errors = [e for e in errors if "COHERE_API_KEY" in e]
        assert cohere_errors == []


class TestNumericRanges:
    def test_match_threshold_must_be_between_0_and_1(self):
        errors = _run_validation(MATCH_THRESHOLD=1.5)
        assert any("MATCH_THRESHOLD" in e for e in errors)

    def test_match_threshold_zero_is_invalid(self):
        errors = _run_validation(MATCH_THRESHOLD=0.0)
        assert any("MATCH_THRESHOLD" in e for e in errors)

    def test_valid_match_threshold_produces_no_error(self):
        errors = _run_validation(MATCH_THRESHOLD=0.3)
        threshold_errors = [e for e in errors if "MATCH_THRESHOLD" in e]
        assert threshold_errors == []

    def test_chunk_size_must_be_positive(self):
        errors = _run_validation(CHUNK_SIZE=0)
        assert any("CHUNK_SIZE" in e for e in errors)

    def test_chunk_min_size_must_be_less_than_chunk_size(self):
        errors = _run_validation(CHUNK_SIZE=100, CHUNK_MIN_SIZE=200)
        assert any("CHUNK_MIN_SIZE" in e and "CHUNK_SIZE" in e for e in errors)

    def test_llm_max_tokens_must_be_positive(self):
        errors = _run_validation(LLM_MAX_TOKENS=0)
        assert any("LLM_MAX_TOKENS" in e for e in errors)

    def test_embedding_dimensions_must_be_positive(self):
        errors = _run_validation(EMBEDDING_DIMENSIONS=-1)
        assert any("EMBEDDING_DIMENSIONS" in e for e in errors)


class TestModelNameChecks:
    def test_empty_chat_model_is_an_error(self):
        errors = _run_validation(OPENAI_CHAT_MODEL="")
        assert any("OPENAI_CHAT_MODEL" in e for e in errors)

    def test_empty_embedding_model_is_an_error(self):
        errors = _run_validation(EMBEDDING_MODEL="")
        assert any("EMBEDDING_MODEL" in e for e in errors)

    def test_empty_extraction_model_is_an_error(self):
        errors = _run_validation(EXTRACTION_MODEL="")
        assert any("EXTRACTION_MODEL" in e for e in errors)


class TestRerankConsistency:
    def test_rerank_max_docs_must_be_gte_rerank_top_k(self):
        errors = _run_validation(RERANK_MAX_DOCS=5, RERANK_TOP_K=10)
        assert any("RERANK_MAX_DOCS" in e for e in errors)

    def test_valid_rerank_settings_produce_no_error(self):
        errors = _run_validation(RERANK_MAX_DOCS=50, RERANK_TOP_K=10)
        rerank_errors = [e for e in errors if "RERANK_MAX_DOCS" in e]
        assert rerank_errors == []
