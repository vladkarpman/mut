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

        # Connect ScrcpyService
        self._scrcpy = ScrcpyService(self._device_id)
        if not self._scrcpy.connect():
            return {"success": False, "error": "Failed to connect ScrcpyService"}

        # Start video recording
        video_path = str(recording_dir / "recording.mp4")
        recording_result = self._scrcpy.start_recording(video_path)
        if not recording_result.get("success"):
            self._scrcpy.disconnect()
            return {
                "success": False,
                "error": f"Failed to start video recording: {recording_result.get('error')}",
            }

        # Start touch monitor
        self._touch_monitor = TouchMonitor(self._device_id)
        if not self._touch_monitor.start():
            self._scrcpy.stop_recording()
            self._scrcpy.disconnect()
            return {"success": False, "error": "Failed to start touch monitor"}

        # Save state
        self._start_time = time.time()
        self._recording = True

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

    def stop(self) -> dict[str, Any]:
        """Stop recording and save artifacts.

        Stops touch monitoring, stops video recording, saves touch events
        to JSON, and cleans up state file.

        Returns:
            Dict with results including event count and duration
        """
        if not self._recording:
            return {"success": False, "error": "Not recording"}

        # Get touch events before stopping
        events = []
        if self._touch_monitor:
            events = self._touch_monitor.get_events()
            self._touch_monitor.stop()

        # Stop video recording
        stop_result = {}
        if self._scrcpy:
            stop_result = self._scrcpy.stop_recording()
            self._scrcpy.disconnect()

        # Save touch events
        recording_dir = self._output_dir / "recording"
        touch_events_path = recording_dir / "touch_events.json"

        events_data = [event.to_dict() for event in events]
        with open(touch_events_path, "w") as f:
            json.dump(events_data, f, indent=2)

        # Clean up state file
        if self.STATE_FILE.exists():
            self.STATE_FILE.unlink()

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
