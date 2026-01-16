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
