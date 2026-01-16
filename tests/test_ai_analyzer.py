"""Tests for AIAnalyzer."""

import os
import pytest
from unittest.mock import patch, MagicMock

from mut.core.ai_analyzer import AIAnalyzer


class TestAIAnalyzerInit:
    """Test AIAnalyzer initialization."""

    def test_is_available_false_without_api_key(self):
        """Should return False when no API key is set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove GOOGLE_API_KEY if present
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)
            assert analyzer.is_available is False

    def test_is_available_true_with_api_key(self):
        """Should return True when API key is provided."""
        analyzer = AIAnalyzer(api_key="test-api-key")
        assert analyzer.is_available is True

    def test_reads_api_key_from_env(self):
        """Should read API key from GOOGLE_API_KEY env var."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "env-api-key"}):
            analyzer = AIAnalyzer()
            assert analyzer.is_available is True

    def test_explicit_api_key_overrides_env(self):
        """Explicit API key should override env var."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "env-key"}):
            analyzer = AIAnalyzer(api_key="explicit-key")
            assert analyzer._api_key == "explicit-key"
