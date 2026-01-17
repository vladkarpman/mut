"""Test execution engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.config import ConfigLoader, MutConfig
from mutcli.core.device_controller import DeviceController
from mutcli.models.test import Step, TestFile


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

        try:
            # Setup
            for step in test.setup:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = f"Setup failed: {result.error}"
                    return TestResult(
                        name=test.path or "unknown",
                        status=status,
                        duration=time.time() - start,
                        steps=results,
                        error=error,
                    )

            # Main steps
            for step in test.steps:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = result.error
                    break

            # Teardown (always run)
            for step in test.teardown:
                result = self.execute_step(step)
                results.append(result)

        except Exception as e:
            status = "error"
            error = str(e)

        return TestResult(
            name=test.path or "unknown",
            status=status,
            duration=time.time() - start,
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

        # Capture before screenshot
        screenshot_before = self._capture_screenshot()

        try:
            # Dispatch to action handler
            handler = getattr(self, f"_action_{step.action}", None)
            if handler is None:
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

            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed" if error else "passed",
                duration=time.time() - start,
                error=error,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
                details={"timestamp": time.time() - self._test_start},
            )

        except Exception as e:
            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed",
                duration=time.time() - start,
                error=str(e),
                screenshot_before=screenshot_before,
            )

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
            return self._coordinates_to_pixels(step), None

        # Case 2: Text + coordinates - validate with AI, use coordinates
        if has_text and has_coords and step.coordinates and step.target:
            coords = self._coordinates_to_pixels(step)
            if coords:
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
                    return None, (
                        f"Validation failed: expected '{step.target}' "
                        f"at ({x_pct:.0f}%, {y_pct:.0f}%), but: {reason}"
                    )

                return coords, None
            return None, f"Invalid coordinates for '{step.target}'"

        # Case 3: Text only - AI finds element
        if has_text and step.target:
            # First try device's element finder (faster, uses accessibility tree)
            coords = self._device.find_element(step.target)
            if coords:
                return coords, None

            # Fall back to AI vision
            screenshot = self._device.take_screenshot()
            coords = self._ai.find_element(screenshot, step.target, width, height)
            if coords:
                return coords, None

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

        while time.time() - start < timeout:
            if self._device.find_element(target):
                return None
            time.sleep(0.5)

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

        for i in range(max_scrolls):
            # First try device's element finder (faster)
            coords = self._device.find_element(target)
            if coords:
                return None  # Found it

            # Fall back to AI vision
            screenshot = self._device.take_screenshot()
            coords = self._ai.find_element(screenshot, target, width, height)
            if coords:
                return None  # Found it

            # Swipe in specified direction
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

        return f"Element '{target}' not found after {max_scrolls} scrolls"

    def _is_element_present(self, target: str) -> bool:
        """Check if element is present using device finder + AI fallback.

        Args:
            target: Element description

        Returns:
            True if element is found, False otherwise
        """
        # First try device's element finder (faster)
        coords = self._device.find_element(target)
        if coords:
            return True

        # Fall back to AI vision
        width, height = self._get_screen_size()
        screenshot = self._device.take_screenshot()
        coords = self._ai.find_element(screenshot, target, width, height)
        return coords is not None

    def _action_if_present(self, step: Step) -> str | None:
        """Execute then/else based on element presence (AI-assisted)."""
        target = step.condition_target
        if not target:
            return "No element specified for if_present"

        if self._is_element_present(target):
            # Element found, execute then branch
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            # Element not found, execute else branch
            return self._execute_nested_steps(step.else_steps)

        return None  # No else branch, just skip

    def _action_if_absent(self, step: Step) -> str | None:
        """Execute then/else based on element absence (AI-assisted)."""
        target = step.condition_target
        if not target:
            return "No element specified for if_absent"

        if not self._is_element_present(target):
            # Element not found, execute then branch
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            # Element found, execute else branch
            return self._execute_nested_steps(step.else_steps)

        return None

    def _action_if_screen(self, step: Step) -> str | None:
        """Execute then/else based on AI screen verification."""
        description = step.condition_target
        if not description:
            return "No screen description specified for if_screen"

        screenshot = self._device.take_screenshot()
        result = self._ai.verify_screen(screenshot, description)

        if result.get("pass"):
            return self._execute_nested_steps(step.then_steps)
        elif step.else_steps:
            return self._execute_nested_steps(step.else_steps)

        return None

    def _execute_nested_steps(self, steps: list[Step]) -> str | None:
        """Execute a list of nested steps.

        Returns error message if any step fails, None otherwise.
        """
        if not steps:
            return None

        for nested_step in steps:
            result = self.execute_step(nested_step)
            if result.status == "failed":
                return result.error

        return None
