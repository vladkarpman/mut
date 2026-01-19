"""Test execution engine."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.ai_recovery import AIRecovery
from mutcli.core.config import ConfigLoader, MutConfig
from mutcli.core.device_controller import DeviceController
from mutcli.models.test import Step, TestFile

if TYPE_CHECKING:
    from mutcli.core.console_reporter import ConsoleReporter
    from mutcli.core.scrcpy_service import ScrcpyService

logger = logging.getLogger("mut.executor")


@dataclass
class StepResult:
    """Result of executing a step."""

    step_number: int
    action: str
    status: str  # "passed", "failed", "skipped"
    target: str | None = None  # Element text or screen description
    description: str | None = None  # Human-readable step description
    duration: float = 0.0
    error: str | None = None
    screenshot_before: bytes | None = None
    screenshot_after: bytes | None = None
    # Action screenshots (varies by gesture type)
    # tap/double_tap: screenshot_action = touch moment
    # swipe: screenshot_action = swipe_start, screenshot_action_end = swipe_end
    # long_press: screenshot_action = press_start, screenshot_action_end = press_held
    screenshot_action: bytes | None = None
    screenshot_action_end: bytes | None = None
    # Screenshot file paths (for report - populated after video extraction)
    screenshot_before_path: Path | None = None
    screenshot_after_path: Path | None = None
    screenshot_action_path: Path | None = None
    screenshot_action_end_path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)
    # AI analysis results (populated by StepVerifier after execution)
    ai_verified: bool | None = None  # AI confirms step succeeded visually
    ai_outcome: str | None = None  # AI description of what happened
    ai_suggestion: str | None = None  # AI suggested fix if failed
    # Internal: timestamps for video-based frame extraction (relative to recording start)
    # These are populated during execution when video recording is active,
    # then used to extract precise frames from the video after recording stops.
    _ts_before: float | None = field(default=None, repr=False)
    _ts_after: float | None = field(default=None, repr=False)
    _ts_action: float | None = field(default=None, repr=False)
    _ts_action_end: float | None = field(default=None, repr=False)


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
        scrcpy: ScrcpyService | None = None,
        output_dir: Path | None = None,
        reporter: ConsoleReporter | None = None,
    ):
        """Initialize executor.

        Args:
            device_id: ADB device identifier
            config: Configuration (loads from files if not provided)
            ai_analyzer: AI analyzer (creates new if not provided)
            scrcpy: Optional ScrcpyService for fast screenshots and video recording
            output_dir: Output directory for reports and recordings
            reporter: Optional ConsoleReporter for live CLI output
        """
        self._device = DeviceController(device_id)
        self._config = config or ConfigLoader.load()
        self._ai = ai_analyzer or AIAnalyzer()
        self._ai_recovery = AIRecovery(self._ai)
        self._scrcpy = scrcpy
        self._output_dir = output_dir or Path.cwd()

        # Enable scrcpy injection for gestures if scrcpy has control
        if scrcpy is not None and scrcpy.is_control_ready:
            self._device.set_scrcpy_service(scrcpy)
        self._reporter = reporter
        self._screen_size: tuple[int, int] | None = None
        self._step_number = 0
        self._test_start: float = 0.0  # Track test start time for timestamps
        self._test_app: str | None = None  # App from test file config
        self._recording_video = False  # Whether video recording is active
        self._recording_start_time: float | None = None  # When video recording started
        self._recording_video_path: Path | None = None  # Path to video file for extraction
        self._step_coords: tuple[int, int] | None = None  # Track coords for report gestures
        self._step_end_coords: tuple[int, int] | None = None  # End coords for swipes
        self._step_direction: str | None = None  # Direction for swipes
        self._step_trajectory: list[dict[str, float]] | None = None  # Trajectory for swipes
        self._original_show_touches: bool | None = None  # Original show_touches setting
        # Action screenshots/timestamps captured during step execution
        self._step_action_screenshot: bytes | None = None
        self._step_action_end_screenshot: bytes | None = None
        self._step_action_timestamp: float | None = None
        self._step_action_end_timestamp: float | None = None

    def execute_test(self, test: TestFile, *, record_video: bool = False) -> TestResult:
        """Execute a complete test file.

        Args:
            test: Parsed test file
            record_video: If True and ScrcpyService is available, record video

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

        # Start video recording if requested
        if record_video and self._scrcpy:
            self._start_video_recording()

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

        finally:
            # Stop video recording if active and extract precise frames
            if self._recording_video:
                self._stop_video_recording()
                # Extract frames from video at stored timestamps for precise captures
                self._extract_frames_from_video(results)

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

        # Clear step state from previous step
        self._step_coords = None
        self._step_end_coords = None
        self._step_direction = None
        self._step_trajectory = None
        self._step_action_screenshot = None
        self._step_action_end_screenshot = None
        self._step_action_timestamp = None
        self._step_action_end_timestamp = None

        # Build step description for logging
        step_desc = self._format_step_description(step)
        logger.debug("Step %d: Starting %s", self._step_number, step_desc)

        # Notify reporter that step is starting
        if self._reporter:
            self._reporter.step_started(
                step_num=self._step_number,
                action=step.action,
                target=step.target or step.condition_target,
            )

        # Maestro-style: wait for screen to settle before action
        if self._step_number > 1:
            self._wait_to_settle(step)

        # Capture before screenshot and timestamp
        screenshot_before, ts_before = self._capture_screenshot_or_timestamp()

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

            # Execute with retry logic
            max_attempts = (step.retry or 0) + 1  # retry=2 means 3 total attempts
            error = None

            for attempt in range(1, max_attempts + 1):
                error = handler(step)
                if error is None:
                    break  # Success
                if attempt < max_attempts:
                    logger.debug(
                        "Step %d: Attempt %d/%d failed, retrying: %s",
                        self._step_number,
                        attempt,
                        max_attempts,
                        error,
                    )
                    time.sleep(0.5)  # Brief pause between retries

            # Capture after screenshot and timestamp
            screenshot_after, ts_after = self._capture_screenshot_or_timestamp()
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

            # Build details including gesture coordinates for report visualization
            details: dict[str, Any] = {"timestamp": time.time() - self._test_start}
            if self._step_coords and self._screen_size:
                # Store coordinates as percentages for responsive rendering
                details["coords"] = {
                    "x": self._step_coords[0] / self._screen_size[0] * 100,
                    "y": self._step_coords[1] / self._screen_size[1] * 100,
                }
                if self._step_end_coords:
                    details["end_coords"] = {
                        "x": self._step_end_coords[0] / self._screen_size[0] * 100,
                        "y": self._step_end_coords[1] / self._screen_size[1] * 100,
                    }
                if self._step_direction:
                    details["direction"] = self._step_direction
                if self._step_trajectory:
                    details["trajectory"] = self._step_trajectory
                    details["duration_ms"] = 300  # Default swipe duration

            # Use explicit description if provided, otherwise generate from step data
            description = step.description or self._format_step_description(step)

            result = StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed" if error else "passed",
                target=step.target or step.condition_target,
                description=description,
                duration=elapsed,
                error=error,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
                screenshot_action=self._step_action_screenshot,
                screenshot_action_end=self._step_action_end_screenshot,
                details=details,
                _ts_before=ts_before,
                _ts_after=ts_after,
                _ts_action=self._step_action_timestamp,
                _ts_action_end=self._step_action_end_timestamp,
            )

            # Notify reporter that step completed
            if self._reporter:
                self._reporter.step_completed(
                    step_num=self._step_number,
                    status=result.status,
                    error=result.error,
                )

            return result

        except Exception as e:
            elapsed = time.time() - start
            logger.exception(
                "Step %d: Exception in %s after %.2fs", self._step_number, step.action, elapsed
            )
            # Use explicit description if provided, otherwise generate from step data
            description = step.description or self._format_step_description(step)
            result = StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed",
                target=step.target or step.condition_target,
                description=description,
                duration=elapsed,
                error=str(e),
                screenshot_before=screenshot_before,
            )

            # Notify reporter that step completed (with failure)
            if self._reporter:
                self._reporter.step_completed(
                    step_num=self._step_number,
                    status=result.status,
                    error=result.error,
                )

            return result

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

    def _get_recording_timestamp(self) -> float | None:
        """Get current timestamp relative to recording start.

        Returns:
            Elapsed seconds since recording started, or None if not recording
        """
        if self._recording_video and self._recording_start_time is not None:
            return time.time() - self._recording_start_time
        return None

    def _capture_screenshot(self) -> bytes | None:
        """Capture screenshot from device if available.

        Uses ScrcpyService for faster screenshots (~50ms) when available,
        falls back to ADB screenshot otherwise.

        Returns:
            Screenshot bytes or None if capture fails
        """
        try:
            # Prefer ScrcpyService for fast screenshots
            if self._scrcpy and self._scrcpy.is_connected:
                return self._scrcpy.screenshot()
            return self._device.take_screenshot()
        except Exception:
            return None

    def _capture_screenshot_or_timestamp(self) -> tuple[bytes | None, float | None]:
        """Capture screenshot and/or timestamp for later frame extraction.

        When video recording is active, captures timestamp for precise frame
        extraction later. Also captures screenshot for immediate use.

        Returns:
            Tuple of (screenshot_bytes, timestamp_relative_to_recording)
        """
        timestamp = self._get_recording_timestamp()
        screenshot = self._capture_screenshot()
        return screenshot, timestamp

    def _start_video_recording(self) -> None:
        """Start video recording for test execution."""
        if not self._scrcpy:
            logger.warning("Cannot start recording: ScrcpyService not available")
            return

        # Ensure scrcpy is connected
        if not self._scrcpy.is_connected:
            logger.info("Connecting ScrcpyService for video recording...")
            if not self._scrcpy.connect():
                logger.error("Failed to connect ScrcpyService for recording")
                return

        # Enable show_touches to display touch indicators in video
        self._original_show_touches = self._device.get_show_touches()
        if not self._original_show_touches:
            self._device.set_show_touches(True)
            logger.info("Enabled show_touches for video recording")

        # Create recording directory
        recording_dir = self._output_dir / "recording"
        recording_dir.mkdir(parents=True, exist_ok=True)
        video_path = recording_dir / "video.mp4"

        result = self._scrcpy.start_recording(str(video_path))
        if result.get("success"):
            self._recording_video = True
            self._recording_start_time = time.time()
            self._recording_video_path = video_path
            logger.info("Video recording started: %s", video_path)
        else:
            logger.error("Failed to start video recording: %s", result.get("error"))
            # Restore show_touches on failure
            if self._original_show_touches is not None and not self._original_show_touches:
                self._device.set_show_touches(False)

    def _stop_video_recording(self) -> None:
        """Stop video recording."""
        if not self._scrcpy or not self._recording_video:
            return

        result = self._scrcpy.stop_recording()
        self._recording_video = False

        # Restore original show_touches setting
        if self._original_show_touches is not None and not self._original_show_touches:
            self._device.set_show_touches(False)
            logger.info("Restored show_touches to original setting")
        self._original_show_touches = None

        if result.get("success"):
            logger.info(
                "Video recording saved: %s (%.1fs, %d frames)",
                result.get("output_path"),
                result.get("duration_seconds", 0),
                result.get("frame_count", 0),
            )
        else:
            logger.error("Failed to stop video recording: %s", result.get("error"))

    # Timing offsets for frame extraction (in seconds)
    # These account for ADB command latency and UI rendering time
    # Values determined empirically based on typical Android device behavior
    FRAME_OFFSET_ACTION = 0.05  # 50ms offset for action frames (ADB latency)
    FRAME_OFFSET_AFTER = 0.20  # 200ms offset for "after" frames (UI render time)

    def _extract_frames_from_video(self, results: list[StepResult]) -> None:
        """Extract precise frames from video using stored timestamps.

        Uses FrameExtractor to extract frames at the timestamps stored during
        execution. Applies timing offsets to account for ADB latency and UI
        update time. Uses parallel extraction for performance.

        Timing offsets:
        - before: no offset (captured before action starts)
        - action/action_end: +50ms (ADB command latency)
        - after: +200ms (UI needs time to render result)

        Args:
            results: List of StepResult objects with _ts_* timestamps populated
        """
        if not self._recording_video_path or not self._recording_video_path.exists():
            logger.warning("No video file available for frame extraction")
            return

        # Build extraction list with timing offsets
        # Format: (step, ts_field, adjusted_timestamp)
        extractions: list[tuple[StepResult, str, float]] = []
        for step in results:
            for ts_field in ["_ts_before", "_ts_after", "_ts_action", "_ts_action_end"]:
                ts = getattr(step, ts_field, None)
                if ts is not None:
                    # Apply timing offsets based on frame type
                    if ts_field == "_ts_after":
                        ts = ts + self.FRAME_OFFSET_AFTER
                    elif ts_field in ("_ts_action", "_ts_action_end"):
                        ts = ts + self.FRAME_OFFSET_ACTION
                    # _ts_before: no offset needed
                    extractions.append((step, ts_field, ts))

        if not extractions:
            logger.debug("No timestamps to extract from video")
            return

        logger.info(
            "Extracting %d frames from video at %s (parallel)",
            len(extractions),
            self._recording_video_path,
        )

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            from mutcli.core.frame_extractor import FrameExtractor

            extractor = FrameExtractor(self._recording_video_path)

            # Parallel extraction using ThreadPoolExecutor
            max_workers = min(16, len(extractions))
            extracted_count = 0

            def extract_single(
                item: tuple[StepResult, str, float],
            ) -> tuple[StepResult, str, bytes | None]:
                """Extract a single frame and return with metadata."""
                step, ts_field, timestamp = item
                frame_bytes = extractor.extract_frame(timestamp)
                return step, ts_field, frame_bytes

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(extract_single, item): item for item in extractions
                }

                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        step, ts_field, frame_bytes = future.result()
                        if frame_bytes:
                            # Map timestamp field to screenshot field
                            screenshot_field = ts_field.replace("_ts_", "screenshot_")
                            setattr(step, screenshot_field, frame_bytes)
                            extracted_count += 1
                        else:
                            logger.warning(
                                "Failed to extract frame at %.3fs for step %d (%s)",
                                item[2],
                                item[0].step_number,
                                ts_field,
                            )
                    except Exception as e:
                        logger.warning(
                            "Exception extracting frame for step %d: %s",
                            item[0].step_number,
                            e,
                        )

            logger.info(
                "Extracted %d/%d frames from video",
                extracted_count,
                len(extractions),
            )

        except Exception as e:
            logger.exception("Failed to extract frames from video: %s", e)

    def _get_screen_size(self) -> tuple[int, int]:
        """Get cached screen size."""
        if self._screen_size is None:
            self._screen_size = self._device.get_screen_size()
        return self._screen_size

    def _wait_for_screen_stability(self, timeout: float = 2.0) -> bool:
        """Wait for screen to stabilize (stop changing).

        Uses hash comparison to detect when UI animations complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if screen stabilized, False if timeout reached
        """
        poll_interval = self._config.resilience.poll_interval
        stability_threshold = self._config.resilience.stability_frames

        start = time.time()
        last_hash: int | None = None
        stable_count = 0

        while time.time() - start < timeout:
            screenshot = self._capture_screenshot()
            if screenshot:
                current_hash = hash(screenshot)
                if current_hash == last_hash:
                    stable_count += 1
                    if stable_count >= stability_threshold:
                        elapsed = time.time() - start
                        logger.debug("Screen stabilized after %.2fs", elapsed)
                        return True
                else:
                    stable_count = 0
                    last_hash = current_hash

            time.sleep(poll_interval)

        logger.debug("Screen stability timeout after %.2fs", timeout)
        return False

    def _wait_to_settle(self, step: Step) -> None:
        """Wait for screen to settle before executing a step (Maestro-style).

        Like Maestro's waitToSettleTimeoutMs - waits until screen stops changing,
        not for a fixed duration. This handles animations, loading states, etc.

        Args:
            step: Step about to be executed
        """
        # Skip for non-UI actions
        if step.action in ("wait", "launch_app", "terminate_app"):
            return

        # Use step-level timeout if specified, otherwise use config default
        timeout = step.wait_to_settle_timeout
        if timeout is None:
            timeout = self._config.resilience.wait_to_settle_timeout

        if timeout <= 0:
            return

        logger.debug("Waiting for screen to settle (max %.1fs)...", timeout)
        self._wait_for_screen_stability(timeout=timeout)

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

    def _synthesize_trajectory(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        duration_ms: int,
        num_points: int = 15,
    ) -> list[dict[str, float]]:
        """Generate trajectory points for swipe visualization.

        Uses ease-out-quad easing for natural finger motion.

        Args:
            start: Start coordinates (x, y) in pixels
            end: End coordinates (x, y) in pixels
            duration_ms: Swipe duration in milliseconds
            num_points: Number of trajectory points to generate

        Returns:
            List of trajectory points with x, y (percentages) and t (ms)
        """

        def ease_out_quad(t: float) -> float:
            return t * (2 - t)

        width, height = self._get_screen_size()
        points = []

        for i in range(num_points):
            t = i / (num_points - 1) if num_points > 1 else 0
            t_eased = ease_out_quad(t)

            x = start[0] + (end[0] - start[0]) * t_eased
            y = start[1] + (end[1] - start[1]) * t_eased

            points.append({
                "x": x / width * 100,
                "y": y / height * 100,
                "t": int(t * duration_ms),
            })

        return points

    def _find_element_with_wait(
        self, target: str, timeout: float | None = None
    ) -> tuple[int, int] | None:
        """Find element with implicit wait and screen stability detection.

        Layer 1 of resilience: polls for element with stability checks.

        Args:
            target: Element text/description to find
            timeout: Override timeout (uses config.resilience.implicit_wait if None)

        Returns:
            (x, y) coordinates if found, None if timeout reached
        """
        timeout = timeout if timeout is not None else self._config.resilience.implicit_wait
        poll_interval = self._config.resilience.poll_interval
        stability_threshold = self._config.resilience.stability_frames
        width, height = self._get_screen_size()

        start = time.time()
        last_screenshot_hash: int | None = None
        stable_count = 0
        attempt = 0
        screenshots_working = True  # Track if screenshots are available

        logger.debug(
            "Finding element '%s' with wait (timeout=%.1fs, poll=%.2fs, stability=%d)",
            target, timeout, poll_interval, stability_threshold,
        )

        while time.time() - start < timeout:
            attempt += 1
            screenshot = self._capture_screenshot()

            # Check screen stability using hash comparison
            if screenshot:
                current_hash = hash(screenshot)
                if current_hash == last_screenshot_hash:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_screenshot_hash = current_hash
            else:
                # Screenshots not working - mark and skip stability check
                screenshots_working = False

            # Search when screen is stable OR when screenshots aren't working
            # (if screenshots fail, we can't check stability, so just try finding)
            should_search = (
                stable_count >= stability_threshold - 1 or not screenshots_working
            )

            if should_search:
                # Try accessibility tree first (fast, always enabled)
                coords = self._device.find_element(target)
                if coords:
                    elapsed = time.time() - start
                    logger.debug(
                        "Element '%s' found via accessibility at %s (%.2fs, %d attempts)",
                        target, coords, elapsed, attempt,
                    )
                    return coords

                # Try AI vision only if ai_fallback is enabled
                if self._config.resilience.ai_fallback and screenshot:
                    coords = self._ai.find_element(screenshot, target, width, height)
                    if coords:
                        elapsed = time.time() - start
                        logger.debug(
                            "Element '%s' found via AI at %s (%.2fs, %d attempts)",
                            target, coords, elapsed, attempt,
                        )
                        return coords

            time.sleep(poll_interval)

        elapsed = time.time() - start
        logger.debug(
            "Element '%s' not found after %.2fs (%d attempts)",
            target, elapsed, attempt,
        )
        return None

    def _resolve_coordinates_ai(self, step: Step) -> tuple[tuple[int, int] | None, str | None]:
        """Resolve coordinates using AI-first approach with smart waits.

        Strategy:
        1. coordinates only (no text) → use coordinates directly
        2. text + coordinates → find element by text, use recorded coords as fallback
        3. text only → find element with smart wait (Layer 1)

        Returns:
            (coordinates, error) - coordinates are (x, y) or None, error is message or None
        """
        has_text = bool(step.target)
        has_coords = bool(step.coordinates)

        # Case 1: Coordinates only - use directly, no AI
        if has_coords and not has_text:
            coords = self._coordinates_to_pixels(step)
            logger.debug("Using direct coordinates: %s", coords)
            return coords, None

        # Case 2: Text + coordinates - find element by text, use recorded coords as fallback
        # Note: We don't validate that text is at recorded coords - that would be overly strict.
        # Recorded coordinates are hints from recording, not assertions.
        if has_text and has_coords and step.coordinates and step.target:
            # First try to find element by text (more resilient to UI changes)
            coords = self._find_element_with_wait(step.target, step.timeout)
            if coords:
                logger.debug(
                    "Element '%s' found at %s (ignoring recorded coords)", step.target, coords
                )
                return coords, None

            # Element not found by text - fall back to recorded coordinates
            fallback_coords = self._coordinates_to_pixels(step)
            if fallback_coords:
                logger.debug(
                    "Element '%s' not found by text, using recorded coords as fallback: %s",
                    step.target,
                    fallback_coords,
                )
                return fallback_coords, None
            return None, f"Element '{step.target}' not found and invalid fallback coordinates"

        # Case 3: Text only - find element with smart wait (Layer 1)
        if has_text and step.target:
            coords = self._find_element_with_wait(step.target, step.timeout)
            if coords:
                return coords, None

            # Layer 1 exhausted - try Layer 2 (AI recovery) if enabled
            ai_recovery_enabled = (
                step.ai_recovery if step.ai_recovery is not None
                else self._config.resilience.ai_recovery
            )

            if ai_recovery_enabled and self._ai_recovery.is_available:
                logger.debug("Layer 1 failed, trying AI recovery for '%s'", step.target)
                screenshot = self._capture_screenshot()
                if screenshot:
                    recovery = self._ai_recovery.analyze_element_not_found(
                        screenshot=screenshot,
                        target=step.target,
                        action=step.action,
                        screen_size=self._get_screen_size(),
                    )
                    logger.debug(
                        "AI recovery result: action=%s, reason=%s",
                        recovery.action, recovery.reason,
                    )

                    if recovery.action == "retry" and recovery.wait_seconds:
                        # AI suggests waiting more
                        logger.debug("AI suggests retry after %.1fs", recovery.wait_seconds)
                        time.sleep(recovery.wait_seconds)
                        coords = self._find_element_with_wait(step.target, 2.0)  # Short retry
                        if coords:
                            return coords, None

                    elif recovery.action == "alternative":
                        # AI found alternative target or coordinates
                        if recovery.alternative_coords:
                            logger.debug(
                                "AI suggests coordinates: %s", recovery.alternative_coords
                            )
                            return recovery.alternative_coords, None
                        elif recovery.alternative_target:
                            logger.debug(
                                "AI suggests alternative target: '%s'",
                                recovery.alternative_target,
                            )
                            coords = self._find_element_with_wait(
                                recovery.alternative_target, 2.0
                            )
                            if coords:
                                return coords, None

                    # AI recovery failed or suggested fail
                    return None, f"Element '{step.target}' not found (AI: {recovery.reason})"

            return None, f"Element '{step.target}' not found"

        return None, "No target or coordinates specified"

    # Action handlers

    def _tap_with_retry(self, x: int, y: int, step: Step) -> bool:
        """Execute tap with retry-if-no-change behavior (Maestro-style).

        Like Maestro's retryTapIfNoChange - if screen doesn't change after tap,
        retry the tap. Handles race conditions where tap fires before element
        is fully interactive.

        Args:
            x: X coordinate
            y: Y coordinate
            step: Step being executed (for retry settings)

        Returns:
            True if tap caused screen change, False if no change after retries
        """
        # Determine if retry is enabled
        retry_enabled = step.retry_if_no_change
        if retry_enabled is None:
            retry_enabled = self._config.resilience.retry_if_no_change

        max_retries = self._config.resilience.retry_if_no_change_limit if retry_enabled else 1

        for attempt in range(max_retries):
            # Capture screenshot before tap
            before_screenshot = self._capture_screenshot()
            before_hash = hash(before_screenshot) if before_screenshot else None

            # Perform tap
            self._device.tap(x, y)

            # Wait briefly for UI to respond
            time.sleep(0.3)

            # Check if screen changed
            after_screenshot = self._capture_screenshot()
            after_hash = hash(after_screenshot) if after_screenshot else None

            if before_hash != after_hash:
                # Screen changed - tap was successful
                if attempt > 0:
                    logger.debug("Tap succeeded on attempt %d/%d", attempt + 1, max_retries)
                return True

            if attempt < max_retries - 1:
                logger.debug(
                    "Screen didn't change after tap, retrying (%d/%d)...",
                    attempt + 1, max_retries
                )
                # Wait a bit before retrying
                time.sleep(0.2)

        logger.debug("Screen didn't change after %d tap attempts", max_retries)
        return False

    def _action_tap(self, step: Step) -> str | None:
        """Execute tap action with retry-if-no-change (Maestro-style)."""
        coords, error = self._resolve_coordinates_ai(step)
        if error:
            return error
        if coords is None:
            return "Could not resolve coordinates for tap"

        self._step_coords = coords  # Store for report gesture indicator

        # Use tap with retry behavior
        self._tap_with_retry(coords[0], coords[1], step)

        # Capture action screenshot and timestamp
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_screenshot = screenshot
        self._step_action_timestamp = timestamp
        return None

    def _action_double_tap(self, step: Step) -> str | None:
        """Execute double tap action using AI-first approach."""
        coords, error = self._resolve_coordinates_ai(step)
        if error:
            return error
        if coords is None:
            return "Could not resolve coordinates for double_tap"

        self._step_coords = coords  # Store for report gesture indicator
        self._device.double_tap(coords[0], coords[1])
        # Capture action screenshot and timestamp after double tap
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_screenshot = screenshot
        self._step_action_timestamp = timestamp
        return None

    def _action_type(self, step: Step) -> str | None:
        """Execute type action."""
        text = step.text or step.target
        if not text:
            return "No text to type"

        self._device.type_text(text)
        return None

    def _swipe_with_retry(
        self,
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        duration_ms: int,
        step: Step,
    ) -> bool:
        """Execute swipe with retry-if-no-change behavior (Maestro-style).

        Args:
            start_x, start_y: Start coordinates
            end_x, end_y: End coordinates
            duration_ms: Swipe duration in milliseconds
            step: Step being executed (for retry settings)

        Returns:
            True if swipe caused screen change, False if no change after retries
        """
        # Determine if retry is enabled
        retry_enabled = step.retry_if_no_change
        if retry_enabled is None:
            retry_enabled = self._config.resilience.retry_if_no_change

        max_retries = self._config.resilience.retry_if_no_change_limit if retry_enabled else 1

        for attempt in range(max_retries):
            # Capture screenshot before swipe
            before_screenshot = self._capture_screenshot()
            before_hash = hash(before_screenshot) if before_screenshot else None

            # Perform swipe
            self._device.swipe(start_x, start_y, end_x, end_y, duration_ms)

            # Wait for UI to settle
            time.sleep(0.3)

            # Check if screen changed
            after_screenshot = self._capture_screenshot()
            after_hash = hash(after_screenshot) if after_screenshot else None

            if before_hash != after_hash:
                if attempt > 0:
                    logger.debug("Swipe succeeded on attempt %d/%d", attempt + 1, max_retries)
                return True

            if attempt < max_retries - 1:
                logger.debug(
                    "Screen didn't change after swipe, retrying (%d/%d)...",
                    attempt + 1, max_retries
                )
                time.sleep(0.2)

        logger.debug("Screen didn't change after %d swipe attempts", max_retries)
        return False

    def _action_swipe(self, step: Step) -> str | None:
        """Execute swipe action with retry-if-no-change (Maestro-style)."""
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
        self._step_coords = (cx, cy)  # Store start coords for report
        self._step_direction = direction

        if direction == "up":
            end_x, end_y = cx, cy - distance_px
        elif direction == "down":
            end_x, end_y = cx, cy + distance_px
        elif direction == "left":
            distance_px = int(distance * width / 100)
            end_x, end_y = cx - distance_px, cy
        elif direction == "right":
            distance_px = int(distance * width / 100)
            end_x, end_y = cx + distance_px, cy
        else:
            return f"Unknown swipe direction: {direction}"

        # Clamp coordinates to screen boundaries (mobile-mcp pattern)
        end_x = max(0, min(width - 1, end_x))
        end_y = max(0, min(height - 1, end_y))

        self._step_end_coords = (end_x, end_y)  # Store end coords for report

        # Capture swipe_start screenshot before swipe
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_screenshot = screenshot
        self._step_action_timestamp = timestamp

        # Generate trajectory for visualization
        duration_ms = step.duration or 300  # Use recorded duration or default
        self._step_trajectory = self._synthesize_trajectory(
            (cx, cy), (end_x, end_y), duration_ms
        )

        # Execute swipe with retry behavior
        self._swipe_with_retry(cx, cy, end_x, end_y, duration_ms, step)

        # Capture swipe_end screenshot
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_end_screenshot = screenshot
        self._step_action_end_timestamp = timestamp

        return None

    def _action_wait(self, step: Step) -> str | None:
        """Execute wait action."""
        duration = step.timeout or 1.0
        time.sleep(duration)
        return None

    def _action_wait_for(self, step: Step) -> str | None:
        """Wait for element to appear using smart wait with stability detection."""
        target = step.target
        if not target:
            return "No element to wait for"

        # Use step timeout, fall back to config wait_for timeout
        timeout = step.timeout or self._config.timeouts.wait_for
        coords = self._find_element_with_wait(target, timeout)

        if coords:
            return None
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
        """Verify screen matches description using AI with Layer 2 recovery.

        Takes a screenshot and asks AI to verify it matches the expected state.
        If verification fails, Layer 2 AI recovery may suggest waiting for
        screen transitions to complete.

        Returns:
            None if verification passes, error message if it fails
        """
        description = step.target or step.description
        if not description:
            return "No description provided for verify_screen"

        if not self._ai.is_available:
            logger.warning("AI not available, skipping verify_screen: %s", description)
            return None

        logger.debug("Verifying screen: %s", description)
        screenshot = self._device.take_screenshot()
        result = self._ai.verify_screen(screenshot, description)

        if result.get("pass"):
            logger.debug("Screen verification passed: %s", description)
            return None

        reason = result.get("reason", "Screen does not match expected state")
        logger.debug("Screen verification failed: %s - %s", description, reason)

        # Layer 2: AI recovery for verify_screen failures
        ai_recovery_enabled = (
            step.ai_recovery if step.ai_recovery is not None
            else self._config.resilience.ai_recovery
        )

        if ai_recovery_enabled and self._ai_recovery.is_available and screenshot:
            logger.debug("Trying AI recovery for verify_screen failure")
            recovery = self._ai_recovery.analyze_verify_screen_failed(
                screenshot=screenshot,
                description=description,
                failure_reason=reason,
            )
            logger.debug(
                "AI recovery result: action=%s, reason=%s",
                recovery.action, recovery.reason,
            )

            if recovery.action == "retry" and recovery.wait_seconds:
                # AI suggests waiting for transition to complete
                logger.debug("AI suggests retry after %.1fs", recovery.wait_seconds)
                time.sleep(recovery.wait_seconds)

                # Retry verification
                screenshot = self._device.take_screenshot()
                result = self._ai.verify_screen(screenshot, description)
                if result.get("pass"):
                    logger.debug("Screen verification passed after AI-suggested wait")
                    return None

                reason = result.get("reason", reason)

            return f"verify_screen failed: {reason} (AI: {recovery.reason})"

        return f"verify_screen failed: {reason}"

    def _action_hide_keyboard(self, step: Step) -> str | None:
        """Hide keyboard by pressing back."""
        self._device.press_key("BACK")
        return None

    def _action_long_press(self, step: Step) -> str | None:
        """Execute long press action with mid-press screenshot capture."""
        coords, error = self._resolve_coordinates_ai(step)
        if error:
            return error
        if coords is None:
            return "Could not resolve coordinates for long_press"

        self._step_coords = coords  # Store for report gesture indicator
        duration_ms = step.duration or 500  # Default 500ms

        # Capture press_start screenshot and timestamp before press begins
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_screenshot = screenshot
        self._step_action_timestamp = timestamp

        # Execute long press asynchronously to capture mid-action
        process = self._device.long_press_async(coords[0], coords[1], duration_ms)

        # Wait 70% of duration, then capture press_held
        time.sleep(duration_ms * 0.7 / 1000)
        screenshot, timestamp = self._capture_screenshot_or_timestamp()
        self._step_action_end_screenshot = screenshot
        self._step_action_end_timestamp = timestamp

        # Wait for press to complete
        process.wait()

        return None

    def _action_scroll_to(self, step: Step) -> str | None:
        """Scroll until element is visible using AI-first approach with stability waits.

        Note: direction refers to scroll direction (content movement).
        'down' scrolls content down (revealing content below).
        """
        target = step.target
        if not target:
            return "No element specified for scroll_to"

        direction = (step.direction or "down").lower()
        max_scrolls = step.max_scrolls or 10
        width, height = self._get_screen_size()
        poll_interval = self._config.resilience.poll_interval

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

            # Wait for scroll animation to settle
            time.sleep(poll_interval)

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

    def _action_repeat(self, step: Step) -> str | None:
        """Execute steps repeatedly for a specified count."""
        count = step.repeat_count or 1
        steps = step.repeat_steps

        if not steps:
            logger.debug("repeat: no steps to repeat")
            return None

        logger.debug("repeat: executing %d step(s) %d time(s)", len(steps), count)

        for iteration in range(count):
            logger.debug("repeat: iteration %d/%d", iteration + 1, count)
            error = self._execute_nested_steps(steps)
            if error:
                logger.debug(
                    "repeat: iteration %d/%d failed: %s", iteration + 1, count, error
                )
                return f"repeat iteration {iteration + 1} failed: {error}"

        logger.debug("repeat: all %d iterations completed successfully", count)
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
