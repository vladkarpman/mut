"""Touch event monitoring via adb getevent."""

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("mut.touch")


@dataclass
class TouchEvent:
    """A single touch event captured from the device.

    Attributes:
        timestamp: Seconds since monitoring started
        x: X coordinate in pixels
        y: Y coordinate in pixels
        event_type: Type of event ("tap", "swipe_start", "swipe_end")
    """

    timestamp: float
    x: int
    y: int
    event_type: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timestamp": self.timestamp,
            "x": self.x,
            "y": self.y,
            "event_type": self.event_type,
        }


class TouchMonitor:
    """Monitor touch events via adb getevent.

    Captures touch events from an Android device using `adb getevent -lt`.
    Runs in a background thread and stores events in a thread-safe list.

    Usage:
        monitor = TouchMonitor("device-id")
        monitor.start()
        # ... user interacts with device ...
        monitor.stop()
        events = monitor.get_events()
    """

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

    @property
    def is_running(self) -> bool:
        """Check if monitoring is active."""
        return self._running

    def start(self) -> bool:
        """Start monitoring touch events.

        Returns:
            True if started successfully, False on error.
        """
        if self._running:
            return True

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
            self._start_time = time.time()

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
        elif value_hex in ("00000000", "UP"):
            self._record_tap_event()
            self._touch_down = False
            self._current_x = None
            self._current_y = None

    def _record_tap_event(self) -> None:
        """Record a tap event when touch is released."""
        if self._current_x is None or self._current_y is None:
            return

        if self._start_time is None:
            return

        timestamp = time.time() - self._start_time

        event = TouchEvent(
            timestamp=timestamp,
            x=self._current_x,
            y=self._current_y,
            event_type="tap",
        )

        with self._lock:
            self._events.append(event)

        logger.debug(f"Tap recorded: ({event.x}, {event.y}) at {timestamp:.3f}s")
