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
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            # Parse response
            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"verify_screen failed: {e}")
            return {
                "pass": False,
                "reason": f"AI verification error: {str(e)}",
                "error": True,
            }

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
        return bool(result.get("pass", False))

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
                contents=[before_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"analyze_step failed: {e}")
            return {
                "before": "Analysis failed",
                "action": "Unknown",
                "after": "Analysis failed",
                "suggested_verification": None,
                "error": str(e),
            }

    def find_element(
        self, screenshot: bytes, description: str, screen_width: int, screen_height: int
    ) -> tuple[int, int] | None:
        """Find element on screen by description.

        Uses AI vision to locate an element matching the description.

        Args:
            screenshot: PNG image bytes
            description: Element description (e.g., "login button", "email field")
            screen_width: Screen width in pixels (for coordinate calculation)
            screen_height: Screen height in pixels (for coordinate calculation)

        Returns:
            (x, y) pixel coordinates of element center, or None if not found
        """
        if not self.is_available or self._client is None:
            logger.warning(f"find_element skipped (no API key): {description}")
            return None

        prompt = f'''Find the UI element described as "{description}" in this mobile app screenshot.

The screen dimensions are {screen_width}x{screen_height} pixels.

If you find the element, respond with its CENTER coordinates as percentages of screen dimensions.
If you cannot find the element, respond with null coordinates.

Respond with JSON only (no markdown, no code blocks):
{{"found": true/false, "x_percent": 0-100 or null, "y_percent": 0-100 or null,
"reason": "brief explanation"}}'''

        try:
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            if result.get("found") and result.get("x_percent") and result.get("y_percent"):
                x = int(float(result["x_percent"]) * screen_width / 100)
                y = int(float(result["y_percent"]) * screen_height / 100)
                logger.info(f"AI found '{description}' at ({x}, {y})")
                return (x, y)

            logger.info(f"AI could not find '{description}': {result.get('reason', 'unknown')}")
            return None

        except Exception as e:
            logger.error(f"find_element failed: {e}")
            return None

    def validate_element_at(
        self, screenshot: bytes, description: str, x_percent: float, y_percent: float
    ) -> dict[str, Any]:
        """Validate that element at coordinates matches description.

        Used when 'at:' coordinates are provided with text description.

        Args:
            screenshot: PNG image bytes
            description: Expected element description
            x_percent: X coordinate as percentage (0-100)
            y_percent: Y coordinate as percentage (0-100)

        Returns:
            Dict with valid (bool), reason (str)
        """
        if not self.is_available or self._client is None:
            return {"valid": True, "reason": "Validation skipped (no API key)", "skipped": True}

        prompt = f'''Look at the UI element at approximately ({x_percent:.0f}%, {y_percent:.0f}%)
of the screen in this mobile app screenshot.

The coordinates are percentages from the top-left corner.

Question: Is there a "{description}" at or near those coordinates?

Respond with JSON only (no markdown, no code blocks):
{{"valid": true/false, "reason": "brief explanation of what is actually at those coordinates"}}'''

        try:
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"validate_element_at failed: {e}")
            return {"valid": False, "reason": f"Validation error: {str(e)}", "error": True}

    def analyze_image(self, image_data: bytes, prompt: str) -> str | None:
        """Analyze image with custom prompt.

        Args:
            image_data: PNG image bytes
            prompt: Custom analysis prompt

        Returns:
            AI response text, or None if unavailable
        """
        if not self.is_available or self._client is None:
            return None

        try:
            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )
            return response.text
        except Exception as e:
            logger.error(f"analyze_image failed: {e}")
            return None

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from model response, handling markdown code blocks."""
        text = text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            text = text.strip()

        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {
                "pass": False,
                "reason": f"Failed to parse AI response: {text[:100]}",
                "error": True,
            }
