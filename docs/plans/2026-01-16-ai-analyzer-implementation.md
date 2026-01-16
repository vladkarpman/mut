# AIAnalyzer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement AIAnalyzer with Gemini 2.5 Flash for verify_screen (deferred verification), if_screen (real-time branching), and analyze_step (recording workflow).

**Architecture:** AIAnalyzer wraps the google-genai client. Uses `types.Part.from_bytes()` for image input. Returns structured JSON responses parsed from model output. Gracefully handles missing API key by skipping verification.

**Tech Stack:** google-genai (Gemini API client), PIL (image handling)

---

## Prerequisites

Before starting, ensure:
- Virtual environment is activated: `source .venv/bin/activate`
- GOOGLE_API_KEY environment variable set (for integration tests)
- Project dependencies installed: `pip install -e ".[dev]"`

---

## Task 1: Test AIAnalyzer Initialization

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`

**Step 1: Write failing tests for initialization**

Create `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest tests/test_ai_analyzer.py::TestAIAnalyzerInit -v
```

Expected: Some tests may pass (stub already has basic logic), but we verify the structure is correct.

**Step 3: Update initialization in ai_analyzer.py**

Replace `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`:

```python
"""AI vision analysis using Gemini 2.5 Flash."""

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger("mut.ai")


class AIAnalyzer:
    """AI vision analysis using Gemini 2.5 Flash.

    Handles verify_screen, if_screen, and step analysis for test execution
    and recording workflows.

    Uses hybrid verification strategy:
    - verify_screen: Deferred (captures screenshot, continues, analyzes post-test)
    - if_screen: Real-time (immediate AI call for branching decisions)
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Initialize analyzer.

        Args:
            api_key: Google API key. If not provided, reads from GOOGLE_API_KEY env var.
            model: Model to use. Defaults to gemini-2.5-flash.
        """
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._model = model or self.DEFAULT_MODEL
        self._client: genai.Client | None = None

        if self._api_key:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize Gemini client."""
        try:
            self._client = genai.Client(api_key=self._api_key)
            logger.info(f"AIAnalyzer initialized with model: {self._model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if AI is available (API key configured)."""
        return self._api_key is not None

    def verify_screen(self, screenshot: bytes, description: str) -> dict[str, Any]:
        """Verify screen matches description.

        Args:
            screenshot: PNG image bytes
            description: Expected screen description

        Returns:
            Dict with pass (bool), reason (str), and optional skipped (bool)
        """
        raise NotImplementedError("verify_screen not yet implemented")

    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition.

        Args:
            screenshot: PNG image bytes
            condition: Condition to check

        Returns:
            True if condition is met
        """
        raise NotImplementedError("if_screen not yet implemented")

    def analyze_step(self, before: bytes, after: bytes) -> dict[str, Any]:
        """Analyze before/after frames to describe a step.

        Args:
            before: PNG image bytes before action
            after: PNG image bytes after action

        Returns:
            Dict with before, action, after descriptions and suggested_verification
        """
        raise NotImplementedError("analyze_step not yet implemented")
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ai_analyzer.py::TestAIAnalyzerInit -v
```

Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add tests/test_ai_analyzer.py mut/core/ai_analyzer.py
git commit -m "feat(ai): implement AIAnalyzer initialization with Gemini client"
```

---

## Task 2: Implement verify_screen Method

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`

**Step 1: Add unit tests for verify_screen**

Append to `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`:

```python
class TestVerifyScreen:
    """Test verify_screen method."""

    def test_returns_skipped_when_no_api_key(self):
        """Should return skipped result when no API key."""
        analyzer = AIAnalyzer(api_key=None)

        # Create a minimal PNG (1x1 pixel)
        from PIL import Image
        import io
        img = Image.new("RGB", (1, 1), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        screenshot = buffer.getvalue()

        result = analyzer.verify_screen(screenshot, "test description")

        assert result["pass"] is True
        assert result["skipped"] is True
        assert "skipped" in result["reason"].lower() or "no api key" in result["reason"].lower()

    @patch("mut.core.ai_analyzer.genai")
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
        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        screenshot = buffer.getvalue()

        result = analyzer.verify_screen(screenshot, "login form")

        assert result["pass"] is True
        assert result["reason"] == "Screen shows login form"
        mock_client.models.generate_content.assert_called_once()

    @patch("mut.core.ai_analyzer.genai")
    def test_handles_json_in_markdown_code_block(self, mock_genai):
        """Should extract JSON from markdown code blocks."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        # Gemini sometimes wraps JSON in markdown
        mock_response.text = '```json\n{"pass": false, "reason": "Not a login screen"}\n```'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.verify_screen(buffer.getvalue(), "login form")

        assert result["pass"] is False
        assert "Not a login screen" in result["reason"]

    @patch("mut.core.ai_analyzer.genai")
    def test_handles_api_error_gracefully(self, mock_genai):
        """Should handle API errors gracefully."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("API Error")

        analyzer = AIAnalyzer(api_key="test-key")

        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.verify_screen(buffer.getvalue(), "test")

        assert result["pass"] is False
        assert "error" in result["reason"].lower()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ai_analyzer.py::TestVerifyScreen -v
```

Expected: FAIL with NotImplementedError

**Step 3: Implement verify_screen method**

Update the `verify_screen` method in `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`:

```python
    def verify_screen(self, screenshot: bytes, description: str) -> dict[str, Any]:
        """Verify screen matches description.

        Args:
            screenshot: PNG image bytes
            description: Expected screen description

        Returns:
            Dict with pass (bool), reason (str), and optional skipped (bool)
        """
        if not self.is_available or self._client is None:
            return {
                "pass": True,
                "reason": "AI verification skipped (no API key)",
                "skipped": True,
            }

        prompt = f'''Analyze this mobile app screenshot.

Question: Does the screen show "{description}"?

Respond with JSON only (no markdown, no code blocks):
{{"pass": true/false, "reason": "brief explanation"}}'''

        try:
            # Create image part from bytes
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],
            )

            # Parse response
            return self._parse_json_response(response.text)

        except Exception as e:
            logger.error(f"verify_screen failed: {e}")
            return {
                "pass": False,
                "reason": f"AI verification error: {str(e)}",
                "error": True,
            }

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from model response, handling markdown code blocks."""
        # Strip whitespace
        text = text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            # Remove ```json or ``` prefix
            lines = text.split("\n")
            # Skip first line (```json) and last line (```)
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {text}")
            return {
                "pass": False,
                "reason": f"Failed to parse AI response: {text[:100]}",
                "error": True,
            }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ai_analyzer.py::TestVerifyScreen -v
```

Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add tests/test_ai_analyzer.py mut/core/ai_analyzer.py
git commit -m "feat(ai): implement verify_screen with Gemini API"
```

---

## Task 3: Implement if_screen Method

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`

**Step 1: Add tests for if_screen**

Append to `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`:

```python
class TestIfScreen:
    """Test if_screen method."""

    def test_returns_false_when_no_api_key(self):
        """Should return False when no API key (safe default)."""
        analyzer = AIAnalyzer(api_key=None)

        from PIL import Image
        import io
        img = Image.new("RGB", (1, 1))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.if_screen(buffer.getvalue(), "some condition")

        # When AI is unavailable, default to False (don't execute conditional branch)
        assert result is False

    @patch("mut.core.ai_analyzer.genai")
    def test_returns_true_when_condition_met(self, mock_genai):
        """Should return True when condition is met."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pass": true, "reason": "Condition met"}'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.if_screen(buffer.getvalue(), "login prompt visible")

        assert result is True

    @patch("mut.core.ai_analyzer.genai")
    def test_returns_false_when_condition_not_met(self, mock_genai):
        """Should return False when condition is not met."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pass": false, "reason": "Condition not met"}'
        mock_client.models.generate_content.return_value = mock_response

        analyzer = AIAnalyzer(api_key="test-key")

        from PIL import Image
        import io
        img = Image.new("RGB", (100, 100))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        result = analyzer.if_screen(buffer.getvalue(), "error dialog visible")

        assert result is False
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ai_analyzer.py::TestIfScreen -v
```

Expected: FAIL with NotImplementedError

**Step 3: Implement if_screen method**

Update the `if_screen` method in `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`:

```python
    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition for branching.

        This is a real-time check used for conditional execution.
        When AI is unavailable, returns False (safe default - don't execute branch).

        Args:
            screenshot: PNG image bytes
            condition: Condition to check

        Returns:
            True if condition is met, False otherwise
        """
        if not self.is_available or self._client is None:
            logger.warning(f"if_screen skipped (no API key): {condition}")
            return False

        result = self.verify_screen(screenshot, condition)
        return result.get("pass", False)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ai_analyzer.py::TestIfScreen -v
```

Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add tests/test_ai_analyzer.py mut/core/ai_analyzer.py
git commit -m "feat(ai): implement if_screen for real-time branching"
```

---

## Task 4: Implement analyze_step Method

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`

**Step 1: Add tests for analyze_step**

Append to `/Users/vladislavkarpman/Projects/mut/tests/test_ai_analyzer.py`:

```python
class TestAnalyzeStep:
    """Test analyze_step method."""

    def test_returns_skipped_when_no_api_key(self):
        """Should return skipped result when no API key."""
        analyzer = AIAnalyzer(api_key=None)

        from PIL import Image
        import io

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

    @patch("mut.core.ai_analyzer.genai")
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

        from PIL import Image
        import io

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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ai_analyzer.py::TestAnalyzeStep -v
```

Expected: FAIL with NotImplementedError

**Step 3: Implement analyze_step method**

Update the `analyze_step` method in `/Users/vladislavkarpman/Projects/mut/mut/core/ai_analyzer.py`:

```python
    def analyze_step(self, before: bytes, after: bytes) -> dict[str, Any]:
        """Analyze before/after frames to describe a step.

        Used in recording workflow to generate step descriptions and
        suggested verifications.

        Args:
            before: PNG image bytes before action
            after: PNG image bytes after action

        Returns:
            Dict with before, action, after descriptions and suggested_verification
        """
        if not self.is_available or self._client is None:
            return {
                "before": "Unknown (AI unavailable)",
                "action": "Unknown",
                "after": "Unknown",
                "suggested_verification": None,
                "skipped": True,
            }

        prompt = '''Compare these two mobile app screenshots (before and after an action).

The first image is BEFORE the action, the second is AFTER.

Describe:
1. What was the UI state before?
2. What action was likely performed?
3. What changed after?
4. What verification would confirm this step succeeded?

Respond with JSON only (no markdown, no code blocks):
{
  "before": "description of before state",
  "action": "description of action performed",
  "after": "description of after state",
  "suggested_verification": "verification description or null if not applicable"
}'''

        try:
            # Create image parts
            before_part = types.Part.from_bytes(
                data=before,
                mime_type="image/png",
            )
            after_part = types.Part.from_bytes(
                data=after,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[before_part, after_part, prompt],
            )

            return self._parse_json_response(response.text)

        except Exception as e:
            logger.error(f"analyze_step failed: {e}")
            return {
                "before": "Analysis failed",
                "action": "Unknown",
                "after": "Analysis failed",
                "suggested_verification": None,
                "error": str(e),
            }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ai_analyzer.py::TestAnalyzeStep -v
```

Expected: PASS (all 2 tests)

**Step 5: Commit**

```bash
git add tests/test_ai_analyzer.py mut/core/ai_analyzer.py
git commit -m "feat(ai): implement analyze_step for recording workflow"
```

---

## Task 5: Integration Test with Real API (Optional)

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_ai_integration.py`

**Step 1: Write integration test**

Create `/Users/vladislavkarpman/Projects/mut/tests/test_ai_integration.py`:

```python
"""Integration tests for AIAnalyzer with real Gemini API.

These tests require GOOGLE_API_KEY to be set and will be skipped otherwise.
They also require a connected Android device for screenshot capture.
"""

import os
import pytest

from mut.core.ai_analyzer import AIAnalyzer
from mut.core.scrcpy_service import ScrcpyService
from mut.core.device_controller import DeviceController


@pytest.fixture
def api_key():
    """Get API key from environment."""
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        pytest.skip("GOOGLE_API_KEY not set")
    return key


@pytest.fixture
def device_id():
    """Get first available device ID."""
    devices = DeviceController.list_devices()
    if not devices:
        pytest.skip("No Android device connected")
    return devices[0]["id"]


class TestAIIntegration:
    """Integration tests with real Gemini API."""

    def test_verify_screen_with_real_screenshot(self, api_key, device_id):
        """Test verify_screen with actual device screenshot."""
        # Connect to device
        scrcpy = ScrcpyService(device_id)
        scrcpy.connect()

        try:
            import time
            time.sleep(1)  # Wait for frames

            # Take screenshot
            screenshot = scrcpy.screenshot()

            # Create analyzer
            analyzer = AIAnalyzer(api_key=api_key)

            # Verify something generic that should be true
            result = analyzer.verify_screen(screenshot, "a mobile app screen")

            assert "pass" in result
            assert "reason" in result
            assert isinstance(result["pass"], bool)

        finally:
            scrcpy.disconnect()

    def test_if_screen_returns_boolean(self, api_key, device_id):
        """Test if_screen returns boolean with real API."""
        scrcpy = ScrcpyService(device_id)
        scrcpy.connect()

        try:
            import time
            time.sleep(1)

            screenshot = scrcpy.screenshot()
            analyzer = AIAnalyzer(api_key=api_key)

            result = analyzer.if_screen(screenshot, "any content visible")

            assert isinstance(result, bool)

        finally:
            scrcpy.disconnect()
```

**Step 2: Run integration tests (if API key available)**

```bash
# Only run if you have GOOGLE_API_KEY set
GOOGLE_API_KEY=your-key pytest tests/test_ai_integration.py -v
```

Expected: PASS (or SKIPPED if no API key/device)

**Step 3: Commit**

```bash
git add tests/test_ai_integration.py
git commit -m "test(ai): add integration tests for real Gemini API"
```

---

## Task 6: Run All Tests and Push

**Step 1: Run all tests**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest -v
```

Expected: All unit tests pass, integration tests skipped (unless device + API key available)

**Step 2: Run type checking**

```bash
mypy mut/core/ai_analyzer.py
```

Expected: No errors (or minimal warnings)

**Step 3: Push to GitHub**

```bash
git push origin main
```

---

## Summary

After completing all tasks:
- ✅ AIAnalyzer initializes with Gemini client
- ✅ verify_screen analyzes screenshots against descriptions
- ✅ if_screen provides real-time branching decisions
- ✅ analyze_step describes before/after for recording workflow
- ✅ Graceful fallback when API key not available
- ✅ JSON response parsing handles markdown code blocks
- ✅ All tests pass

**Next phase:** TestExecutor implementation (YAML parsing, step execution with hybrid verification)

---

## API Reference

Based on [google-genai documentation](https://github.com/googleapis/python-genai):

```python
from google import genai
from google.genai import types

# Initialize client
client = genai.Client(api_key="your-key")

# Send image for analysis
image_part = types.Part.from_bytes(
    data=png_bytes,
    mime_type="image/png",
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[image_part, "Your prompt here"],
)

# Get text response
print(response.text)
```
