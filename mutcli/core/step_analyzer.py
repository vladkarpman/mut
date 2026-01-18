"""Step analyzer for AI-powered element extraction from screenshots."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.api_core import exceptions as google_exceptions

from mutcli.core.ai_analyzer import AIAnalyzer

if TYPE_CHECKING:
    from mutcli.core.step_collapsing import CollapsedStep

logger = logging.getLogger("mut.step_analyzer")


# Exceptions that indicate transient errors and should trigger retry
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    # Google API exceptions (rate limit, server errors)
    google_exceptions.TooManyRequests,        # 429
    google_exceptions.ResourceExhausted,      # 429 (gRPC variant)
    google_exceptions.InternalServerError,    # 500
    google_exceptions.BadGateway,             # 502
    google_exceptions.ServiceUnavailable,     # 503
    google_exceptions.DeadlineExceeded,       # Timeout
    # Python built-in network errors
    TimeoutError,
    ConnectionError,
)


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

    def _build_adb_context(
        self,
        timestamp: float,
        x: int | None,
        y: int | None,
        adb_data: dict | None,
    ) -> dict | None:
        """Build ADB context for AI prompt enrichment.

        Finds the most recent ADB state for the given timestamp.

        Args:
            timestamp: Event timestamp
            x: Tap X coordinate (optional)
            y: Tap Y coordinate (optional)
            adb_data: Dict with keyboard_states, activity_states, window_states

        Returns:
            Context dict for AI prompt, or None if no data
        """
        if not adb_data:
            return None

        context: dict[str, Any] = {}

        # Get keyboard state - find most recent state before/at timestamp
        keyboard_states = adb_data.get("keyboard_states", [])
        if keyboard_states:
            for ts, visible in keyboard_states:
                if ts <= timestamp:
                    context["keyboard_visible"] = visible
                else:
                    break

        # Get activity - find most recent activity before/at timestamp
        activity_states = adb_data.get("activity_states", [])
        if activity_states:
            for ts, activity in activity_states:
                if ts <= timestamp:
                    context["activity"] = activity
                else:
                    break

        # Get windows - find most recent window state before/at timestamp
        window_states = adb_data.get("window_states", [])
        if window_states:
            for ts, windows in window_states:
                if ts <= timestamp:
                    context["windows"] = windows
                else:
                    break

        return context if context else None

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

        Only retries on transient errors (rate limits, timeouts, server errors).
        Client errors (4xx like invalid API key) fail immediately without retry.

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
        step_num = index + 1

        for attempt in range(max_retries + 1):
            try:
                result = await self._analyze_single_step(index, event, screenshots_dir)
                return (index, result)
            except RETRYABLE_EXCEPTIONS as e:
                # Transient error - retry with backoff
                last_error = e
                attempt_num = attempt + 1
                total_attempts = max_retries + 1
                logger.warning(
                    f"Step {step_num} analysis failed (attempt {attempt_num}/{total_attempts}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
            except Exception as e:
                # Non-retryable error (client error, invalid API key, etc.) - fail immediately
                logger.error(f"Step {step_num} analysis failed with non-retryable error: {e}")
                return (index, self._placeholder_result(index, event, str(e)))

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
        adb_context: dict | None = None,
    ) -> AnalyzedStep:
        """Analyze a tap gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")
            adb_context: Optional ADB context for enhanced analysis

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
            adb_context=adb_context,
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
        adb_context: dict | None = None,
    ) -> AnalyzedStep:
        """Analyze a swipe gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")
            adb_context: Optional ADB context for enhanced analysis

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
            adb_context=adb_context,
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
        adb_context: dict | None = None,
    ) -> AnalyzedStep:
        """Analyze a long press gesture step.

        Args:
            index: Step index (0-based)
            event: Touch event dict
            screenshots_dir: Directory with extracted frames
            before_data: PNG bytes of before frame
            after_data: PNG bytes of after frame
            step_str: Zero-padded step number string (e.g., "001")
            adb_context: Optional ADB context for enhanced analysis

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
            adb_context=adb_context,
        )

        return AnalyzedStep(
            index=index,
            original_tap=event,
            element_text=result.get("element_text"),
            before_description=result.get("before_description", ""),
            after_description=result.get("after_description", ""),
            suggested_verification=result.get("suggested_verification"),
        )

    async def _analyze_type_step(
        self,
        index: int,
        step: CollapsedStep,
        screenshots_dir: Path,
        adb_context: dict | None = None,
    ) -> AnalyzedStep:
        """Analyze a type action step using before and after frames.

        Args:
            index: Step index (0-based)
            step: CollapsedStep for the type action
            screenshots_dir: Directory with extracted frames
            adb_context: Optional ADB context for enhanced analysis

        Returns:
            AnalyzedStep with type analysis results
        """
        step_str = f"{step.index:03d}"

        before_path = screenshots_dir / f"step_{step_str}_before.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        if not before_path.exists():
            raise FileNotFoundError(f"Missing before screenshot: {before_path}")
        if not after_path.exists():
            raise FileNotFoundError(f"Missing after screenshot: {after_path}")

        before_data = before_path.read_bytes()
        after_data = after_path.read_bytes()

        result = await self._ai_analyzer.analyze_type(
            before=before_data,
            after=after_data,
            adb_context=adb_context,
        )

        # Convert CollapsedStep to event dict for original_tap field
        original_event = {
            "action": step.action,
            "timestamp": step.timestamp,
            "tap_count": step.tap_count,
            "text": step.text,
        }

        return AnalyzedStep(
            index=index,
            original_tap=original_event,
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

    # -------------------------------------------------------------------------
    # Collapsed steps analysis methods
    # -------------------------------------------------------------------------

    async def analyze_collapsed_steps_parallel(
        self,
        collapsed_steps: list[CollapsedStep],
        screenshots_dir: Path,
        on_progress: Callable[[int, int], None] | None = None,
        adb_data: dict | None = None,
    ) -> list[AnalyzedStep]:
        """Analyze all collapsed steps in parallel with progress callback.

        Handles CollapsedStep objects, routing each action type to the
        appropriate analyzer:
        - type: Uses analyze_type (2 frames: before, after)
        - tap: Uses analyze_tap (3 frames: before, touch, after)
        - swipe: Uses analyze_swipe (4 frames)
        - long_press: Uses analyze_long_press (4 frames)

        Args:
            collapsed_steps: List of CollapsedStep objects
            screenshots_dir: Directory with extracted frames
            on_progress: Callback(completed, total) called as each finishes
            adb_data: Dict with keyboard_states, activity_states, window_states for
                     enhanced AI analysis

        Returns:
            List of AnalyzedStep in original order
        """
        if not collapsed_steps:
            return []

        # Create tasks for all steps
        tasks = []
        for i, step in enumerate(collapsed_steps):
            task = self._analyze_collapsed_step_with_retry(
                i, step, screenshots_dir, adb_data=adb_data
            )
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

    async def _analyze_collapsed_step_with_retry(
        self,
        index: int,
        step: CollapsedStep,
        screenshots_dir: Path,
        max_retries: int = 2,
        adb_data: dict | None = None,
    ) -> tuple[int, AnalyzedStep]:
        """Analyze single collapsed step with exponential backoff retry.

        Routes to appropriate handler based on step.action.

        Args:
            index: Step index (0-based)
            step: CollapsedStep object
            screenshots_dir: Directory with extracted frames
            max_retries: Maximum number of retries (default: 2)
            adb_data: Dict with keyboard_states, activity_states, window_states

        Returns:
            Tuple of (index, AnalyzedStep) to preserve ordering
        """
        delay = 0.5
        last_error: Exception | None = None
        step_num = step.index

        # Create event dict from CollapsedStep for placeholder
        event_dict = self._collapsed_step_to_event(step)

        for attempt in range(max_retries + 1):
            try:
                result = await self._analyze_single_collapsed_step(
                    index, step, screenshots_dir, adb_data=adb_data
                )
                return (index, result)
            except RETRYABLE_EXCEPTIONS as e:
                # Transient error - retry with backoff
                last_error = e
                attempt_num = attempt + 1
                total_attempts = max_retries + 1
                logger.warning(
                    f"Step {step_num} analysis failed (attempt {attempt_num}/{total_attempts}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
            except Exception as e:
                # Non-retryable error - fail immediately
                logger.error(f"Step {step_num} analysis failed with non-retryable error: {e}")
                return (index, self._placeholder_result(index, event_dict, str(e)))

        # All retries exhausted - return placeholder
        return (index, self._placeholder_result(index, event_dict, str(last_error)))

    async def _analyze_single_collapsed_step(
        self,
        index: int,
        step: CollapsedStep,
        screenshots_dir: Path,
        adb_data: dict | None = None,
    ) -> AnalyzedStep:
        """Analyze a single collapsed step by routing to the correct analyzer.

        Args:
            index: Step index (0-based)
            step: CollapsedStep object
            screenshots_dir: Directory with extracted frames
            adb_data: Dict with keyboard_states, activity_states, window_states

        Returns:
            AnalyzedStep with analysis results

        Raises:
            FileNotFoundError: If required screenshot files are missing
            Exception: If AI analysis fails
        """
        action = step.action

        # Build ADB context for this step's timestamp
        if step.coordinates:
            x = step.coordinates.get("x")
            y = step.coordinates.get("y")
        elif step.start:
            x = step.start.get("x")
            y = step.start.get("y")
        else:
            x, y = None, None
        adb_context = self._build_adb_context(step.timestamp, x, y, adb_data)

        if action == "type":
            return await self._analyze_type_step(
                index, step, screenshots_dir, adb_context=adb_context
            )

        # For gesture actions, convert to event dict and use existing methods
        step_str = f"{step.index:03d}"

        # Load common frames (before, after)
        before_path = screenshots_dir / f"step_{step_str}_before.png"
        after_path = screenshots_dir / f"step_{step_str}_after.png"

        if not before_path.exists():
            raise FileNotFoundError(f"Missing before screenshot: {before_path}")
        if not after_path.exists():
            raise FileNotFoundError(f"Missing after screenshot: {after_path}")

        before_data = before_path.read_bytes()
        after_data = after_path.read_bytes()

        # Convert CollapsedStep to event dict for the gesture handlers
        event = self._collapsed_step_to_event(step)

        if action == "tap":
            return await self._analyze_tap_step(
                index, event, screenshots_dir, before_data, after_data, step_str,
                adb_context=adb_context,
            )
        elif action == "swipe":
            return await self._analyze_swipe_step(
                index, event, screenshots_dir, before_data, after_data, step_str,
                adb_context=adb_context,
            )
        elif action == "long_press":
            return await self._analyze_long_press_step(
                index, event, screenshots_dir, before_data, after_data, step_str,
                adb_context=adb_context,
            )
        else:
            # Unknown action - treat as tap
            logger.warning(
                f"Unknown action type '{action}' for step {step.index}, treating as tap"
            )
            return await self._analyze_tap_step(
                index, event, screenshots_dir, before_data, after_data, step_str,
                adb_context=adb_context,
            )

    def _collapsed_step_to_event(self, step: CollapsedStep) -> dict[str, Any]:
        """Convert CollapsedStep to event dict for compatibility.

        Args:
            step: CollapsedStep object

        Returns:
            Dict compatible with touch event format
        """
        event: dict[str, Any] = {
            "gesture": step.action if step.action != "type" else "tap",
            "action": step.action,
            "timestamp": step.timestamp,
        }

        if step.coordinates:
            event["x"] = step.coordinates["x"]
            event["y"] = step.coordinates["y"]

        if step.start:
            event["x"] = step.start["x"]
            event["y"] = step.start["y"]

        if step.end:
            event["end_x"] = step.end["x"]
            event["end_y"] = step.end["y"]

        if step.duration_ms is not None:
            event["duration_ms"] = step.duration_ms

        if step.tap_count is not None:
            event["tap_count"] = step.tap_count

        if step.text is not None:
            event["text"] = step.text

        return event
