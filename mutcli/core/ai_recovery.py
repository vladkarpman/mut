"""AI-powered failure recovery for test execution.

Layer 2 of resilience: when smart waits (Layer 1) fail, AI analyzes
the situation and suggests recovery actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mutcli.core.ai_analyzer import AIAnalyzer

logger = logging.getLogger("mut.recovery")


@dataclass
class AIRecoveryResult:
    """Result of AI recovery analysis."""

    action: str  # "retry", "alternative", "fail"
    reason: str  # Human-readable explanation
    wait_seconds: float | None = None  # Additional wait if action="retry"
    alternative_target: str | None = None  # New target text if action="alternative"
    alternative_coords: tuple[int, int] | None = None  # Direct coords if found


class AIRecovery:
    """AI-powered failure recovery.

    Analyzes screenshots when element finding or verification fails,
    and suggests recovery actions:
    - retry: Wait longer (screen is loading/animating)
    - alternative: Try different target text or coordinates
    - fail: Give up with clear explanation
    """

    def __init__(self, analyzer: AIAnalyzer):
        """Initialize recovery.

        Args:
            analyzer: AIAnalyzer instance for vision analysis
        """
        self._analyzer = analyzer

    @property
    def is_available(self) -> bool:
        """Check if AI recovery is available."""
        return self._analyzer.is_available

    def analyze_element_not_found(
        self,
        screenshot: bytes,
        target: str,
        action: str,
        screen_size: tuple[int, int],
    ) -> AIRecoveryResult:
        """Analyze why element wasn't found and suggest recovery.

        Args:
            screenshot: Current screen state
            target: Element text/description that wasn't found
            action: Action type (tap, wait_for, etc.)
            screen_size: (width, height) of screen

        Returns:
            AIRecoveryResult with suggested action
        """
        if not self.is_available or not self._analyzer._client:
            logger.warning("AI not available for recovery analysis")
            return AIRecoveryResult(
                action="fail",
                reason="AI recovery unavailable",
            )

        width, height = screen_size
        prompt = self._build_element_not_found_prompt(target, action)

        try:
            from google.genai import types

            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._analyzer._client.models.generate_content(
                model=self._analyzer._model,
                contents=[image_part, prompt],
            )

            response_text = response.text or ""
            result = self._analyzer._parse_json_response(response_text)

            return self._parse_recovery_result(result, width, height)

        except Exception as e:
            logger.error(f"AI recovery analysis failed: {e}")
            return AIRecoveryResult(
                action="fail",
                reason=f"Analysis error: {e}",
            )

    def analyze_verify_screen_failed(
        self,
        screenshot: bytes,
        description: str,
        failure_reason: str,
    ) -> AIRecoveryResult:
        """Analyze why screen verification failed and suggest recovery.

        Args:
            screenshot: Current screen state
            description: Expected screen description
            failure_reason: Why verification failed

        Returns:
            AIRecoveryResult with suggested action
        """
        if not self.is_available or not self._analyzer._client:
            logger.warning("AI not available for recovery analysis")
            return AIRecoveryResult(
                action="fail",
                reason="AI recovery unavailable",
            )

        prompt = self._build_verify_screen_failed_prompt(description, failure_reason)

        try:
            from google.genai import types

            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._analyzer._client.models.generate_content(
                model=self._analyzer._model,
                contents=[image_part, prompt],
            )

            response_text = response.text or ""
            result = self._analyzer._parse_json_response(response_text)

            return self._parse_recovery_result(result, 0, 0)

        except Exception as e:
            logger.error(f"AI recovery analysis failed: {e}")
            return AIRecoveryResult(
                action="fail",
                reason=f"Analysis error: {e}",
            )

    def _build_element_not_found_prompt(self, target: str, action: str) -> str:
        """Build prompt for element not found analysis."""
        return f"""You are analyzing a mobile UI test failure.

Action attempted: {action} "{target}"
Result: Element not found after waiting

Screenshot shows the current screen state.

Analyze and respond with JSON only (no markdown, no code blocks):
{{
  "action": "retry" | "alternative" | "fail",
  "reason": "brief explanation (1 sentence)",
  "wait_seconds": number or null,
  "alternative": "different element text" or null,
  "coordinates": [x_percent, y_percent] or null
}}

Decision guide:
- "retry" + wait_seconds: Screen is still loading (spinner visible, progress indicator, blank areas loading)
  - Set wait_seconds between 1-3 based on how much more loading appears needed
- "alternative" + alternative text: Similar element exists with different text
  - Example: Looking for "Login" but see "LOG IN" or "Sign In"
  - Set alternative to the exact text you see on screen
- "alternative" + coordinates: Element found visually but text doesn't match exactly
  - Set coordinates as [x%, y%] from top-left (e.g., [50, 30] for center-ish top area)
- "fail": Element clearly doesn't exist on this screen
  - Wrong screen entirely (e.g., looking for "Submit" on login screen)
  - No similar elements visible
  - Screen is fully loaded but element not present

Be decisive. If the screen looks fully loaded and element isn't there, fail fast.
If you see the element with slightly different text, provide the alternative.
Only suggest retry if you see clear loading indicators."""

    def _build_verify_screen_failed_prompt(
        self, description: str, failure_reason: str
    ) -> str:
        """Build prompt for verify_screen failure analysis."""
        return f"""You are analyzing a mobile UI test verification failure.

Expected screen: "{description}"
Verification failed because: {failure_reason}

Screenshot shows the current screen state.

Analyze and respond with JSON only (no markdown, no code blocks):
{{
  "action": "retry" | "fail",
  "reason": "brief explanation (1 sentence)",
  "wait_seconds": number or null
}}

Decision guide:
- "retry" + wait_seconds: Screen is transitioning or loading
  - Content is appearing but not complete yet
  - Animation in progress
  - Set wait_seconds between 1-3
- "fail": Screen doesn't match and won't change
  - Completely wrong screen
  - Screen is fully loaded but doesn't match description
  - No loading indicators visible

Be decisive. Only retry if you see clear signs of loading/transition."""

    def _parse_recovery_result(
        self, result: dict[str, Any], width: int, height: int
    ) -> AIRecoveryResult:
        """Parse AI response into AIRecoveryResult.

        Args:
            result: Parsed JSON from AI
            width: Screen width for coordinate conversion
            height: Screen height for coordinate conversion

        Returns:
            AIRecoveryResult
        """
        action = result.get("action", "fail")
        reason = result.get("reason", "Unknown")

        # Validate action
        if action not in ("retry", "alternative", "fail"):
            logger.warning(f"Invalid recovery action '{action}', defaulting to fail")
            action = "fail"

        recovery = AIRecoveryResult(action=action, reason=reason)

        if action == "retry":
            wait = result.get("wait_seconds")
            if isinstance(wait, (int, float)) and 0 < wait <= 5:
                recovery.wait_seconds = float(wait)
            else:
                recovery.wait_seconds = 2.0  # Default retry wait

        elif action == "alternative":
            # Check for alternative text
            alt_text = result.get("alternative")
            if alt_text and isinstance(alt_text, str):
                recovery.alternative_target = alt_text
                logger.debug(f"AI suggests alternative target: '{alt_text}'")

            # Check for coordinates
            coords = result.get("coordinates")
            if coords and isinstance(coords, list) and len(coords) == 2:
                try:
                    x_pct, y_pct = float(coords[0]), float(coords[1])
                    if 0 <= x_pct <= 100 and 0 <= y_pct <= 100 and width > 0 and height > 0:
                        recovery.alternative_coords = (
                            int(x_pct * width / 100),
                            int(y_pct * height / 100),
                        )
                        logger.debug(
                            f"AI suggests coordinates: ({x_pct}%, {y_pct}%) -> {recovery.alternative_coords}"
                        )
                except (TypeError, ValueError):
                    pass

            # If alternative action but no useful alternative provided, treat as fail
            if not recovery.alternative_target and not recovery.alternative_coords:
                logger.warning("AI suggested alternative but provided no target/coords")
                recovery.action = "fail"
                recovery.reason = f"{reason} (no alternative provided)"

        return recovery
