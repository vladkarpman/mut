"""AI vision analysis using Gemini 2.5 Flash."""

import base64
import json
import os
from typing import Any


class AIAnalyzer:
    """AI vision analysis using Gemini 2.5 Flash.

    Handles verify_screen, if_screen, and step analysis for test execution
    and recording workflows.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize analyzer.

        Args:
            api_key: Google API key. If not provided, reads from GOOGLE_API_KEY env var.
        """
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._model = "gemini-2.5-flash"
        self._client = None

        if self._api_key:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize Gemini client."""
        # TODO: Initialize google-genai client
        # import google.genai as genai
        # self._client = genai.Client(api_key=self._api_key)
        pass

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
            Dict with pass (bool) and reason (str)
        """
        if not self.is_available:
            return {
                "pass": True,
                "reason": "AI verification skipped (no API key)",
                "skipped": True,
            }

        prompt = f"""Analyze this mobile app screenshot.

Question: Does the screen show "{description}"?

Respond with JSON only:
{{"pass": true/false, "reason": "brief explanation"}}
"""

        # TODO: Call Gemini API
        # response = self._client.models.generate_content(
        #     model=self._model,
        #     contents=[
        #         {"mime_type": "image/png", "data": base64.b64encode(screenshot).decode()},
        #         prompt
        #     ]
        # )
        # return json.loads(response.text)

        raise NotImplementedError("AIAnalyzer.verify_screen() not yet implemented")

    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition.

        Args:
            screenshot: PNG image bytes
            condition: Condition to check

        Returns:
            True if condition is met
        """
        result = self.verify_screen(screenshot, condition)
        return result.get("pass", False)

    def analyze_step(
        self,
        before: bytes,
        after: bytes,
    ) -> dict[str, Any]:
        """Analyze before/after frames to describe a step.

        Args:
            before: PNG image bytes before action
            after: PNG image bytes after action

        Returns:
            Dict with before, action, after descriptions and suggested_verification
        """
        if not self.is_available:
            return {
                "before": "Unknown (AI unavailable)",
                "action": "Unknown",
                "after": "Unknown",
                "suggested_verification": None,
                "skipped": True,
            }

        prompt = """Compare these two mobile app screenshots (before and after an action).

Describe:
1. What was the UI state before?
2. What action was likely performed?
3. What changed after?
4. What verification would confirm this step succeeded?

Respond with JSON only:
{
  "before": "description of before state",
  "action": "description of action",
  "after": "description of after state",
  "suggested_verification": "verification description or null"
}
"""

        # TODO: Call Gemini API with both images
        # response = self._client.models.generate_content(
        #     model=self._model,
        #     contents=[
        #         {"mime_type": "image/png", "data": base64.b64encode(before).decode()},
        #         {"mime_type": "image/png", "data": base64.b64encode(after).decode()},
        #         prompt
        #     ]
        # )
        # return json.loads(response.text)

        raise NotImplementedError("AIAnalyzer.analyze_step() not yet implemented")
