"""Recording session management for mobile UI testing."""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutcli.core.scrcpy_service import ScrcpyService
from mutcli.core.touch_monitor import TouchMonitor

logger = logging.getLogger("mut.recorder")


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
    ):
        """Initialize recorder.

        Args:
            name: Test name
            device_id: ADB device identifier
            output_dir: Output directory (defaults to tests/{name}/)
        """
        self._name = name
        self._device_id = device_id
        self._output_dir = output_dir or Path(f"tests/{name}")
        self._recording = False
        self._start_time: float | None = None

        self._scrcpy: ScrcpyService | None = None
        self._touch_monitor: TouchMonitor | None = None

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

        # Create directory structure
        recording_dir = self._output_dir / "recording"
        recording_dir.mkdir(parents=True, exist_ok=True)

        video_path = str(recording_dir / "recording.mp4")

        try:
            # Connect ScrcpyService
            self._scrcpy = ScrcpyService(self._device_id)
            if not self._scrcpy.connect():
                self._scrcpy = None
                return {"success": False, "error": "Failed to connect ScrcpyService"}

            # Start video recording
            recording_result = self._scrcpy.start_recording(video_path)
            if not recording_result.get("success"):
                self._cleanup_scrcpy()
                return {
                    "success": False,
                    "error": f"Failed to start video recording: {recording_result.get('error')}",
                }

            # Start touch monitor
            self._touch_monitor = TouchMonitor(self._device_id)
            if not self._touch_monitor.start():
                self._cleanup_scrcpy()
                self._touch_monitor = None
                return {"success": False, "error": "Failed to start touch monitor"}

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
        recording_dir = self._output_dir / "recording"
        touch_events_path = recording_dir / "touch_events.json"

        try:
            events_data = [event.to_dict() for event in events]
            with open(touch_events_path, "w") as f:
                json.dump(events_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save touch events: {e}")
            # Continue cleanup even if save fails

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

        self._cleanup_scrcpy()
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
