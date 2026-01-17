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


# Helper function to create test images
def _make_test_image(color: str = "white") -> bytes:
    """Create a minimal test PNG image."""
    import io

    from PIL import Image
    img = Image.new("RGB", (100, 100), color=color)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestAnalyzeTap:
    """Test async analyze_tap method."""

    import pytest

    @pytest.mark.asyncio
    async def test_returns_default_when_no_api_key(self):
        """Should return default TapAnalysisResult when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            result = await analyzer.analyze_tap(
                before=_make_test_image(),
                touch=_make_test_image("blue"),
                after=_make_test_image("green"),
                x=540,
                y=1200,
            )

            assert result["element_text"] is None
            assert result["element_type"] == "other"
            assert "unavailable" in result["before_description"].lower()
            assert "unavailable" in result["after_description"].lower()
            assert result["suggested_verification"] is None

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_successful_api_call(self, mock_genai):
        """Should parse successful API response correctly."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Mock the async response
        mock_response = MagicMock()
        mock_response.text = '''{
            "element_text": "Login",
            "element_type": "button",
            "before_description": "Login screen with form",
            "after_description": "Loading indicator shown",
            "suggested_verification": "loading indicator visible"
        }'''

        # Create async mock for aio.models.generate_content
        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_client.aio.models.generate_content = mock_generate

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_tap(
            before=_make_test_image(),
            touch=_make_test_image("blue"),
            after=_make_test_image("green"),
            x=540,
            y=1200,
        )

        assert result["element_text"] == "Login"
        assert result["element_type"] == "button"
        assert result["before_description"] == "Login screen with form"
        assert result["after_description"] == "Loading indicator shown"
        assert result["suggested_verification"] == "loading indicator visible"

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_handles_api_error(self, mock_genai):
        """Should return error state when API call fails."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        # Create async mock that raises an exception
        async def mock_generate_error(*args, **kwargs):
            raise Exception("API connection failed")

        mock_client.aio.models.generate_content = mock_generate_error

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_tap(
            before=_make_test_image(),
            touch=_make_test_image("blue"),
            after=_make_test_image("green"),
            x=540,
            y=1200,
        )

        assert result["element_text"] is None
        assert result["element_type"] == "other"
        assert "failed" in result["before_description"].lower()
        assert "failed" in result["after_description"].lower()


class TestAnalyzeSwipe:
    """Test async analyze_swipe method."""

    import pytest

    @pytest.mark.asyncio
    async def test_returns_default_when_no_api_key(self):
        """Should return default SwipeAnalysisResult when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            result = await analyzer.analyze_swipe(
                before=_make_test_image(),
                swipe_start=_make_test_image("blue"),
                swipe_end=_make_test_image("green"),
                after=_make_test_image("red"),
                start_x=540,
                start_y=1500,
                end_x=540,
                end_y=500,
            )

            assert result["direction"] == "unknown"
            assert "unavailable" in result["content_changed"].lower()
            assert "unavailable" in result["before_description"].lower()
            assert "unavailable" in result["after_description"].lower()
            assert result["suggested_verification"] is None

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_successful_api_call(self, mock_genai):
        """Should parse successful API response correctly."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '''{
            "direction": "up",
            "content_changed": "More items scrolled into view",
            "before_description": "List showing items 1-5",
            "after_description": "List showing items 6-10",
            "suggested_verification": "item 6 visible"
        }'''

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_client.aio.models.generate_content = mock_generate

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_swipe(
            before=_make_test_image(),
            swipe_start=_make_test_image("blue"),
            swipe_end=_make_test_image("green"),
            after=_make_test_image("red"),
            start_x=540,
            start_y=1500,
            end_x=540,
            end_y=500,
        )

        assert result["direction"] == "up"
        assert result["content_changed"] == "More items scrolled into view"
        assert result["before_description"] == "List showing items 1-5"
        assert result["after_description"] == "List showing items 6-10"
        assert result["suggested_verification"] == "item 6 visible"

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_handles_api_error(self, mock_genai):
        """Should return error state when API call fails."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        async def mock_generate_error(*args, **kwargs):
            raise Exception("Network timeout")

        mock_client.aio.models.generate_content = mock_generate_error

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_swipe(
            before=_make_test_image(),
            swipe_start=_make_test_image("blue"),
            swipe_end=_make_test_image("green"),
            after=_make_test_image("red"),
            start_x=540,
            start_y=1500,
            end_x=540,
            end_y=500,
        )

        assert result["direction"] == "unknown"
        assert "failed" in result["content_changed"].lower()
        assert "failed" in result["before_description"].lower()
        assert "failed" in result["after_description"].lower()


class TestAnalyzeLongPress:
    """Test async analyze_long_press method."""

    import pytest

    @pytest.mark.asyncio
    async def test_returns_default_when_no_api_key(self):
        """Should return default LongPressAnalysisResult when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            result = await analyzer.analyze_long_press(
                before=_make_test_image(),
                press_start=_make_test_image("blue"),
                press_held=_make_test_image("green"),
                after=_make_test_image("red"),
                x=540,
                y=800,
                duration_ms=1000,
            )

            assert result["element_text"] is None
            assert result["element_type"] == "other"
            assert result["result_type"] == "other"
            assert "unavailable" in result["before_description"].lower()
            assert "unavailable" in result["after_description"].lower()
            assert result["suggested_verification"] is None

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_successful_api_call(self, mock_genai):
        """Should parse successful API response correctly."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '''{
            "element_text": "Photo 1",
            "element_type": "image",
            "result_type": "context_menu",
            "before_description": "Photo gallery grid",
            "after_description": "Context menu with options: Share, Delete, Edit",
            "suggested_verification": "context menu visible"
        }'''

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_client.aio.models.generate_content = mock_generate

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_long_press(
            before=_make_test_image(),
            press_start=_make_test_image("blue"),
            press_held=_make_test_image("green"),
            after=_make_test_image("red"),
            x=540,
            y=800,
            duration_ms=1000,
        )

        assert result["element_text"] == "Photo 1"
        assert result["element_type"] == "image"
        assert result["result_type"] == "context_menu"
        assert result["before_description"] == "Photo gallery grid"
        assert result["after_description"] == "Context menu with options: Share, Delete, Edit"
        assert result["suggested_verification"] == "context menu visible"

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_handles_api_error(self, mock_genai):
        """Should return error state when API call fails."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        async def mock_generate_error(*args, **kwargs):
            raise Exception("Service unavailable")

        mock_client.aio.models.generate_content = mock_generate_error

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_long_press(
            before=_make_test_image(),
            press_start=_make_test_image("blue"),
            press_held=_make_test_image("green"),
            after=_make_test_image("red"),
            x=540,
            y=800,
            duration_ms=1000,
        )

        assert result["element_text"] is None
        assert result["element_type"] == "other"
        assert result["result_type"] == "other"
        assert "failed" in result["before_description"].lower()
        assert "failed" in result["after_description"].lower()


class TestAnalyzeType:
    """Test async analyze_type method."""

    import pytest

    @pytest.mark.asyncio
    async def test_returns_default_when_no_api_key(self):
        """Should return default TypeAnalysisResult when no API key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_API_KEY", None)
            analyzer = AIAnalyzer(api_key=None)

            result = await analyzer.analyze_type(
                before=_make_test_image(),
                after=_make_test_image("green"),
            )

            assert result["element_text"] is None
            assert result["element_type"] == "other"
            assert "unavailable" in result["before_description"].lower()
            assert "unavailable" in result["after_description"].lower()
            assert result["suggested_verification"] is None

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_successful_api_call(self, mock_genai):
        """Should parse successful API response correctly."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '''{
            "element_text": "Search field",
            "element_type": "search_box",
            "before_description": "Search screen with empty search field and keyboard",
            "after_description": "Search field contains 'test query'",
            "suggested_verification": "search field contains text"
        }'''

        async def mock_generate(*args, **kwargs):
            return mock_response

        mock_client.aio.models.generate_content = mock_generate

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_type(
            before=_make_test_image(),
            after=_make_test_image("green"),
        )

        assert result["element_text"] == "Search field"
        assert result["element_type"] == "search_box"
        assert result["before_description"] == "Search screen with empty search field and keyboard"
        assert result["after_description"] == "Search field contains 'test query'"
        assert result["suggested_verification"] == "search field contains text"

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_handles_api_error(self, mock_genai):
        """Should return error state when API call fails."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        async def mock_generate_error(*args, **kwargs):
            raise Exception("API rate limit exceeded")

        mock_client.aio.models.generate_content = mock_generate_error

        analyzer = AIAnalyzer(api_key="test-key")

        result = await analyzer.analyze_type(
            before=_make_test_image(),
            after=_make_test_image("green"),
        )

        assert result["element_text"] is None
        assert result["element_type"] == "other"
        assert "failed" in result["before_description"].lower()
        assert "failed" in result["after_description"].lower()

    @pytest.mark.asyncio
    @patch("mutcli.core.ai_analyzer.genai")
    async def test_uses_only_two_frames(self, mock_genai):
        """Should send exactly 2 images (before, after) to API."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = '''{
            "element_text": "Email input",
            "element_type": "text_field",
            "before_description": "Login form",
            "after_description": "Email entered",
            "suggested_verification": null
        }'''

        captured_contents = []

        async def mock_generate(*args, **kwargs):
            captured_contents.append(kwargs.get("contents"))
            return mock_response

        mock_client.aio.models.generate_content = mock_generate

        analyzer = AIAnalyzer(api_key="test-key")

        await analyzer.analyze_type(
            before=_make_test_image("white"),
            after=_make_test_image("blue"),
        )

        # Should have 2 image parts + 1 text prompt = 3 total
        assert len(captured_contents) == 1
        contents = captured_contents[0]
        assert len(contents) == 3
