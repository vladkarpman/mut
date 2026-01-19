"""Interactive recording via injection-based touch capture.

Provides a GUI window for recording touch interactions with perfect
coordinate accuracy by injecting touches via scrcpy control.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutcli.core.recording_window import RecordingWindow
from mutcli.core.scrcpy_service import ScrcpyService
from mutcli.core.touch_injector import TouchInjector

logger = logging.getLogger("mut.interactive_recorder")


@dataclass
class RecordingState:
    """Persisted state for an active recording session."""

    name: str
    device_id: str
    output_dir: Path
    start_time: float

    def save(self, path: Path) -> None:
        """Save state to JSON file."""
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
        """Load state from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            name=data["name"],
            device_id=data["device_id"],
            output_dir=Path(data["output_dir"]),
            start_time=data["start_time"],
        )


class InteractiveRecorder:
    """Interactive recorder using injection-based touch capture.

    Opens a GUI window showing the device screen. User clicks/drags
    on the window, touches are injected to the device and logged
    with perfect coordinate accuracy.

    Usage:
        recorder = InteractiveRecorder("my-test", "emulator-5554")
        result = recorder.record()  # Blocks until window closed
        # result contains event_count, video_path, etc.
    """

    STATE_FILE = Path(".claude/recording-state.json")

    def __init__(
        self,
        name: str,
        device_id: str,
        output_dir: Path | None = None,
        window_scale: float = 0.5,
    ):
        """Initialize interactive recorder.

        Args:
            name: Test name
            device_id: ADB device identifier
            output_dir: Output directory (defaults to tests/{name}/)
            window_scale: Scale factor for recording window (0.5 = half size)
        """
        self._name = name
        self._device_id = device_id
        self._output_dir = output_dir or Path(f"tests/{name}")
        self._window_scale = window_scale

        self._scrcpy: ScrcpyService | None = None
        self._injector: TouchInjector | None = None
        self._window: RecordingWindow | None = None
        self._start_time: float | None = None

    @property
    def output_dir(self) -> Path:
        """Get output directory path."""
        return self._output_dir

    def record(self) -> dict[str, Any]:
        """Start interactive recording session.

        Opens recording window and blocks until user closes it.
        Touch events are captured via injection with perfect accuracy.

        Returns:
            Dict with recording results
        """
        # Create output directory
        self._output_dir.mkdir(parents=True, exist_ok=True)
        video_path = str(self._output_dir / "video.mp4")

        try:
            # Connect ScrcpyService with control enabled
            logger.info(f"Connecting to {self._device_id} with control...")
            self._scrcpy = ScrcpyService(self._device_id, enable_control=True)

            if not self._scrcpy.connect():
                return {"success": False, "error": "Failed to connect to device"}

            # Wait for control to be ready
            retries = 10
            while not self._scrcpy.is_control_ready and retries > 0:
                time.sleep(0.2)
                retries -= 1

            if not self._scrcpy.is_control_ready:
                self._cleanup()
                return {"success": False, "error": "Control not ready"}

            logger.info("Control ready, starting recording...")

            # Start video recording
            recording_result = self._scrcpy.start_recording(video_path)
            if not recording_result.get("success"):
                self._cleanup()
                return {
                    "success": False,
                    "error": f"Failed to start video: {recording_result.get('error')}",
                }

            # Get recording start time
            self._start_time = recording_result.get("recording_start_time", time.time())

            # Create touch injector
            self._injector = TouchInjector(self._scrcpy, self._start_time)

            # Save state file
            state = RecordingState(
                name=self._name,
                device_id=self._device_id,
                output_dir=self._output_dir,
                start_time=self._start_time,
            )
            state.save(self.STATE_FILE)

            # Create and run recording window (blocks until closed)
            self._window = RecordingWindow(
                scrcpy=self._scrcpy,
                injector=self._injector,
                title=f"MUT Recording - {self._name}",
                scale=self._window_scale,
            )

            logger.info("Recording window opened, waiting for user interaction...")
            self._window.run()  # Blocks until window closed

            # Get events from injector
            events = self._injector.get_events()
            logger.info(f"Recording complete: {len(events)} events captured")

            # Stop video recording
            stop_result = self._scrcpy.stop_recording()

            # Save touch events
            touch_events_path = self._output_dir / "touch_events.json"
            events_data = [event.to_dict() for event in events]
            with open(touch_events_path, "w") as f:
                json.dump(events_data, f, indent=2)

            # Save screen dimensions
            screen_size_path = self._output_dir / "screen_size.json"
            screen_width, screen_height = self._scrcpy.get_screen_size()
            with open(screen_size_path, "w") as f:
                json.dump({"width": screen_width, "height": screen_height}, f, indent=2)

            # Cleanup
            self._cleanup()

            # Remove state file
            if self.STATE_FILE.exists():
                self.STATE_FILE.unlink()

            return {
                "success": True,
                "name": self._name,
                "output_dir": str(self._output_dir),
                "event_count": len(events),
                "duration_seconds": stop_result.get("duration_seconds"),
                "video_path": stop_result.get("output_path"),
                "touch_events_path": str(touch_events_path),
            }

        except Exception as e:
            logger.exception(f"Recording failed: {e}")
            self._cleanup()
            return {"success": False, "error": str(e)}

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._window:
            try:
                self._window.close()
            except Exception:
                pass
            self._window = None

        if self._scrcpy:
            try:
                self._scrcpy.stop_recording()
            except Exception:
                pass
            try:
                self._scrcpy.disconnect()
            except Exception:
                pass
            self._scrcpy = None

        self._injector = None

        # Remove state file on cleanup
        try:
            if self.STATE_FILE.exists():
                self.STATE_FILE.unlink()
        except Exception:
            pass
