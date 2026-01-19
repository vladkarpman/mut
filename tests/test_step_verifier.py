# tests/test_step_verifier.py
"""Tests for StepVerifier AI analysis."""

from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.step_verifier import StepAnalysis, StepVerifier


class TestStepVerifier:
    """Test StepVerifier functionality."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create a mock AIAnalyzer."""
        analyzer = MagicMock()
        analyzer.is_available = True
        analyzer._model = "test-model"
        return analyzer

    @pytest.fixture
    def verifier(self, mock_analyzer):
        """Create StepVerifier with mock analyzer."""
        return StepVerifier(mock_analyzer)

    def test_is_available_when_analyzer_available(self, verifier, mock_analyzer):
        """is_available reflects analyzer availability."""
        mock_analyzer.is_available = True
        assert verifier.is_available is True

        mock_analyzer.is_available = False
        assert verifier.is_available is False

    def test_analyze_step_returns_placeholder_when_unavailable(self, mock_analyzer):
        """Returns placeholder analysis when AI is unavailable."""
        mock_analyzer.is_available = False
        verifier = StepVerifier(mock_analyzer)

        result = verifier.analyze_step(
            action="tap",
            target="button",
            description="Tap the button",
            reported_status="passed",
            error=None,
            screenshot_before=b"before",
            screenshot_after=b"after",
        )

        assert result.verified is True
        assert result.outcome_description == "AI analysis unavailable"
        assert result.suggestion is None

    def test_analyze_step_returns_failure_placeholder_when_unavailable(
        self, mock_analyzer
    ):
        """Returns failure placeholder when AI unavailable and step failed."""
        mock_analyzer.is_available = False
        verifier = StepVerifier(mock_analyzer)

        result = verifier.analyze_step(
            action="tap",
            target="button",
            description="Tap the button",
            reported_status="failed",
            error="Element not found",
            screenshot_before=b"before",
            screenshot_after=b"after",
        )

        assert result.verified is False
        assert result.outcome_description == "AI analysis unavailable"

    @patch("google.genai.types")
    def test_analyze_step_calls_ai(self, mock_types, mock_analyzer):
        """analyze_step calls AI with correct prompt."""
        mock_analyzer._client = MagicMock()
        mock_analyzer._parse_json_response = MagicMock(
            return_value={
                "verified": True,
                "outcome": "Button was tapped successfully",
                "suggestion": None,
            }
        )

        verifier = StepVerifier(mock_analyzer)

        result = verifier.analyze_step(
            action="tap",
            target="Submit",
            description="Tap Submit button",
            reported_status="passed",
            error=None,
            screenshot_before=b"before",
            screenshot_after=b"after",
        )

        # Check AI was called
        assert mock_analyzer._client.models.generate_content.called

        # Check result
        assert result.verified is True
        assert result.outcome_description == "Button was tapped successfully"
        assert result.suggestion is None

    def test_analyze_all_steps_empty_list(self, verifier):
        """analyze_all_steps handles empty list."""
        result = verifier.analyze_all_steps([])
        assert result == []

    def test_analyze_all_steps_missing_screenshots(self, verifier):
        """Creates placeholder for steps without screenshots."""
        steps = [
            {
                "action": "tap",
                "target": "button",
                "status": "passed",
                "error": None,
                "screenshot_before": None,
                "screenshot_after": None,
            }
        ]

        results = verifier.analyze_all_steps(steps)

        assert len(results) == 1
        assert results[0].verified is True
        assert "missing screenshots" in results[0].outcome_description


class TestStepAnalysis:
    """Test StepAnalysis dataclass."""

    def test_step_analysis_creation(self):
        """Can create StepAnalysis with all fields."""
        analysis = StepAnalysis(
            verified=True,
            outcome_description="Step completed successfully",
            suggestion=None,
        )

        assert analysis.verified is True
        assert analysis.outcome_description == "Step completed successfully"
        assert analysis.suggestion is None

    def test_step_analysis_with_suggestion(self):
        """Can create StepAnalysis with suggestion."""
        analysis = StepAnalysis(
            verified=False,
            outcome_description="Element not found",
            suggestion="Try using a different selector",
        )

        assert analysis.verified is False
        assert analysis.suggestion == "Try using a different selector"
