"""ADB state monitor for background device state capture."""

import logging
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

# Polling intervals in seconds
KEYBOARD_POLL_INTERVAL = 0.3  # 300ms for keyboard state
FAST_POLL_INTERVAL = 0.15  # 150ms for activity/windows


class ADBStateMonitor:
    """Monitor device state via ADB during recording.

    Captures keyboard visibility, current activity, and visible windows
    at regular intervals for enriching AI analysis prompts.
    """

    def __init__(self, device_id: str):
        """Initialize monitor for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._running = False
        self._stop_event = threading.Event()
        self._start_time: float | None = None

        # State storage: list of (timestamp, value) tuples
        self._keyboard_states: list[tuple[float, bool]] = []
        self._activity_states: list[tuple[float, str | None]] = []
        self._window_states: list[tuple[float, list[str]]] = []

        # Lock for thread-safe access to state lists
        self._lock = threading.Lock()

        # Daemon threads for polling
        self._keyboard_thread: threading.Thread | None = None
        self._activity_thread: threading.Thread | None = None
        self._windows_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        """Check if monitor is currently running."""
        return self._running

    def start(self) -> None:
        """Start background monitoring threads."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._start_time = time.monotonic()

        # Clear previous states
        self._keyboard_states = []
        self._activity_states = []
        self._window_states = []

        # Start daemon threads
        self._keyboard_thread = threading.Thread(
            target=self._keyboard_polling_loop, daemon=True
        )
        self._activity_thread = threading.Thread(
            target=self._activity_polling_loop, daemon=True
        )
        self._windows_thread = threading.Thread(
            target=self._windows_polling_loop, daemon=True
        )

        self._keyboard_thread.start()
        self._activity_thread.start()
        self._windows_thread.start()

        logger.debug("ADB state monitor started for device %s", self._device_id)

    def stop(self) -> None:
        """Stop background monitoring threads."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        # Wait for threads to finish
        if self._keyboard_thread and self._keyboard_thread.is_alive():
            self._keyboard_thread.join(timeout=1.0)
        if self._activity_thread and self._activity_thread.is_alive():
            self._activity_thread.join(timeout=1.0)
        if self._windows_thread and self._windows_thread.is_alive():
            self._windows_thread.join(timeout=1.0)

        logger.debug("ADB state monitor stopped for device %s", self._device_id)

    def _get_relative_timestamp(self) -> float:
        """Get timestamp relative to monitor start."""
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    def _keyboard_polling_loop(self) -> None:
        """Background loop for keyboard state polling."""
        while not self._stop_event.is_set():
            try:
                visible = self._poll_keyboard()
                timestamp = self._get_relative_timestamp()
                with self._lock:
                    self._keyboard_states.append((timestamp, visible))
            except Exception as e:
                logger.debug("Keyboard poll failed: %s", e)
            self._stop_event.wait(KEYBOARD_POLL_INTERVAL)

    def _activity_polling_loop(self) -> None:
        """Background loop for activity polling."""
        while not self._stop_event.is_set():
            try:
                activity = self._poll_activity()
                if activity:
                    timestamp = self._get_relative_timestamp()
                    with self._lock:
                        self._activity_states.append((timestamp, activity))
            except Exception as e:
                logger.debug("Activity poll failed: %s", e)
            self._stop_event.wait(FAST_POLL_INTERVAL)

    def _windows_polling_loop(self) -> None:
        """Background loop for windows polling."""
        while not self._stop_event.is_set():
            try:
                windows = self._poll_windows()
                timestamp = self._get_relative_timestamp()
                with self._lock:
                    self._window_states.append((timestamp, windows))
            except Exception as e:
                logger.debug("Windows poll failed: %s", e)
            self._stop_event.wait(FAST_POLL_INTERVAL)

    def _poll_keyboard(self) -> bool:
        """Poll keyboard visibility state.

        Returns:
            True if keyboard is visible, False otherwise
        """
        result = subprocess.run(
            ["adb", "-s", self._device_id, "shell", "dumpsys", "input_method"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        # Look for mInputShown=true/false in output
        return "mInputShown=true" in result.stdout

    def _poll_activity(self) -> str | None:
        """Poll current top activity.

        Returns:
            Activity name (e.g., "com.example.app/.MainActivity") or None
        """
        result = subprocess.run(
            ["adb", "-s", self._device_id, "shell", "dumpsys", "activity", "activities"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        # Parse topResumedActivity line
        # Format: topResumedActivity=ActivityRecord{abc u0 com.example.app/.MainActivity}
        match = re.search(
            r"topResumedActivity=ActivityRecord\{[^}]*\s+(\S+/\S+)\}",
            result.stdout,
        )
        if match:
            return match.group(1)
        return None

    def _poll_windows(self) -> list[str]:
        """Poll visible windows.

        Returns:
            List of visible window titles
        """
        result = subprocess.run(
            ["adb", "-s", self._device_id, "shell", "dumpsys", "window", "windows"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        windows = []
        # Parse window entries - look for Window{...} followed by isOnScreen=true
        lines = result.stdout.split("\n")
        current_window = None
        for line in lines:
            # Match window definition: Window #N Window{abc u0 Title}
            window_match = re.search(r"Window\s+#\d+\s+Window\{[^}]*\s+(\S+)\}", line)
            if window_match:
                current_window = window_match.group(1)
            # Check if window is on screen
            if current_window and "isOnScreen=true" in line:
                windows.append(current_window)
                current_window = None
        return windows

    def get_keyboard_state_at(self, timestamp: float) -> bool:
        """Get keyboard visibility state at a specific timestamp.

        Finds the most recent state recorded before or at the given timestamp.

        Args:
            timestamp: Relative timestamp (seconds since start)

        Returns:
            True if keyboard was visible, False otherwise
        """
        with self._lock:
            if not self._keyboard_states:
                return False

            # Find the most recent state at or before the timestamp
            result = False
            for ts, visible in self._keyboard_states:
                if ts <= timestamp:
                    result = visible
                else:
                    break
            return result

    def get_activity_state_at(self, timestamp: float) -> str | None:
        """Get current activity at a specific timestamp.

        Args:
            timestamp: Relative timestamp (seconds since start)

        Returns:
            Activity name or None
        """
        with self._lock:
            if not self._activity_states:
                return None

            result = None
            for ts, activity in self._activity_states:
                if ts <= timestamp:
                    result = activity
                else:
                    break
            return result

    def get_windows_state_at(self, timestamp: float) -> list[str]:
        """Get visible windows at a specific timestamp.

        Args:
            timestamp: Relative timestamp (seconds since start)

        Returns:
            List of window titles
        """
        with self._lock:
            if not self._window_states:
                return []

            result: list[str] = []
            for ts, windows in self._window_states:
                if ts <= timestamp:
                    result = windows
                else:
                    break
            return result

    def get_keyboard_states(self) -> list[tuple[float, bool]]:
        """Get all recorded keyboard states.

        Returns:
            Copy of all (timestamp, is_visible) tuples.
        """
        with self._lock:
            return list(self._keyboard_states)

    def get_activity_states(self) -> list[tuple[float, str | None]]:
        """Get all recorded activity states.

        Returns:
            Copy of all (timestamp, activity_name) tuples.
        """
        with self._lock:
            return list(self._activity_states)

    def get_window_states(self) -> list[tuple[float, list[str]]]:
        """Get all recorded window states.

        Returns:
            Copy of all (timestamp, window_list) tuples.
        """
        with self._lock:
            return list(self._window_states)
