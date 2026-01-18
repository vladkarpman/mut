"""Touch event monitoring via adb getevent."""

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from mutcli.core.adb_state_monitor import ADBStateMonitor

logger = logging.getLogger("mut.touch")


@dataclass
class TrajectoryPoint:
    """A single point in a touch trajectory."""
    timestamp: float  # Seconds since monitoring started
    x: int  # Screen X coordinate
    y: int  # Screen Y coordinate


@dataclass
class TouchEvent:
    """A single touch event captured from the device.

    Attributes:
        timestamp: Seconds since monitoring started (touch END time)
        x: End X coordinate in pixels
        y: End Y coordinate in pixels
        gesture: Type of gesture ("tap", "swipe", "long_press")
        duration_ms: Touch duration in milliseconds
        start_x: Start X coordinate
        start_y: Start Y coordinate
        trajectory: Full path of touch points (for detailed analysis)
        path_distance: Total distance traveled along path in pixels
    """

    timestamp: float
    x: int
    y: int
    gesture: str
    duration_ms: int
    start_x: int
    start_y: int
    trajectory: list[TrajectoryPoint]
    path_distance: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "x": self.x,
            "y": self.y,
            "gesture": self.gesture,
            "duration_ms": self.duration_ms,
            "start_x": self.start_x,
            "start_y": self.start_y,
            "path_distance": round(self.path_distance, 1),
        }
        # Include trajectory for swipes (useful for replay/analysis)
        if self.gesture == "swipe" and self.trajectory:
            result["trajectory"] = [
                {"t": round(p.timestamp, 3), "x": p.x, "y": p.y}
                for p in self.trajectory
            ]
        return result


class TouchMonitor:
    """Monitor touch events via adb getevent.

    Captures touch events from an Android device using `adb getevent -lt`.
    Runs in a background thread and stores events in a thread-safe list.
    Coordinates are automatically scaled from touch panel to screen pixels.

    Gesture classification:
    - tap: duration < 200ms AND distance < 50px
    - long_press: duration >= 500ms AND distance < 100px
    - swipe: distance >= 100px

    Usage:
        monitor = TouchMonitor("device-id")
        monitor.start()
        # ... user interacts with device ...
        monitor.stop()
        events = monitor.get_events()
    """

    # Gesture classification thresholds
    TAP_MAX_DURATION_MS = 200
    TAP_MAX_DISTANCE_PX = 50
    LONG_PRESS_MIN_DURATION_MS = 500
    SWIPE_MIN_DISTANCE_PX = 100

    def __init__(self, device_id: str):
        """Initialize monitor for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._events: list[TouchEvent] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._start_time: float | None = None

        # Touch state tracking
        self._current_x: int | None = None
        self._current_y: int | None = None
        self._touch_down: bool = False
        self._touch_down_time: float | None = None
        self._touch_start_x: int | None = None
        self._touch_start_y: int | None = None
        self._trajectory: list[TrajectoryPoint] = []  # Full path during touch

        # Coordinate scaling (touch panel -> screen pixels)
        # Will be detected from device in _get_device_info()
        self._touch_max_x: int | None = None
        self._touch_max_y: int | None = None
        self._screen_width: int | None = None
        self._screen_height: int | None = None

        # ADB state monitor for keyboard/activity/windows
        self._adb_state_monitor: ADBStateMonitor | None = None

    @property
    def is_running(self) -> bool:
        """Check if monitoring is active."""
        return self._running

    def _get_device_info(self) -> bool:
        """Query device for screen size and touch coordinate bounds.

        Returns:
            True if device info was retrieved successfully.
        """
        # Get screen size
        result = subprocess.run(
            ["adb", "-s", self._device_id, "shell", "wm", "size"],
            capture_output=True,
            text=True,
        )
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        if match:
            self._screen_width = int(match.group(1))
            self._screen_height = int(match.group(2))
        else:
            logger.error("Failed to get screen size from device")
            return False

        # Get touch coordinate bounds from getevent -lp
        result = subprocess.run(
            ["adb", "-s", self._device_id, "shell", "getevent", "-lp"],
            capture_output=True,
            text=True,
        )

        for line in result.stdout.split("\n"):
            if "ABS_MT_POSITION_X" in line:
                match = re.search(r"max (\d+)", line)
                if match:
                    self._touch_max_x = int(match.group(1))
            elif "ABS_MT_POSITION_Y" in line:
                match = re.search(r"max (\d+)", line)
                if match:
                    self._touch_max_y = int(match.group(1))

        if self._touch_max_x is None or self._touch_max_y is None:
            logger.error("Failed to get touch bounds from device")
            return False

        logger.info(
            f"Device info: screen={self._screen_width}x{self._screen_height}, "
            f"touch_max={self._touch_max_x}x{self._touch_max_y}"
        )
        return True

    def _raw_to_screen(self, raw_x: int, raw_y: int) -> tuple[int, int]:
        """Convert raw touch coordinates to screen pixels."""
        max_x = self._touch_max_x
        max_y = self._touch_max_y
        width = self._screen_width
        height = self._screen_height

        if max_x is None or max_y is None or width is None or height is None:
            return raw_x, raw_y

        screen_x = int((raw_x / max_x) * width)
        screen_y = int((raw_y / max_y) * height)
        return screen_x, screen_y

    def start(self, reference_time: float | None = None) -> bool:
        """Start monitoring touch events.

        Args:
            reference_time: Optional reference timestamp (time.time()).
                           If provided, touch timestamps are relative to this.
                           Use video start time for synchronization.

        Returns:
            True if started successfully, False on error.
        """
        if self._running:
            return True

        # Get device info (screen size and touch bounds)
        if not self._get_device_info():
            logger.error("Failed to get device info, cannot start monitoring")
            return False

        try:
            # Launch adb getevent
            cmd = [
                "adb", "-s", self._device_id,
                "shell", "getevent", "-lt",
            ]

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self._running = True
            # Use provided reference time or current time
            self._start_time = reference_time if reference_time is not None else time.time()

            # Start ADB state monitor
            self._adb_state_monitor = ADBStateMonitor(self._device_id)
            self._adb_state_monitor.start()

            # Start processing thread
            self._thread = threading.Thread(
                target=self._process_loop,
                daemon=True,
            )
            self._thread.start()

            logger.info(f"Touch monitoring started for {self._device_id}")
            return True

        except OSError as e:
            logger.error(f"Failed to start touch monitoring: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        """Stop monitoring touch events."""
        self._running = False

        # Stop ADB state monitor
        if self._adb_state_monitor:
            self._adb_state_monitor.stop()

        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None

        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

        logger.info("Touch monitoring stopped")

    def get_events(self) -> list[TouchEvent]:
        """Get all captured events.

        Returns:
            Copy of the event list (thread-safe).
        """
        with self._lock:
            return list(self._events)

    def clear_events(self) -> None:
        """Clear all captured events."""
        with self._lock:
            self._events.clear()

    def _process_loop(self) -> None:
        """Process getevent output in background thread."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in self._process.stdout:
                if not self._running:
                    break
                self._parse_line(line.strip())

        except Exception as e:
            logger.debug(f"Process loop error: {e}")

    def _parse_line(self, line: str) -> None:
        """Parse a single getevent output line.

        Format: [timestamp] /dev/input/eventX: TYPE CODE VALUE
        Example: [   123.456789] /dev/input/event5: EV_ABS ABS_MT_POSITION_X 00000219

        Args:
            line: Raw getevent output line
        """
        # Match getevent format with -lt flags
        match = re.match(
            r"\[\s*([\d.]+)\]\s+\S+:\s+(\w+)\s+(\w+)\s+(\w+)",
            line,
        )
        if not match:
            return

        _, ev_type, code, value_hex = match.groups()

        if ev_type == "EV_ABS":
            self._handle_abs_event(code, value_hex)
        elif ev_type == "EV_KEY":
            self._handle_key_event(code, value_hex)

    def _handle_abs_event(self, code: str, value_hex: str) -> None:
        """Handle absolute position events.

        Captures position updates and adds to trajectory during active touch.

        Args:
            code: Event code (ABS_MT_POSITION_X, ABS_MT_POSITION_Y)
            value_hex: Hex value string
        """
        try:
            value = int(value_hex, 16)
        except ValueError:
            return

        if code == "ABS_MT_POSITION_X":
            self._current_x = value
        elif code == "ABS_MT_POSITION_Y":
            self._current_y = value

        # Add to trajectory if touch is active and we have both coordinates
        if (self._touch_down and self._start_time is not None
                and self._current_x is not None and self._current_y is not None):
            screen_x, screen_y = self._raw_to_screen(self._current_x, self._current_y)
            timestamp = time.time() - self._start_time
            self._trajectory.append(TrajectoryPoint(timestamp, screen_x, screen_y))

    def _handle_key_event(self, code: str, value_hex: str) -> None:
        """Handle key events (BTN_TOUCH).

        Args:
            code: Event code (BTN_TOUCH)
            value_hex: Hex value string or DOWN/UP
        """
        if code != "BTN_TOUCH":
            return

        # With -l flag, values can be "DOWN"/"UP" or hex codes
        if value_hex in ("00000001", "DOWN"):
            self._touch_down = True
            self._touch_down_time = time.time()
            self._trajectory = []  # Reset trajectory for new touch
            # Store start position (converted to screen pixels)
            if self._current_x is not None and self._current_y is not None:
                self._touch_start_x, self._touch_start_y = self._raw_to_screen(
                    self._current_x, self._current_y
                )
        elif value_hex in ("00000000", "UP"):
            self._record_gesture()
            self._touch_down = False
            self._touch_down_time = None
            self._touch_start_x = None
            self._touch_start_y = None
            self._current_x = None
            self._current_y = None
            self._trajectory = []  # Clear trajectory

    def _calculate_path_distance(self, trajectory: list[TrajectoryPoint]) -> float:
        """Calculate total distance traveled along the trajectory path.

        This is more accurate than start-to-end distance for detecting swipes,
        especially for curved gestures that end near where they started.

        Args:
            trajectory: List of trajectory points

        Returns:
            Total path distance in pixels
        """
        if len(trajectory) < 2:
            return 0.0

        total_distance = 0.0
        for i in range(1, len(trajectory)):
            dx = trajectory[i].x - trajectory[i - 1].x
            dy = trajectory[i].y - trajectory[i - 1].y
            total_distance += (dx ** 2 + dy ** 2) ** 0.5

        return total_distance

    def _classify_gesture(self, duration_ms: int, path_distance: float) -> str:
        """Classify touch gesture based on duration and path distance.

        Uses total path distance (not start-to-end) for accurate swipe detection.

        Args:
            duration_ms: Touch duration in milliseconds
            path_distance: Total distance traveled along path in pixels

        Returns:
            Gesture type: "tap", "swipe", or "long_press"
        """
        if path_distance >= self.SWIPE_MIN_DISTANCE_PX:
            return "swipe"
        elif duration_ms >= self.LONG_PRESS_MIN_DURATION_MS:
            return "long_press"
        elif duration_ms < self.TAP_MAX_DURATION_MS and path_distance < self.TAP_MAX_DISTANCE_PX:
            return "tap"
        else:
            # Ambiguous case - default to tap
            return "tap"

    def _record_gesture(self) -> None:
        """Record a gesture when touch is released."""
        if self._current_x is None or self._current_y is None:
            return
        if self._start_time is None:
            return
        if self._touch_down_time is None:
            return

        now = time.time()
        timestamp = now - self._start_time
        duration_ms = int((now - self._touch_down_time) * 1000)

        # Convert end position to screen pixels
        end_x, end_y = self._raw_to_screen(self._current_x, self._current_y)

        # Use start position or fall back to end position
        start_x = self._touch_start_x if self._touch_start_x is not None else end_x
        start_y = self._touch_start_y if self._touch_start_y is not None else end_y

        # Calculate path distance from full trajectory
        path_distance = self._calculate_path_distance(self._trajectory)

        # Classify gesture using path distance
        gesture = self._classify_gesture(duration_ms, path_distance)

        # Copy trajectory for the event
        trajectory_copy = list(self._trajectory)

        event = TouchEvent(
            timestamp=timestamp,
            x=end_x,
            y=end_y,
            gesture=gesture,
            duration_ms=duration_ms,
            start_x=start_x,
            start_y=start_y,
            trajectory=trajectory_copy,
            path_distance=path_distance,
        )

        with self._lock:
            self._events.append(event)

        logger.debug(
            f"{gesture.upper()}: ({start_x},{start_y})->({end_x},{end_y}) "
            f"{duration_ms}ms path={path_distance:.0f}px"
        )

    def get_keyboard_states(self) -> list[tuple[float, bool]]:
        """Get recorded keyboard visibility states.

        Returns:
            List of (timestamp, is_visible) tuples.
        """
        if self._adb_state_monitor:
            return self._adb_state_monitor.get_keyboard_states()
        return []

    def get_activity_states(self) -> list[tuple[float, str | None]]:
        """Get recorded activity states.

        Returns:
            List of (timestamp, activity_name) tuples.
        """
        if self._adb_state_monitor:
            return self._adb_state_monitor.get_activity_states()
        return []

    def get_window_states(self) -> list[tuple[float, list[str]]]:
        """Get recorded window states.

        Returns:
            List of (timestamp, window_list) tuples.
        """
        if self._adb_state_monitor:
            return self._adb_state_monitor.get_window_states()
        return []

    def get_adb_state_at(self, timestamp: float) -> dict:
        """Get complete ADB state at a timestamp.

        Args:
            timestamp: Relative timestamp (seconds since start)

        Returns:
            Dict with keyboard_visible, activity, and windows keys.
            Empty dict if ADB state monitor not running.
        """
        if not self._adb_state_monitor:
            return {}
        return {
            "keyboard_visible": self._adb_state_monitor.get_keyboard_state_at(timestamp),
            "activity": self._adb_state_monitor.get_activity_state_at(timestamp),
            "windows": self._adb_state_monitor.get_windows_state_at(timestamp),
        }
