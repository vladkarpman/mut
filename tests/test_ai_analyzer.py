"""Tests for AIAnalyzer."""

import os
from unittest.mock import MagicMock, patch

from mutcli.core.ai_analyzer import AIAnalyzer


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


class TestVerifyScreen:
    """Test verify_screen method."""

    def test_returns_skipped_when_no_api_key(self):
        """Should return skipped result when no API key."""
        # Clear GOOGLE_API_KEY to ensure no API key is available
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            # Create a minimal PNG (1x1 pixel)
            import io

            from PIL import Image
            img = Image.new("RGB", (1, 1), color="red")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            screenshot = buffer.getvalue()

            result = analyzer.verify_screen(screenshot, "test description")

            assert result["pass"] is True
            assert result["skipped"] is True
            assert "skipped" in result["reason"].lower() or "no api key" in result["reason"].lower()

    @patch("mutcli.core.ai_analyzer.genai")
    def test_calls_gemini_api_with_image(self, mock_genai):
        """Should call Gemini API with image and prompt."""
        # Setup mock
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pass": true, "reason": "Screen shows login form"}'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        # Create test image
        import io

        from PIL import Image
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        screenshot = buffer.getvalue()

        result = analyzer.verify_screen(screenshot, "login form")

        assert result["pass"] is True
        assert result["reason"] == "Screen shows login form"
        mock_client.models.generate_content.assert_called_once()

    @patch("mutcli.core.ai_analyzer.genai")
    def test_handles_json_in_markdown_code_block(self, mock_genai):
        """Should extract JSON from markdown code blocks."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '```json\n{"pass": false, "reason": "Not a login screen"}\n```'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        import io

        from PIL import Image
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.verify_screen(buffer.getvalue(), "login form")

        assert result["pass"] is False
        assert "Not a login screen" in result["reason"]

    @patch("mutcli.core.ai_analyzer.genai")
    def test_handles_api_error_gracefully(self, mock_genai):
        """Should handle API errors gracefully."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("API Error")

        analyzer = AIAnalyzer(api_key="test-key")

        import io

        from PIL import Image
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.verify_screen(buffer.getvalue(), "test")

        assert result["pass"] is False
        assert "error" in result["reason"].lower()


class TestIfScreen:
    """Test if_screen method."""

    def test_returns_false_when_no_api_key(self):
        """Should return False when no API key (safe default)."""
        # Clear GOOGLE_API_KEY to ensure no API key is available
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            import io

            from PIL import Image
            img = Image.new("RGB", (1, 1))
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")

            result = analyzer.if_screen(buffer.getvalue(), "some condition")

            # When AI is unavailable, default to False (don't execute conditional branch)
            assert result is False

    @patch("mutcli.core.ai_analyzer.genai")
    def test_returns_true_when_condition_met(self, mock_genai):
        """Should return True when condition is met."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pass": true, "reason": "Condition met"}'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        import io

        from PIL import Image
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.if_screen(buffer.getvalue(), "login prompt visible")

        assert result is True

    @patch("mutcli.core.ai_analyzer.genai")
    def test_returns_false_when_condition_not_met(self, mock_genai):
        """Should return False when condition is not met."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pass": false, "reason": "Condition not met"}'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        import io

        from PIL import Image
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.if_screen(buffer.getvalue(), "error dialog visible")

        assert result is False


class TestAnalyzeStep:
    """Test analyze_step method."""

    def test_returns_skipped_when_no_api_key(self):
        """Should return skipped result when no API key."""
        # Clear GOOGLE_API_KEY to ensure no API key is available
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            import io

            from PIL import Image

            def make_image():
                img = Image.new("RGB", (100, 100))
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue()

            result = analyzer.analyze_step(make_image(), make_image())

            assert result["skipped"] is True
            assert "before" in result
            assert "action" in result
            assert "after" in result

    @patch("mutcli.core.ai_analyzer.genai")
    def test_analyzes_before_after_frames(self, mock_genai):
        """Should analyze before/after frames and return descriptions."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '''{
            "before": "Login screen with empty form",
            "action": "User tapped on email field",
            "after": "Keyboard appeared, email field focused",
            "suggested_verification": "keyboard is visible"
        }'''
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        import io

        from PIL import Image

        def make_image(color):
            img = Image.new("RGB", (100, 100), color=color)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        result = analyzer.analyze_step(make_image("white"), make_image("blue"))

        assert result["before"] == "Login screen with empty form"
        assert result["action"] == "User tapped on email field"
        assert result["after"] == "Keyboard appeared, email field focused"
        assert result["suggested_verification"] == "keyboard is visible"

        # Verify API was called with two images
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
        # Should have 2 image parts + 1 text prompt
        assert len(contents) == 3
