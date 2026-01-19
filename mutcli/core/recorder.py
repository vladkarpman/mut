"""Recording session management for mobile UI testing."""

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutcli.core.scrcpy_service import ScrcpyService
from mutcli.core.touch_monitor import TouchMonitor
from mutcli.core.ui_hierarchy_monitor import UIHierarchyMonitor

logger = logging.getLogger("mut.recorder")


def _get_show_touches(device_id: str) -> bool:
    """Get current show_touches setting.

    Args:
        device_id: ADB device identifier

    Returns:
        True if show_touches is enabled, False otherwise
    """
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "settings", "get", "system", "show_touches"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "1"
    except Exception as e:
        logger.warning(f"Failed to get show_touches setting: {e}")
        return False


def _set_show_touches(device_id: str, enabled: bool) -> bool:
    """Set show_touches setting.

    Args:
        device_id: ADB device identifier
        enabled: True to enable, False to disable

    Returns:
        True if successful, False otherwise
    """
    try:
        value = "1" if enabled else "0"
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "settings", "put", "system", "show_touches", value],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.debug(f"Set show_touches to {enabled}")
            return True
        logger.warning(f"Failed to set show_touches: {result.stderr}")
        return False
    except Exception as e:
        logger.warning(f"Failed to set show_touches: {e}")
        return False


@dataclass
class RecordingState:
    """Persisted state for an active recording session.

    Attributes:
        name: Test name
        device_id: ADB device identifier
        output_dir: Path to output directory
        start_time: Recording start timestamp (Unix time)
    """

    name: str
    device_id: str
    output_dir: Path
    start_time: float

    def save(self, path: Path) -> None:
        """Save state to JSON file.

        Args:
            path: Path to save state file
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": self.name,
            "device_id": self.device_id,
            "output_dir": str(self.output_dir),
            "start_time": self.start_time,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "RecordingState":
        """Load state from JSON file.

        Args:
            path: Path to state file

        Returns:
            RecordingState instance

        Raises:
            FileNotFoundError: If state file doesn't exist
        """
        with open(path) as f:
            data = json.load(f)

        return cls(
            name=data["name"],
            device_id=data["device_id"],
            output_dir=Path(data["output_dir"]),
            start_time=data["start_time"],
        )


class Recorder:
    """Coordinates video recording and touch event capture.

    Manages a recording session by coordinating ScrcpyService for video
    recording and TouchMonitor for touch event capture.

    Usage:
        recorder = Recorder("my-test", "emulator-5554")
        recorder.start()
        # ... user interacts with device ...
        result = recorder.stop()
    """

    STATE_FILE = Path(".claude/recording-state.json")

    def __init__(
        self,
        name: str,
        device_id: str,
        output_dir: Path | None = None,
        app_package: str | None = None,
    ):
        """Initialize recorder.

        Args:
            name: Test name
            device_id: ADB device identifier
            output_dir: Output directory (defaults to tests/{name}/)
            app_package: App package name for UI hierarchy filtering.
                        Required for accurate element identification.
        """
        self._name = name
        self._device_id = device_id
        self._output_dir = output_dir or Path(f"tests/{name}")
        self._app_package = app_package
        self._recording = False
        self._start_time: float | None = None

        self._scrcpy: ScrcpyService | None = None
        self._touch_monitor: TouchMonitor | None = None
        self._ui_monitor: UIHierarchyMonitor | None = None

        # Track original show_touches state to restore after recording
        self._original_show_touches: bool | None = None

    @property
    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._recording

    @property
    def output_dir(self) -> Path:
        """Get output directory path."""
        return self._output_dir

    def start(self) -> dict[str, Any]:
        """Start recording session.

        Creates output directories, connects ScrcpyService, starts video
        recording, starts touch monitoring, and saves state file.

        Returns:
            Dict with success status and error message if failed
        """
        if self._recording:
            return {"success": False, "error": "Already recording"}

        # Create output directory
        self._output_dir.mkdir(parents=True, exist_ok=True)

        video_path = str(self._output_dir / "video.mp4")

        try:
            # Enable show_touches to display touch indicators in video
            self._original_show_touches = _get_show_touches(self._device_id)
            if not self._original_show_touches:
                _set_show_touches(self._device_id, True)
                logger.info("Enabled show_touches for recording")

            # Connect ScrcpyService
            self._scrcpy = ScrcpyService(self._device_id)
            if not self._scrcpy.connect():
                self._scrcpy = None
                # Restore show_touches on failure
                if self._original_show_touches is not None and not self._original_show_touches:
                    _set_show_touches(self._device_id, False)
                return {"success": False, "error": "Failed to connect ScrcpyService"}

            # Start video recording
            recording_result = self._scrcpy.start_recording(video_path)
            if not recording_result.get("success"):
                self._cleanup_scrcpy()
                return {
                    "success": False,
                    "error": f"Failed to start video recording: {recording_result.get('error')}",
                }

            # Get video start time for synchronization
            video_start_time = recording_result.get("recording_start_time")

            # Start touch monitor with video start time as reference
            # This ensures touch timestamps match video timestamps
            self._touch_monitor = TouchMonitor(self._device_id)
            if not self._touch_monitor.start(reference_time=video_start_time):
                self._cleanup_scrcpy()
                self._touch_monitor = None
                return {"success": False, "error": "Failed to start touch monitor"}

            # Start UI hierarchy monitoring (mobile-mcp style fast dump)
            # Captures element data in background for accurate element identification
            if self._app_package:
                self._ui_monitor = UIHierarchyMonitor(self._device_id, self._app_package)
                self._ui_monitor.start(reference_time=video_start_time)
                logger.info("UI hierarchy monitoring started")

            # Set recording state BEFORE saving state file (Issue 5)
            self._start_time = time.time()
            self._recording = True

            # Save state file
            state = RecordingState(
                name=self._name,
                device_id=self._device_id,
                output_dir=self._output_dir,
                start_time=self._start_time,
            )
            state.save(self.STATE_FILE)

            logger.info(f"Recording started: {self._name}")

            return {
                "success": True,
                "name": self._name,
                "output_dir": str(self._output_dir),
                "video_path": video_path,
            }

        except Exception as e:
            # Rollback on any unexpected exception (Issue 3)
            logger.error(f"Failed to start recording: {e}")
            self._cleanup_on_start_failure()
            return {"success": False, "error": f"Failed to start recording: {e}"}

    def stop(self) -> dict[str, Any]:
        """Stop recording and save artifacts.

        Stops touch monitoring, stops video recording, saves touch events
        to JSON, and cleans up state file.

        Returns:
            Dict with results including event count and duration
        """
        if not self._recording:
            return {"success": False, "error": "Not recording"}

        # Stop touch monitor BEFORE getting events to prevent race condition (Issue 1)
        events = []
        if self._touch_monitor:
            try:
                self._touch_monitor.stop()
                events = self._touch_monitor.get_events()
            except Exception as e:
                logger.warning(f"Error stopping touch monitor: {e}")

        # Stop video recording with proper cleanup (Issue 2)
        stop_result = {}
        if self._scrcpy:
            try:
                stop_result = self._scrcpy.stop_recording()
            except Exception as e:
                logger.warning(f"Error stopping video recording: {e}")
            try:
                self._scrcpy.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting scrcpy: {e}")

        # Save touch events with exception handling (Issue 4)
        touch_events_path = self._output_dir / "touch_events.json"

        try:
            events_data = [event.to_dict() for event in events]
            with open(touch_events_path, "w") as f:
                json.dump(events_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save touch events: {e}")
            # Continue cleanup even if save fails

        # Save screen dimensions
        screen_size_path = self._output_dir / "screen_size.json"
        try:
            if self._touch_monitor:
                screen_width, screen_height = self._touch_monitor.get_screen_size()
                with open(screen_size_path, "w") as f:
                    json.dump({"width": screen_width, "height": screen_height}, f, indent=2)
                logger.info(f"Saved screen size: {screen_width}x{screen_height}")
        except Exception as e:
            logger.error(f"Failed to save screen size: {e}")

        # Save ADB state data
        if self._touch_monitor:
            try:
                keyboard_states = self._touch_monitor.get_keyboard_states()
                keyboard_path = self._output_dir / "keyboard_states.json"
                with open(keyboard_path, "w") as f:
                    json.dump(keyboard_states, f, indent=2)

                activity_states = self._touch_monitor.get_activity_states()
                activity_path = self._output_dir / "activity_states.json"
                with open(activity_path, "w") as f:
                    json.dump(activity_states, f, indent=2)

                window_states = self._touch_monitor.get_window_states()
                window_path = self._output_dir / "window_states.json"
                with open(window_path, "w") as f:
                    json.dump(window_states, f, indent=2)

                logger.info(
                    f"Saved ADB state: {len(keyboard_states)} keyboard, "
                    f"{len(activity_states)} activity, {len(window_states)} window states"
                )
            except Exception as e:
                logger.warning(f"Error saving ADB state data: {e}")

        # Stop UI hierarchy monitoring and save dumps
        if self._ui_monitor:
            try:
                self._ui_monitor.stop()
                ui_dumps = self._ui_monitor.get_dumps()
                if ui_dumps:
                    ui_dumps_path = self._output_dir / "ui_hierarchy.json"
                    with open(ui_dumps_path, "w") as f:
                        json.dump(ui_dumps, f, indent=2)
                    logger.info(f"Saved {len(ui_dumps)} UI hierarchy dumps")
            except Exception as e:
                logger.warning(f"Error saving UI hierarchy: {e}")

        # Restore original show_touches setting
        if self._original_show_touches is not None and not self._original_show_touches:
            _set_show_touches(self._device_id, False)
            logger.info("Restored show_touches to original state (disabled)")

        # Clean up state file with exception handling (Issue 4)
        try:
            if self.STATE_FILE.exists():
                self.STATE_FILE.unlink()
        except Exception as e:
            logger.warning(f"Error cleaning up state file: {e}")

        self._recording = False

        logger.info(f"Recording stopped: {self._name} ({len(events)} events)")

        return {
            "success": True,
            "name": self._name,
            "output_dir": str(self._output_dir),
            "event_count": len(events),
            "duration_seconds": stop_result.get("duration_seconds"),
            "video_path": stop_result.get("output_path"),
            "touch_events_path": str(touch_events_path),
        }

    def _cleanup_scrcpy(self) -> None:
        """Clean up ScrcpyService resources safely."""
        if self._scrcpy:
            try:
                self._scrcpy.stop_recording()
            except Exception as e:
                logger.warning(f"Error stopping recording during cleanup: {e}")
            try:
                self._scrcpy.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting scrcpy during cleanup: {e}")
            self._scrcpy = None

    def _cleanup_on_start_failure(self) -> None:
        """Clean up all resources after a failed start attempt."""
        if self._touch_monitor:
            try:
                self._touch_monitor.stop()
            except Exception as e:
                logger.warning(f"Error stopping touch monitor during cleanup: {e}")
            self._touch_monitor = None

        if self._ui_monitor:
            try:
                self._ui_monitor.stop()
            except Exception as e:
                logger.warning(f"Error stopping UI monitor during cleanup: {e}")
            self._ui_monitor = None

        self._cleanup_scrcpy()

        # Restore show_touches if it was changed
        if self._original_show_touches is not None and not self._original_show_touches:
            _set_show_touches(self._device_id, False)

        self._recording = False

    @classmethod
    def load_active(cls) -> "Recorder | None":
        """Load active recording from state file.

        Returns:
            Recorder instance if active recording exists, None otherwise
        """
        if not cls.STATE_FILE.exists():
            return None

        state = RecordingState.load(cls.STATE_FILE)

        recorder = cls(
            name=state.name,
            device_id=state.device_id,
            output_dir=state.output_dir,
        )
        recorder._start_time = state.start_time
        recorder._recording = True

        return recorder
