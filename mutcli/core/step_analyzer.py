"""Step analyzer for AI-powered element extraction from screenshots."""

import asyncio
import json
import logging
from collections.abc import Callable
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
        return self._parse_element_response(response_text or "")

    def _parse_element_response(self, text: str) -> dict[str, Any]:
        """Parse JSON response from element extraction.

        Args:
            text: Raw response text from AI

        Returns:
            Parsed dict with element_text and element_type
        """
        if not text:
            logger.debug("AI returned empty response for element extraction")
            return {"element_text": None, "element_type": None}

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
            # Log the actual response for debugging
            preview = text[:100] if len(text) > 100 else text
            logger.warning(f"Failed to parse element JSON: {e}. Response: {preview!r}")
            return {"element_text": None, "element_type": None}

    # -------------------------------------------------------------------------
    # Async parallel analysis methods
    # -------------------------------------------------------------------------

    async def analyze_all_parallel(
        self,
        touch_events: list[dict[str, Any]],
        screenshots_dir: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[AnalyzedStep]:
        """Analyze all steps in parallel with progress callback.

        Args:
            touch_events: List of gesture events (with 'gesture' field: tap/swipe/long_press)
            screenshots_dir: Directory with extracted frames
            on_progress: Callback(completed, total) called as each finishes

        Returns:
            List of AnalyzedStep in original order
        """
        if not touch_events:
            return []

        # Create tasks for all steps
        tasks = []
        for i, event in enumerate(touch_events):
            task = self._analyze_with_retry(i, event, screenshots_dir)
            tasks.append(task)

        # Execute in parallel, collecting results as they complete
        results: list[AnalyzedStep | None] = [None] * len(tasks)
        completed = 0

        for coro in asyncio.as_completed(tasks):
            index, result = await coro
            results[index] = result
            completed += 1
            if on_progress:
                on_progress(completed, len(tasks))

        # Filter out None values (should not happen, but for type safety)
        return [r for r in results if r is not None]

    async def _analyze_with_retry(
        self,
        index: int,
        event: dict[str, Any],
        screenshots_dir: Path,
        max_retries: int = 2,
    ) -> tuple[int, AnalyzedStep]:
        """Analyze single step with exponential backoff retry.

        Args:
            index: Step index (0-based)
            event: Touch event dict with gesture type and coordinates
            screenshots_dir: Directory with extracted frames
            max_retries: Maximum number of retries (default: 2)

        Returns:
            Tuple of (index, AnalyzedStep) to preserve ordering
        """
        delay = 0.5
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                result = await self._analyze_single_step(index, event, screenshots_dir)
                return (index, result)
            except Exception as e:
                last_error = e
                step_num = index + 1
                attempt_num = attempt + 1
                total_attempts = max_retries + 1
                logger.warning(
                    f"Step {step_num} analysis failed (attempt {attempt_num}/{total_attempts}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff

        # All retries exhausted - return placeholder
        return (index, self._placeholder_result(index, event, str(last_error)))

    async def _analyze_single_step(
        self,
        index: int,
        event: dict[str, Any],
        screenshots_dir: Path,
    ) -> AnalyzedStep:
        """Analyze a single step by routing to the correct gesture analyzer.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames

        Returns:
            AnalyzedStep with analysis results

        Raises:
            FileNotFoundError: If required screenshot files are missing
            Exception: If AI analysis fails
        """
        step_num = index + 1
        step_str = f"{step_num:03d}"
        gesture = event.get("gesture", "tap")

        # Load common frames (before, after)
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        if not before_path.exists():
            raise FileNotFoundError(f"Missing before screenshot: {before_path}")
        if not after_path.exists():
            raise FileNotFoundError(f"Missing after screenshot: {after_path}")

        before_data = before_path.read_bytes()
        after_data = after_path.read_bytes()

        # Route to gesture-specific analyzer
        if gesture == "tap":
            return await self._analyze_tap_step(
                index, event, screenshots_dir, before_data, after_data, step_str
            )
        elif gesture == "swipe":
            return await self._analyze_swipe_step(
                index, event, screenshots_dir, before_data, after_data, step_str
            )
        elif gesture == "long_press":
            return await self._analyze_long_press_step(
                index, event, screenshots_dir, before_data, after_data, step_str
            )
        else:
            # Unknown gesture - treat as tap
            logger.warning(f"Unknown gesture type '{gesture}' for step {step_num}, treating as tap")
            return await self._analyze_tap_step(
                index, event, screenshots_dir, before_data, after_data, step_str
            )

    async def _analyze_tap_step(
        self,
        index: int,
        event: dict[str, Any],
        screenshots_dir: Path,
        before_data: bytes,
        after_data: bytes,
        step_str: str,
    ) -> AnalyzedStep:
        """Analyze a tap gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")

        Returns:
            AnalyzedStep with tap analysis results
        """
        touch_path = screenshots_dir / f"step_{step_str}_touch.png"
        if not touch_path.exists():
            raise FileNotFoundError(f"Missing touch screenshot: {touch_path}")

        touch_data = touch_path.read_bytes()
        x = int(event.get("x", 0))
        y = int(event.get("y", 0))

        result = await self._ai_analyzer.analyze_tap(
            before=before_data,
            touch=touch_data,
            after=after_data,
            x=x,
            y=y,
        )

        return AnalyzedStep(
            index=index,
            original_tap=event,
            element_text=result.get("element_text"),
            before_description=result.get("before_description", ""),
            after_description=result.get("after_description", ""),
            suggested_verification=result.get("suggested_verification"),
        )

    async def _analyze_swipe_step(
        self,
        index: int,
        event: dict[str, Any],
        screenshots_dir: Path,
        before_data: bytes,
        after_data: bytes,
        step_str: str,
    ) -> AnalyzedStep:
        """Analyze a swipe gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")

        Returns:
            AnalyzedStep with swipe analysis results
        """
        swipe_start_path = screenshots_dir / f"step_{step_str}_swipe_start.png"
        swipe_end_path = screenshots_dir / f"step_{step_str}_swipe_end.png"

        if not swipe_start_path.exists():
            raise FileNotFoundError(f"Missing swipe_start screenshot: {swipe_start_path}")
        if not swipe_end_path.exists():
            raise FileNotFoundError(f"Missing swipe_end screenshot: {swipe_end_path}")

        swipe_start_data = swipe_start_path.read_bytes()
        swipe_end_data = swipe_end_path.read_bytes()

        # Extract coordinates
        start_x = int(event.get("x", 0))
        start_y = int(event.get("y", 0))
        end_x = int(event.get("end_x", start_x))
        end_y = int(event.get("end_y", start_y))

        result = await self._ai_analyzer.analyze_swipe(
            before=before_data,
            swipe_start=swipe_start_data,
            swipe_end=swipe_end_data,
            after=after_data,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
        )

        # Use direction as element_text for swipes
        direction = result.get("direction", "unknown")
        element_text = f"swipe {direction}"

        return AnalyzedStep(
            index=index,
            original_tap=event,
            element_text=element_text,
            before_description=result.get("before_description", ""),
            after_description=result.get("after_description", ""),
            suggested_verification=result.get("suggested_verification"),
        )

    async def _analyze_long_press_step(
        self,
        index: int,
        event: dict[str, Any],
        screenshots_dir: Path,
        before_data: bytes,
        after_data: bytes,
        step_str: str,
    ) -> AnalyzedStep:
        """Analyze a long press gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")

        Returns:
            AnalyzedStep with long press analysis results
        """
        press_start_path = screenshots_dir / f"step_{step_str}_press_start.png"
        press_held_path = screenshots_dir / f"step_{step_str}_press_held.png"

        if not press_start_path.exists():
            raise FileNotFoundError(f"Missing press_start screenshot: {press_start_path}")
        if not press_held_path.exists():
            raise FileNotFoundError(f"Missing press_held screenshot: {press_held_path}")

        press_start_data = press_start_path.read_bytes()
        press_held_data = press_held_path.read_bytes()

        x = int(event.get("x", 0))
        y = int(event.get("y", 0))
        duration_ms = int(event.get("duration_ms", 500))

        result = await self._ai_analyzer.analyze_long_press(
            before=before_data,
            press_start=press_start_data,
            press_held=press_held_data,
            after=after_data,
            x=x,
            y=y,
            duration_ms=duration_ms,
        )

        return AnalyzedStep(
            index=index,
            original_tap=event,
            element_text=result.get("element_text"),
            before_description=result.get("before_description", ""),
            after_description=result.get("after_description", ""),
            suggested_verification=result.get("suggested_verification"),
        )

    def _placeholder_result(
        self,
        index: int,
        event: dict[str, Any],
        error_message: str,
    ) -> AnalyzedStep:
        """Create a placeholder result for failed analysis.

        Args:
            index: Step index (0-based)
            event: Original touch event
            error_message: Error message from the failure

        Returns:
            AnalyzedStep with error information
        """
        return AnalyzedStep(
            index=index,
            original_tap=event,
            element_text=None,
            before_description=f"Analysis failed: {error_message}",
            after_description=f"Analysis failed: {error_message}",
            suggested_verification=None,
        )
