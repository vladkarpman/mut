"""Test execution engine."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.config import ConfigLoader, MutConfig
from mutcli.core.device_controller import DeviceController
from mutcli.models.test import Step, TestFile

logger = logging.getLogger("mut.executor")


@dataclass
class StepResult:
    """Result of executing a step."""

    step_number: int
    action: str
    status: str  # "passed", "failed", "skipped"
    duration: float = 0.0
    error: str | None = None
    screenshot_before: bytes | None = None
    screenshot_after: bytes | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Result of executing a test."""

    name: str
    status: str  # "passed", "failed", "error"
    duration: float
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None


class TestExecutor:
    """Execute test steps on device."""

    # Tell pytest not to collect this as a test class
    __test__ = False

    def __init__(
        self,
        device_id: str,
        config: MutConfig | None = None,
        ai_analyzer: AIAnalyzer | None = None,
    ):
        """Initialize executor.

        Args:
            device_id: ADB device identifier
            config: Configuration (loads from files if not provided)
            ai_analyzer: AI analyzer (creates new if not provided)
        """
        self._device = DeviceController(device_id)
        self._config = config or ConfigLoader.load()
        self._ai = ai_analyzer or AIAnalyzer()
        self._screen_size: tuple[int, int] | None = None
        self._step_number = 0
        self._test_start: float = 0.0  # Track test start time for timestamps
        self._test_app: str | None = None  # App from test file config

    def execute_test(self, test: TestFile) -> TestResult:
        """Execute a complete test file.

        Args:
            test: Parsed test file

        Returns:
            TestResult with all step results
        """
        start = time.time()
        self._test_start = start  # Store for step timestamps
        self._step_number = 0  # Reset for each test
        self._test_app = test.config.app  # Store app from test file config
        results: list[StepResult] = []
        status = "passed"
        error = None

        test_name = test.path or "unknown"
        logger.info("Starting test: %s", test_name)
        logger.debug(
            "Test config: app=%s, setup_steps=%d, main_steps=%d, teardown_steps=%d",
            test.config.app,
            len(test.setup),
            len(test.steps),
            len(test.teardown),
        )

        try:
            # Setup
            logger.debug("Executing setup phase (%d steps)", len(test.setup))
            for step in test.setup:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = f"Setup failed: {result.error}"
                    logger.error("Setup failed at step %d: %s", result.step_number, result.error)
                    return TestResult(
                        name=test.path or "unknown",
                        status=status,
                        duration=time.time() - start,
                        steps=results,
                        error=error,
                    )

            logger.debug("Setup phase completed successfully")

            # Main steps
            logger.debug("Executing main test phase (%d steps)", len(test.steps))
            for step in test.steps:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = result.error
                    logger.error("Main step %d failed: %s", result.step_number, result.error)
                    break

            if status == "passed":
                logger.debug("Main test phase completed successfully")

            # Teardown (always run)
            logger.debug("Executing teardown phase (%d steps)", len(test.teardown))
            for step in test.teardown:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    logger.warning(
                        "Teardown step %d failed: %s", result.step_number, result.error
                    )

        except Exception as e:
            status = "error"
            error = str(e)
            logger.exception("Test execution error: %s", e)

        duration = time.time() - start
        logger.info(
            "Test completed: %s - status=%s, duration=%.2fs, steps=%d",
            test_name,
            status,
            duration,
            len(results),
        )

        return TestResult(
            name=test.path or "unknown",
            status=status,
            duration=duration,
            steps=results,
            error=error,
        )

    def execute_step(self, step: Step) -> StepResult:
        """Execute a single step.

        Args:
            step: Step to execute

        Returns:
            StepResult
        """
        self._step_number += 1
        start = time.time()

        # Build step description for logging
        step_desc = self._format_step_description(step)
        logger.debug("Step %d: Starting %s", self._step_number, step_desc)

        # Capture before screenshot
        screenshot_before = self._capture_screenshot()

        try:
            # Dispatch to action handler
            handler = getattr(self, f"_action_{step.action}", None)
            if handler is None:
                logger.error("Step %d: Unknown action '%s'", self._step_number, step.action)
                return StepResult(
                    step_number=self._step_number,
                    action=step.action,
                    status="failed",
                    error=f"Unknown action: {step.action}",
                    screenshot_before=screenshot_before,
                )

            error = handler(step)

            # Capture after screenshot
            screenshot_after = self._capture_screenshot()
            elapsed = time.time() - start

            if error:
                logger.debug(
                    "Step %d: Failed %s in %.2fs - %s",
                    self._step_number,
                    step.action,
                    elapsed,
                    error,
                )
            else:
                logger.debug(
                    "Step %d: Completed %s in %.2fs", self._step_number, step.action, elapsed
                )

            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed" if error else "passed",
                duration=elapsed,
                error=error,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
                details={"timestamp": time.time() - self._test_start},
            )

        except Exception as e:
            elapsed = time.time() - start
            logger.exception(
                "Step %d: Exception in %s after %.2fs", self._step_number, step.action, elapsed
            )
            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed",
                duration=elapsed,
                error=str(e),
                screenshot_before=screenshot_before,
            )

    def _format_step_description(self, step: Step) -> str:
        """Format step for logging purposes.

        Args:
            step: Step to format

        Returns:
            Human-readable step description
        """
        parts = [step.action]
        if step.target:
            parts.append(f"'{step.target}'")
        if step.coordinates:
            parts.append(f"at {step.coordinates}")
        if step.direction:
            parts.append(f"direction={step.direction}")
        if step.text:
            # Truncate long text for logging
            text = step.text if len(step.text) <= 20 else step.text[:17] + "..."
            parts.append(f"text='{text}'")
        return " ".join(parts)

    def _capture_screenshot(self) -> bytes | None:
        """Capture screenshot from device if available.

        Returns:
            Screenshot bytes or None if capture fails
        """
        try:
            return self._device.take_screenshot()
        except Exception:
            return None

    def _get_screen_size(self) -> tuple[int, int]:
        """Get cached screen size."""
        if self._screen_size is None:
            self._screen_size = self._device.get_screen_size()
        return self._screen_size

    def _coordinates_to_pixels(self, step: Step) -> tuple[int, int] | None:
        """Convert step coordinates to pixels.

        Args:
            step: Step with coordinates

        Returns:
            (x, y) in pixels, or None if no coordinates
        """
        if not step.coordinates:
            return None

        x, y = step.coordinates
        if step.coordinates_type == "percent":
            width, height = self._get_screen_size()
            return int(x * width / 100), int(y * height / 100)
        return int(x), int(y)

    def _resolve_coordinates_ai(self, step: Step) -> tuple[tuple[int, int] | None, str | None]:
        """Resolve coordinates using AI-first approach.

        Strategy:
        1. coordinates only (no text) → use coordinates directly
        2. text + coordinates → validate with AI, use coordinates
        3. text only → AI finds element

        Returns:
            (coordinates, error) - coordinates are (x, y) or None, error is message or None
        """
        width, height = self._get_screen_size()
        has_text = bool(step.target)
        has_coords = bool(step.coordinates)

        # Case 1: Coordinates only - use directly, no AI
        if has_coords and not has_text:
            coords = self._coordinates_to_pixels(step)
            logger.debug("Using direct coordinates: %s", coords)
            return coords, None

        # Case 2: Text + coordinates - validate with AI, use coordinates
        if has_text and has_coords and step.coordinates and step.target:
            coords = self._coordinates_to_pixels(step)
            if coords:
                logger.debug(
                    "Validating element '%s' at coordinates %s with AI", step.target, coords
                )
                screenshot = self._device.take_screenshot()
                if step.coordinates_type == "percent":
                    x_pct = step.coordinates[0]
                    y_pct = step.coordinates[1]
                else:
                    x_pct = coords[0] * 100 / width
                    y_pct = coords[1] * 100 / height

                validation = self._ai.validate_element_at(
                    screenshot, step.target, x_pct, y_pct
                )
                if not validation.get("valid") and not validation.get("skipped"):
                    reason = validation.get("reason", "unknown")
                    logger.debug(
                        "AI validation failed for '%s' at (%.0f%%, %.0f%%): %s",
                        step.target,
                        x_pct,
                        y_pct,
                        reason,
                    )
                    return None, (
                        f"Validation failed: expected '{step.target}' "
                        f"at ({x_pct:.0f}%, {y_pct:.0f}%), but: {reason}"
                    )

                logger.debug(
                    "AI validation passed for '%s' at (%.0f%%, %.0f%%)",
                    step.target,
                    x_pct,
                    y_pct,
                )
                return coords, None
            return None, f"Invalid coordinates for '{step.target}'"

        # Case 3: Text only - AI finds element
        if has_text and step.target:
            # First try device's element finder (faster, uses accessibility tree)
            logger.debug("Searching for element '%s' using accessibility tree", step.target)
            coords = self._device.find_element(step.target)
            if coords:
                logger.debug("Element '%s' found via accessibility at %s", step.target, coords)
                return coords, None

            # Fall back to AI vision
            logger.debug("Element '%s' not in accessibility tree, trying AI vision", step.target)
            screenshot = self._device.take_screenshot()
            coords = self._ai.find_element(screenshot, step.target, width, height)
            if coords:
                logger.debug("Element '%s' found via AI vision at %s", step.target, coords)
                return coords, None

            logger.debug("Element '%s' not found by any method", step.target)
            return None, f"Element '{step.target}' not found"

        return None, "No target or coordinates specified"

    # Action handlers

    def _action_tap(self, step: Step) -> str | None:
        """Execute tap action using AI-first approach."""
        coords, error = self._resolve_coordinates_ai(step)
        if error:
            return error
        if coords is None:
            return "Could not resolve coordinates for tap"

        self._device.tap(coords[0], coords[1])
        return None

    def _action_type(self, step: Step) -> str | None:
        """Execute type action."""
        text = step.text or step.target
        if not text:
            return "No text to type"

        self._device.type_text(text)
        return None

    def _action_swipe(self, step: Step) -> str | None:
        """Execute swipe action."""
        width, height = self._get_screen_size()

        # Default: center of screen
        cx, cy = width // 2, height // 2

        # Custom start point
        if step.from_coords:
            x, y = step.from_coords
            cx = int(x * width / 100)
            cy = int(y * height / 100)

        # Calculate end point based on direction
        distance = step.distance or 30  # Default 30%
        distance_px = int(distance * height / 100)

        direction = (step.direction or "up").lower()
        if direction == "up":
            self._device.swipe(cx, cy, cx, cy - distance_px)
        elif direction == "down":
            self._device.swipe(cx, cy, cx, cy + distance_px)
        elif direction == "left":
            distance_px = int(distance * width / 100)
            self._device.swipe(cx, cy, cx - distance_px, cy)
        elif direction == "right":
            distance_px = int(distance * width / 100)
            self._device.swipe(cx, cy, cx + distance_px, cy)
        else:
            return f"Unknown swipe direction: {direction}"

        return None

    def _action_wait(self, step: Step) -> str | None:
        """Execute wait action."""
        duration = step.timeout or 1.0
        time.sleep(duration)
        return None

    def _action_wait_for(self, step: Step) -> str | None:
        """Wait for element to appear."""
        target = step.target
        if not target:
            return "No element to wait for"

        timeout = step.timeout or self._config.timeouts.wait_for
        start = time.time()
        attempt = 0

        logger.debug("Waiting for element '%s' (timeout=%.1fs)", target, timeout)

        while time.time() - start < timeout:
            attempt += 1
            if self._device.find_element(target):
                elapsed = time.time() - start
                logger.debug(
                    "Element '%s' found after %.2fs (%d attempts)", target, elapsed, attempt
                )
                return None
            time.sleep(0.5)

        logger.debug(
            "Timeout waiting for element '%s' after %.1fs (%d attempts)",
            target,
            timeout,
            attempt,
        )
        return f"Timeout waiting for '{target}'"

    def _action_launch_app(self, step: Step) -> str | None:
        """Launch app."""
        package = step.target or self._test_app or self._config.app
        if not package:
            return "No app package specified"

        self._device.launch_app(package)
        return None

    def _action_terminate_app(self, step: Step) -> str | None:
        """Terminate app."""
        package = step.target or self._test_app or self._config.app
        if not package:
            return "No app package specified"

        self._device.terminate_app(package)
        return None

    def _action_back(self, step: Step) -> str | None:
        """Press back button."""
        self._device.press_key("BACK")
        return None

    def _action_verify_screen(self, step: Step) -> str | None:
        """Verify screen with AI.

        Note: Full implementation requires ScrcpyService for screenshots.
        For now, skip if no AI available.
        """
        if not self._ai.is_available:
            return None

        # TODO: Integrate with ScrcpyService for screenshots
        return None

    def _action_hide_keyboard(self, step: Step) -> str | None:
        """Hide keyboard by pressing back."""
        self._device.press_key("BACK")
        return None

    def _action_long_press(self, step: Step) -> str | None:
        """Execute long press action using AI-first approach."""
        coords, error = self._resolve_coordinates_ai(step)
        if error:
            return error
        if coords is None:
            return "Could not resolve coordinates for long_press"

        duration = step.duration or 500  # Default 500ms
        self._device.long_press(coords[0], coords[1], duration)
        return None

    def _action_scroll_to(self, step: Step) -> str | None:
        """Scroll until element is visible using AI-first approach.

        Note: direction refers to scroll direction (content movement).
        'down' scrolls content down (revealing content below).
        """
        target = step.target
        if not target:
            return "No element specified for scroll_to"

        direction = (step.direction or "down").lower()
        max_scrolls = step.max_scrolls or 10
        width, height = self._get_screen_size()

        logger.debug(
            "Scrolling to find element '%s' (direction=%s, max_scrolls=%d)",
            target,
            direction,
            max_scrolls,
        )

        for i in range(max_scrolls):
            # First try device's element finder (faster)
            coords = self._device.find_element(target)
            if coords:
                logger.debug("Element '%s' found after %d scroll(s) at %s", target, i, coords)
                return None  # Found it

            # Fall back to AI vision
            screenshot = self._device.take_screenshot()
            coords = self._ai.find_element(screenshot, target, width, height)
            if coords:
                logger.debug(
                    "Element '%s' found via AI after %d scroll(s) at %s", target, i, coords
                )
                return None  # Found it

            # Swipe in specified direction
            logger.debug("Scroll attempt %d/%d (%s)", i + 1, max_scrolls, direction)
            cx, cy = width // 2, height // 2
            distance = int(height * 0.3)  # 30% of screen

            if direction == "up":
                self._device.swipe(cx, cy, cx, cy + distance)
            elif direction == "down":
                self._device.swipe(cx, cy, cx, cy - distance)
            elif direction == "left":
                distance = int(width * 0.3)
                self._device.swipe(cx, cy, cx + distance, cy)
            elif direction == "right":
                distance = int(width * 0.3)
                self._device.swipe(cx, cy, cx - distance, cy)

        logger.debug(
            "Element '%s' not found after %d scroll attempts", target, max_scrolls
        )
        return f"Element '{target}' not found after {max_scrolls} scrolls"

    def _is_element_present(self, target: str) -> bool:
        """Check if element is present using device finder + AI fallback.

        Args:
            target: Element description

        Returns:
            True if element is found, False otherwise
        """
        logger.debug("Checking presence of element '%s'", target)

        # First try device's element finder (faster)
        coords = self._device.find_element(target)
        if coords:
            logger.debug("Element '%s' is present (accessibility) at %s", target, coords)
            return True

        # Fall back to AI vision
        width, height = self._get_screen_size()
        screenshot = self._device.take_screenshot()
        coords = self._ai.find_element(screenshot, target, width, height)
        is_present = coords is not None
        if is_present:
            logger.debug("Element '%s' is present (AI vision) at %s", target, coords)
        else:
            logger.debug("Element '%s' is not present", target)
        return is_present

    def _action_if_present(self, step: Step) -> str | None:
        """Execute then/else based on element presence (AI-assisted)."""
        target = step.condition_target
        if not target:
            return "No element specified for if_present"

        if self._is_element_present(target):
            # Element found, execute then branch
            logger.debug(
                "if_present('%s'): condition TRUE, executing %d then step(s)",
                target,
                len(step.then_steps),
            )
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            # Element not found, execute else branch
            logger.debug(
                "if_present('%s'): condition FALSE, executing %d else step(s)",
                target,
                len(step.else_steps),
            )
            return self._execute_nested_steps(step.else_steps)

        logger.debug("if_present('%s'): condition FALSE, no else branch", target)
        return None  # No else branch, just skip

    def _action_if_absent(self, step: Step) -> str | None:
        """Execute then/else based on element absence (AI-assisted)."""
        target = step.condition_target
        if not target:
            return "No element specified for if_absent"

        if not self._is_element_present(target):
            # Element not found, execute then branch
            logger.debug(
                "if_absent('%s'): condition TRUE (not found), executing %d then step(s)",
                target,
                len(step.then_steps),
            )
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            # Element found, execute else branch
            logger.debug(
                "if_absent('%s'): condition FALSE (found), executing %d else step(s)",
                target,
                len(step.else_steps),
            )
            return self._execute_nested_steps(step.else_steps)

        logger.debug("if_absent('%s'): condition FALSE (found), no else branch", target)
        return None

    def _action_if_screen(self, step: Step) -> str | None:
        """Execute then/else based on AI screen verification."""
        description = step.condition_target
        if not description:
            return "No screen description specified for if_screen"

        logger.debug("if_screen: verifying screen matches '%s'", description)
        screenshot = self._device.take_screenshot()
        result = self._ai.verify_screen(screenshot, description)

        if result.get("pass"):
            logger.debug(
                "if_screen('%s'): condition TRUE, executing %d then step(s)",
                description,
                len(step.then_steps),
            )
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            logger.debug(
                "if_screen('%s'): condition FALSE, executing %d else step(s)",
                description,
                len(step.else_steps),
            )
            return self._execute_nested_steps(step.else_steps)

        logger.debug("if_screen('%s'): condition FALSE, no else branch", description)
        return None

    def _execute_nested_steps(self, steps: list[Step]) -> str | None:
        """Execute a list of nested steps.

        Returns error message if any step fails, None otherwise.
        """
        if not steps:
            return None

        logger.debug("Executing %d nested step(s)", len(steps))
        for i, nested_step in enumerate(steps):
            result = self.execute_step(nested_step)
            if result.status == "failed":
                logger.debug("Nested step %d/%d failed: %s", i + 1, len(steps), result.error)
                return result.error

        logger.debug("All %d nested step(s) completed successfully", len(steps))
        return None
