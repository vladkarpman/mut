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
        """Verify screen matches description."""
        raise NotImplementedError("verify_screen not yet implemented")

    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition."""
        raise NotImplementedError("if_screen not yet implemented")

    def analyze_step(self, before: bytes, after: bytes) -> dict[str, Any]:
        """Analyze before/after frames to describe a step."""
        raise NotImplementedError("analyze_step not yet implemented")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from model response, handling markdown code blocks."""
        text = text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {
                "pass": False,
                "reason": f"Failed to parse AI response: {text[:100]}",
                "error": True,
            }
