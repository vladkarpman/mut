"""Tests for AI recovery module."""

from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.ai_recovery import AIRecovery, AIRecoveryResult


class TestAIRecoveryResult:
    """Test AIRecoveryResult dataclass."""

    def test_default_values(self):
        """Test default values for optional fields."""
        result = AIRecoveryResult(action="fail", reason="Test")
        assert result.action == "fail"
        assert result.reason == "Test"
        assert result.wait_seconds is None
        assert result.alternative_target is None
        assert result.alternative_coords is None

    def test_all_values(self):
        """Test setting all values."""
        result = AIRecoveryResult(
            action="alternative",
            reason="Found similar",
            wait_seconds=2.0,
            alternative_target="Login",
            alternative_coords=(540, 1200),
        )
        assert result.action == "alternative"
        assert result.reason == "Found similar"
        assert result.wait_seconds == 2.0
        assert result.alternative_target == "Login"
        assert result.alternative_coords == (540, 1200)


class TestAIRecoveryInit:
    """Test AIRecovery initialization."""

    def test_is_available_depends_on_analyzer(self):
        """Availability should match analyzer availability."""
        mock_analyzer = MagicMock()
        mock_analyzer.is_available = True
        recovery = AIRecovery(mock_analyzer)
        assert recovery.is_available is True

        mock_analyzer.is_available = False
        assert recovery.is_available is False


class TestAnalyzeElementNotFound:
    """Test analyze_element_not_found method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock analyzer."""
        analyzer = MagicMock()
        analyzer.is_available = True
        analyzer._client = MagicMock()
        analyzer._model = "gemini-2.0-flash"
        return analyzer

    @pytest.fixture
    def recovery(self, mock_analyzer):
        """Create recovery with mocked analyzer."""
        return AIRecovery(mock_analyzer)

    def test_returns_fail_when_not_available(self, mock_analyzer):
        """Should return fail result when AI not available."""
        mock_analyzer.is_available = False
        recovery = AIRecovery(mock_analyzer)

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "fail"
        assert "unavailable" in result.reason.lower()

    def test_parses_retry_response(self, recovery, mock_analyzer):
        """Should parse retry response from AI."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "retry",
            "reason": "Screen is loading",
            "wait_seconds": 2,
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "retry"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "retry"
        assert result.wait_seconds == 2.0

    def test_parses_alternative_with_text(self, recovery, mock_analyzer):
        """Should parse alternative with different text."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "alternative",
            "reason": "Found similar element",
            "alternative": "LOG IN",
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "alternative"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Login",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "alternative"
        assert result.alternative_target == "LOG IN"

    def test_parses_alternative_with_coords(self, recovery, mock_analyzer):
        """Should parse alternative with coordinates."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "alternative",
            "reason": "Found element visually",
            "coordinates": [50, 30],
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "alternative"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "alternative"
        # Coords should be converted from percentages to pixels
        assert result.alternative_coords == (540, 702)  # 50% of 1080, 30% of 2340

    def test_parses_fail_response(self, recovery, mock_analyzer):
        """Should parse fail response."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "fail",
            "reason": "Wrong screen entirely",
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "fail"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "fail"
        assert "wrong screen" in result.reason.lower()

    def test_handles_api_error(self, recovery, mock_analyzer):
        """Should return fail on API error."""
        mock_analyzer._client.models.generate_content.side_effect = RuntimeError("API error")

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "fail"
        assert "error" in result.reason.lower()

    def test_validates_action_value(self, recovery, mock_analyzer):
        """Should default to fail for invalid action values."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "invalid_action",
            "reason": "Test",
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "invalid"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "fail"

    def test_clamps_wait_seconds(self, recovery, mock_analyzer):
        """Should use default wait when AI suggests unreasonable value."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "retry",
            "reason": "Loading",
            "wait_seconds": 100,  # Unreasonably high
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "retry"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_element_not_found(
            screenshot=b"fake",
            target="Button",
            action="tap",
            screen_size=(1080, 2340),
        )

        assert result.action == "retry"
        assert result.wait_seconds == 2.0  # Default value


class TestAnalyzeVerifyScreenFailed:
    """Test analyze_verify_screen_failed method."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock analyzer."""
        analyzer = MagicMock()
        analyzer.is_available = True
        analyzer._client = MagicMock()
        analyzer._model = "gemini-2.0-flash"
        return analyzer

    @pytest.fixture
    def recovery(self, mock_analyzer):
        """Create recovery with mocked analyzer."""
        return AIRecovery(mock_analyzer)

    def test_returns_fail_when_not_available(self, mock_analyzer):
        """Should return fail result when AI not available."""
        mock_analyzer.is_available = False
        recovery = AIRecovery(mock_analyzer)

        result = recovery.analyze_verify_screen_failed(
            screenshot=b"fake",
            description="Login screen",
            failure_reason="Not a login screen",
        )

        assert result.action == "fail"

    def test_parses_retry_response(self, recovery, mock_analyzer):
        """Should parse retry response for screen transition."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "retry",
            "reason": "Screen is transitioning",
            "wait_seconds": 1.5,
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "retry"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_verify_screen_failed(
            screenshot=b"fake",
            description="Home screen",
            failure_reason="Loading spinner visible",
        )

        assert result.action == "retry"
        assert result.wait_seconds == 1.5

    def test_parses_fail_response(self, recovery, mock_analyzer):
        """Should parse fail response for wrong screen."""
        mock_analyzer._parse_json_response.return_value = {
            "action": "fail",
            "reason": "Completely wrong screen",
        }
        mock_response = MagicMock()
        mock_response.text = '{"action": "fail"}'
        mock_analyzer._client.models.generate_content.return_value = mock_response

        result = recovery.analyze_verify_screen_failed(
            screenshot=b"fake",
            description="Home screen",
            failure_reason="Shows login instead",
        )

        assert result.action == "fail"
