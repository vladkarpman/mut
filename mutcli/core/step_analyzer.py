"""Step analyzer for AI-powered element extraction from screenshots."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutcli.core.ai_analyzer import AIAnalyzer

logger = logging.getLogger("mut.step_analyzer")


ELEMENT_EXTRACTION_PROMPT = '''Analyze this mobile app screenshot.

A tap occurred at coordinates ({x}, {y}).

1. What UI element was tapped? Look for buttons, text fields, links near those coordinates.
2. What is the text label of that element?

Respond with JSON only:
{{"element_text": "button/field text or null if unclear",
"element_type": "button|text_field|link|icon|other"}}'''


@dataclass
class AnalyzedStep:
    """Result of analyzing a single step.

    Attributes:
        index: Step index (0-based)
        original_tap: Original touch event data
        element_text: AI-extracted element text (None if unavailable)
        before_description: Description of screen state before tap
        after_description: Description of screen state after tap
        suggested_verification: Optional verification suggestion
    """

    index: int
    original_tap: dict[str, Any]
    element_text: str | None
    before_description: str
    after_description: str
    suggested_verification: str | None


class StepAnalyzer:
    """Analyzes recording steps using AI to extract element text and descriptions.

    Uses AIAnalyzer to:
    1. Extract element text from tapped UI elements
    2. Generate before/after descriptions of screen states
    3. Suggest verifications for meaningful checkpoints
    """

    def __init__(self, ai_analyzer: AIAnalyzer):
        """Initialize with AIAnalyzer instance.

        Args:
            ai_analyzer: AIAnalyzer instance for vision analysis
        """
        self._ai_analyzer = ai_analyzer

    def analyze_step(
        self,
        before_screenshot: bytes,
        after_screenshot: bytes,
        tap_coordinates: tuple[int, int],
    ) -> AnalyzedStep:
        """Analyze a single step using AI.

        Args:
            before_screenshot: PNG bytes before tap
            after_screenshot: PNG bytes after tap
            tap_coordinates: (x, y) of tap

        Returns:
            AnalyzedStep with extracted information.
            Note: index and original_tap are set to placeholders (0 and {}).
            The caller (analyze_all) sets the correct values.
        """
        # Extract element text from the before screenshot
        element_info = self._extract_element(before_screenshot, tap_coordinates)
        element_text = element_info.get("element_text")

        # Analyze before/after to get descriptions
        step_analysis = self._ai_analyzer.analyze_step(before_screenshot, after_screenshot)

        return AnalyzedStep(
            index=0,
            original_tap={},
            element_text=element_text,
            before_description=step_analysis.get("before", "Unknown"),
            after_description=step_analysis.get("after", "Unknown"),
            suggested_verification=step_analysis.get("suggested_verification"),
        )

    def analyze_all(
        self,
        touch_events: list[dict[str, Any]],
        screenshots_dir: Path,
    ) -> list[AnalyzedStep]:
        """Analyze all steps from recording.

        Args:
            touch_events: List of touch event dicts
            screenshots_dir: Directory with step_001_before.png, step_001_after.png, etc.

        Returns:
            List of AnalyzedStep objects
        """
        if not touch_events:
            return []

        results: list[AnalyzedStep] = []

        for i, tap in enumerate(touch_events):
            step_num = i + 1
            before_path = screenshots_dir / f"step_{step_num:03d}_before.png"
            after_path = screenshots_dir / f"step_{step_num:03d}_after.png"

            # Check if screenshot files exist
            if not before_path.exists() or not after_path.exists():
                logger.warning(f"Missing screenshots for step {step_num}")
                results.append(AnalyzedStep(
                    index=i,
                    original_tap=tap,
                    element_text=None,
                    before_description="Screenshot missing",
                    after_description="Screenshot missing",
                    suggested_verification=None,
                ))
                continue

            try:
                before_screenshot = before_path.read_bytes()
                after_screenshot = after_path.read_bytes()

                x = int(tap.get("x", 0))
                y = int(tap.get("y", 0))

                analyzed = self.analyze_step(
                    before_screenshot=before_screenshot,
                    after_screenshot=after_screenshot,
                    tap_coordinates=(x, y),
                )
                # Set the correct index and original_tap on the returned object
                analyzed.index = i
                analyzed.original_tap = tap
                results.append(analyzed)

            except Exception as e:
                logger.error(f"Failed to analyze step {step_num}: {e}")
                results.append(AnalyzedStep(
                    index=i,
                    original_tap=tap,
                    element_text=None,
                    before_description=f"Analysis failed: {e}",
                    after_description=f"Analysis failed: {e}",
                    suggested_verification=None,
                ))

        return results

    def _extract_element(
        self,
        screenshot: bytes,
        tap_coordinates: tuple[int, int],
    ) -> dict[str, Any]:
        """Extract element information from screenshot at tap location.

        Args:
            screenshot: PNG bytes of the screen
            tap_coordinates: (x, y) of the tap

        Returns:
            Dict with element_text and element_type (None if unavailable)
        """
        x, y = tap_coordinates
        prompt = ELEMENT_EXTRACTION_PROMPT.format(x=x, y=y)

        response_text = self._ai_analyzer.analyze_image(screenshot, prompt)
        if not response_text:
            return {"element_text": None, "element_type": None}

        return self._parse_element_response(response_text)

    def _parse_element_response(self, text: str) -> dict[str, Any]:
        """Parse JSON response from element extraction.

        Args:
            text: Raw response text from AI

        Returns:
            Parsed dict with element_text and element_type
        """
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
            logger.warning(f"Failed to parse element JSON: {e}")
            return {"element_text": None, "element_type": None}
