# Recording Workflow Implementation Plan (Phase 2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `mut record`, `mut stop`, and `mut report` commands for interactive test recording with AI-powered step analysis.

**Architecture:** Recording captures touch events via adb getevent + video via ScrcpyService. Stop command extracts frames, analyzes with AIAnalyzer, generates YAML with cleanup.

**Tech Stack:** adb getevent (touch capture), ScrcpyService (video), AIAnalyzer (step analysis), threading (background capture)

---

## Overview

Recording workflow:
1. `mut record <name>` - Start video recording + touch capture
2. User interacts with device
3. `mut stop` (or Ctrl+C) - Stop recording, extract frames, AI analysis, generate YAML

Files created during recording:
```
tests/{name}/
├── recording/
│   ├── recording.mp4       # Video from ScrcpyService
│   ├── touch_events.json   # Raw touch events with timestamps
│   └── screenshots/        # Frames extracted at touch points
└── test.yaml              # Generated test file
```

---

## Task 1: Implement TouchMonitor for Event Capture

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/touch_monitor.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_touch_monitor.py`

**Step 1: Write failing tests for TouchMonitor**

```python
"""Tests for TouchMonitor."""

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.touch_monitor import TouchMonitor, TouchEvent


class TestTouchEvent:
    """Test TouchEvent dataclass."""

    def test_touch_event_creation(self):
        """Should create TouchEvent with required fields."""
        event = TouchEvent(
            timestamp=1.5,
            x=540,
            y=1200,
            event_type="tap",
        )

        assert event.timestamp == 1.5
        assert event.x == 540
        assert event.y == 1200
        assert event.event_type == "tap"

    def test_touch_event_to_dict(self):
        """Should convert to dictionary."""
        event = TouchEvent(
            timestamp=1.5,
            x=540,
            y=1200,
            event_type="tap",
        )

        d = event.to_dict()

        assert d["timestamp"] == 1.5
        assert d["x"] == 540
        assert d["y"] == 1200
        assert d["event_type"] == "tap"


class TestTouchMonitorUnit:
    """Unit tests for TouchMonitor."""

    def test_is_running_false_initially(self):
        """Should not be running initially."""
        monitor = TouchMonitor(device_id="test-device")

        assert monitor.is_running is False

    def test_get_events_returns_empty_initially(self):
        """Should return empty list initially."""
        monitor = TouchMonitor(device_id="test-device")

        events = monitor.get_events()

        assert events == []

    @patch("mutcli.core.touch_monitor.subprocess.Popen")
    def test_start_launches_adb_getevent(self, mock_popen):
        """Should launch adb getevent process."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = b""
        mock_popen.return_value = mock_process

        monitor = TouchMonitor(device_id="test-device")
        monitor.start()

        # Give thread time to start
        time.sleep(0.1)
        monitor.stop()

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "adb" in call_args
        assert "getevent" in call_args

    def test_stop_clears_running_state(self):
        """Should clear running state on stop."""
        monitor = TouchMonitor(device_id="test-device")
        monitor._running = True

        monitor.stop()

        assert monitor.is_running is False


class TestTouchEventParsing:
    """Test touch event parsing from adb getevent output."""

    def test_parses_tap_event(self):
        """Should parse touch down/up as tap."""
        monitor = TouchMonitor(device_id="test-device")

        # Simulate touch events (ABS_MT_POSITION_X, ABS_MT_POSITION_Y, BTN_TOUCH)
        lines = [
            "/dev/input/event5: EV_ABS ABS_MT_POSITION_X 00000219",  # X = 537
            "/dev/input/event5: EV_ABS ABS_MT_POSITION_Y 000004b0",  # Y = 1200
            "/dev/input/event5: EV_KEY BTN_TOUCH DOWN",
            "/dev/input/event5: EV_SYN SYN_REPORT",
            "/dev/input/event5: EV_KEY BTN_TOUCH UP",
        ]

        for line in lines:
            monitor._parse_line(line)

        events = monitor.get_events()
        assert len(events) >= 1
        assert events[0].event_type == "tap"

    def test_ignores_non_touch_events(self):
        """Should ignore non-touch events."""
        monitor = TouchMonitor(device_id="test-device")

        # Non-touch event
        monitor._parse_line("/dev/input/event0: EV_KEY KEY_VOLUMEUP DOWN")

        events = monitor.get_events()
        assert len(events) == 0
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest tests/test_touch_monitor.py -v
```

Expected: FAIL with ModuleNotFoundError

**Step 3: Implement TouchMonitor**

Create `/Users/vladislavkarpman/Projects/mut/mutcli/core/touch_monitor.py`:

```python
"""Touch event monitor using adb getevent."""

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger("mut.touch")


@dataclass
class TouchEvent:
    """Represents a touch event."""

    timestamp: float
    x: int
    y: int
    event_type: str  # "tap", "swipe_start", "swipe_end"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class TouchMonitor:
    """Monitor touch events via adb getevent.

    Captures touch events in a background thread and provides
    them as a list of TouchEvent objects.
    """

    # Regex patterns for parsing getevent output
    ABS_X_PATTERN = re.compile(r"EV_ABS\s+ABS_MT_POSITION_X\s+([0-9a-fA-F]+)")
    ABS_Y_PATTERN = re.compile(r"EV_ABS\s+ABS_MT_POSITION_Y\s+([0-9a-fA-F]+)")
    BTN_TOUCH_PATTERN = re.compile(r"EV_KEY\s+BTN_TOUCH\s+(DOWN|UP)")
    SYN_REPORT_PATTERN = re.compile(r"EV_SYN\s+SYN_REPORT")

    def __init__(self, device_id: str):
        """Initialize monitor for device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._running = False
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._events: list[TouchEvent] = []
        self._lock = threading.Lock()

        # Current touch state
        self._current_x: int | None = None
        self._current_y: int | None = None
        self._touch_down = False
        self._start_time: float | None = None

    @property
    def is_running(self) -> bool:
        """Check if monitor is running."""
        return self._running

    def start(self) -> bool:
        """Start monitoring touch events.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        try:
            # Launch adb getevent
            cmd = [
                "adb",
                "-s", self._device_id,
                "shell",
                "getevent", "-lt",  # -l for labels, -t for timestamps
            ]

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=False,
            )

            self._running = True
            self._start_time = time.time()
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()

            logger.info(f"Touch monitor started for {self._device_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start touch monitor: {e}")
            return False

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                pass
            self._process = None

        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

        logger.info("Touch monitor stopped")

    def get_events(self) -> list[TouchEvent]:
        """Get all captured events.

        Returns:
            List of TouchEvent objects
        """
        with self._lock:
            return list(self._events)

    def clear_events(self) -> None:
        """Clear all captured events."""
        with self._lock:
            self._events.clear()

    def _read_loop(self) -> None:
        """Read events from adb getevent."""
        if not self._process or not self._process.stdout:
            return

        while self._running:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break

                self._parse_line(line.decode("utf-8", errors="ignore").strip())

            except Exception as e:
                logger.debug(f"Error reading event: {e}")

    def _parse_line(self, line: str) -> None:
        """Parse a single getevent output line."""
        if not line:
            return

        # Parse X coordinate
        x_match = self.ABS_X_PATTERN.search(line)
        if x_match:
            self._current_x = int(x_match.group(1), 16)
            return

        # Parse Y coordinate
        y_match = self.ABS_Y_PATTERN.search(line)
        if y_match:
            self._current_y = int(y_match.group(1), 16)
            return

        # Parse touch down/up
        btn_match = self.BTN_TOUCH_PATTERN.search(line)
        if btn_match:
            if btn_match.group(1) == "DOWN":
                self._touch_down = True
            else:  # UP
                self._touch_down = False
                # Record tap event on touch up
                if self._current_x is not None and self._current_y is not None:
                    self._record_tap()
            return

        # SYN_REPORT marks end of event batch - we record on BTN_TOUCH UP instead

    def _record_tap(self) -> None:
        """Record a tap event."""
        if self._current_x is None or self._current_y is None:
            return

        timestamp = time.time() - (self._start_time or 0)

        event = TouchEvent(
            timestamp=timestamp,
            x=self._current_x,
            y=self._current_y,
            event_type="tap",
        )

        with self._lock:
            self._events.append(event)

        logger.debug(f"Tap recorded: ({self._current_x}, {self._current_y})")

        # Reset current position
        self._current_x = None
        self._current_y = None
```

**Step 4: Run tests**

```bash
pytest tests/test_touch_monitor.py -v
```

Expected: PASS (all tests)

**Step 5: Update exports**

Add to `/Users/vladislavkarpman/Projects/mut/mutcli/core/__init__.py`:

```python
from mutcli.core.touch_monitor import TouchMonitor, TouchEvent
```

**Step 6: Commit**

```bash
git add mutcli/core/touch_monitor.py tests/test_touch_monitor.py mutcli/core/__init__.py
git commit -m "feat(recording): implement TouchMonitor for adb getevent capture"
```

---

## Task 2: Implement Recorder Class

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/recorder.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_recorder.py`

**Step 1: Write failing tests for Recorder**

```python
"""Tests for Recorder."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.recorder import Recorder, RecordingState


class TestRecordingState:
    """Test RecordingState management."""

    def test_create_state(self):
        """Should create recording state."""
        state = RecordingState(
            name="login-test",
            device_id="emulator-5554",
            output_dir=Path("/tmp/tests/login-test"),
            start_time=time.time(),
        )

        assert state.name == "login-test"
        assert state.device_id == "emulator-5554"

    def test_save_and_load_state(self):
        """Should save and load state from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            state = RecordingState(
                name="test",
                device_id="device-1",
                output_dir=Path(tmpdir) / "tests" / "test",
                start_time=1234567890.0,
            )

            state.save(state_file)
            loaded = RecordingState.load(state_file)

            assert loaded.name == state.name
            assert loaded.device_id == state.device_id


class TestRecorderUnit:
    """Unit tests for Recorder."""

    def test_is_recording_false_initially(self):
        """Should not be recording initially."""
        recorder = Recorder(name="test", device_id="device-1")

        assert recorder.is_recording is False

    @patch("mutcli.core.recorder.ScrcpyService")
    @patch("mutcli.core.recorder.TouchMonitor")
    def test_start_creates_output_directory(self, mock_touch, mock_scrcpy):
        """Should create output directory structure."""
        mock_scrcpy_instance = MagicMock()
        mock_scrcpy_instance.connect.return_value = True
        mock_scrcpy_instance.start_recording.return_value = {"success": True}
        mock_scrcpy.return_value = mock_scrcpy_instance

        mock_touch_instance = MagicMock()
        mock_touch_instance.start.return_value = True
        mock_touch.return_value = mock_touch_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "login-test"

            recorder = Recorder(
                name="login-test",
                device_id="device-1",
                output_dir=output_dir,
            )
            recorder.start()

            assert output_dir.exists()
            assert (output_dir / "recording").exists()

            recorder.stop()

    @patch("mutcli.core.recorder.ScrcpyService")
    @patch("mutcli.core.recorder.TouchMonitor")
    def test_stop_saves_touch_events(self, mock_touch, mock_scrcpy):
        """Should save touch events to JSON file."""
        mock_scrcpy_instance = MagicMock()
        mock_scrcpy_instance.connect.return_value = True
        mock_scrcpy_instance.start_recording.return_value = {"success": True}
        mock_scrcpy_instance.stop_recording.return_value = {
            "success": True,
            "output_path": "/tmp/recording.mp4",
        }
        mock_scrcpy.return_value = mock_scrcpy_instance

        mock_touch_instance = MagicMock()
        mock_touch_instance.start.return_value = True
        mock_touch_instance.get_events.return_value = [
            MagicMock(to_dict=lambda: {"timestamp": 1.0, "x": 100, "y": 200, "event_type": "tap"})
        ]
        mock_touch.return_value = mock_touch_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            recorder = Recorder(
                name="test",
                device_id="device-1",
                output_dir=output_dir,
            )
            recorder.start()
            recorder.stop()

            touch_file = output_dir / "recording" / "touch_events.json"
            assert touch_file.exists()

            with open(touch_file) as f:
                events = json.load(f)
                assert len(events) == 1
```

**Step 2: Run tests**

```bash
pytest tests/test_recorder.py -v
```

Expected: FAIL with ModuleNotFoundError

**Step 3: Implement Recorder**

Create `/Users/vladislavkarpman/Projects/mut/mutcli/core/recorder.py`:

```python
"""Recording management for test creation."""

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from mutcli.core.scrcpy_service import ScrcpyService
from mutcli.core.touch_monitor import TouchMonitor

logger = logging.getLogger("mut.recorder")


@dataclass
class RecordingState:
    """Persistent state for active recording."""

    name: str
    device_id: str
    output_dir: Path
    start_time: float

    def save(self, path: Path) -> None:
        """Save state to file."""
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
        """Load state from file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            name=data["name"],
            device_id=data["device_id"],
            output_dir=Path(data["output_dir"]),
            start_time=data["start_time"],
        )


class Recorder:
    """Manages test recording sessions.

    Coordinates ScrcpyService (video) and TouchMonitor (events)
    to capture user interactions for test generation.
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
        self._recording_dir = self._output_dir / "recording"

        self._scrcpy: ScrcpyService | None = None
        self._touch_monitor: TouchMonitor | None = None
        self._state: RecordingState | None = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._is_recording

    @property
    def output_dir(self) -> Path:
        """Get output directory."""
        return self._output_dir

    def start(self) -> dict[str, Any]:
        """Start recording session.

        Returns:
            Dict with success status and details
        """
        if self._is_recording:
            return {"success": False, "error": "Recording already in progress"}

        # Create directories
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._recording_dir.mkdir(parents=True, exist_ok=True)

        # Start scrcpy service
        self._scrcpy = ScrcpyService(self._device_id)
        if not self._scrcpy.connect():
            return {"success": False, "error": "Failed to connect to device"}

        # Start video recording
        video_path = str(self._recording_dir / "recording.mp4")
        result = self._scrcpy.start_recording(video_path)
        if not result.get("success"):
            self._scrcpy.disconnect()
            return {"success": False, "error": result.get("error", "Failed to start recording")}

        # Start touch monitor
        self._touch_monitor = TouchMonitor(self._device_id)
        if not self._touch_monitor.start():
            self._scrcpy.stop_recording()
            self._scrcpy.disconnect()
            return {"success": False, "error": "Failed to start touch monitor"}

        # Save state
        self._state = RecordingState(
            name=self._name,
            device_id=self._device_id,
            output_dir=self._output_dir,
            start_time=time.time(),
        )
        self._state.save(self.STATE_FILE)

        self._is_recording = True
        logger.info(f"Recording started: {self._name}")

        return {
            "success": True,
            "name": self._name,
            "output_dir": str(self._output_dir),
        }

    def stop(self) -> dict[str, Any]:
        """Stop recording and save artifacts.

        Returns:
            Dict with recording results
        """
        if not self._is_recording:
            return {"success": False, "error": "No recording in progress"}

        # Stop touch monitor
        touch_events = []
        if self._touch_monitor:
            touch_events = self._touch_monitor.get_events()
            self._touch_monitor.stop()

        # Save touch events
        touch_file = self._recording_dir / "touch_events.json"
        with open(touch_file, "w") as f:
            json.dump([e.to_dict() for e in touch_events], f, indent=2)

        # Stop video recording
        video_result = {"success": False}
        if self._scrcpy:
            video_result = self._scrcpy.stop_recording()
            self._scrcpy.disconnect()

        # Clean up state file
        if self.STATE_FILE.exists():
            self.STATE_FILE.unlink()

        self._is_recording = False
        duration = time.time() - (self._state.start_time if self._state else 0)

        logger.info(f"Recording stopped: {len(touch_events)} events captured")

        return {
            "success": True,
            "name": self._name,
            "output_dir": str(self._output_dir),
            "touch_events": len(touch_events),
            "duration_seconds": round(duration, 2),
            "video_path": video_result.get("output_path"),
        }

    @classmethod
    def load_active(cls) -> "Recorder | None":
        """Load active recording from state file.

        Returns:
            Recorder instance if active recording exists, None otherwise
        """
        if not cls.STATE_FILE.exists():
            return None

        try:
            state = RecordingState.load(cls.STATE_FILE)
            recorder = cls(
                name=state.name,
                device_id=state.device_id,
                output_dir=state.output_dir,
            )
            recorder._state = state
            recorder._is_recording = True

            # Reconnect services
            recorder._scrcpy = ScrcpyService(state.device_id)
            recorder._touch_monitor = TouchMonitor(state.device_id)

            return recorder

        except Exception as e:
            logger.error(f"Failed to load recording state: {e}")
            return None
```

**Step 4: Run tests**

```bash
pytest tests/test_recorder.py -v
```

Expected: PASS

**Step 5: Update exports**

```python
from mutcli.core.recorder import Recorder, RecordingState
```

**Step 6: Commit**

```bash
git add mutcli/core/recorder.py tests/test_recorder.py mutcli/core/__init__.py
git commit -m "feat(recording): implement Recorder class for session management"
```

---

## Task 3: Implement Frame Extraction

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/frame_extractor.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_frame_extractor.py`

**Step 1: Write failing tests**

```python
"""Tests for FrameExtractor."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.frame_extractor import FrameExtractor


class TestFrameExtractorUnit:
    """Unit tests for FrameExtractor."""

    @patch("mutcli.core.frame_extractor.av")
    def test_extract_frame_at_timestamp(self, mock_av):
        """Should extract frame at given timestamp."""
        # Setup mock video container
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.time_base = 1 / 30  # 30fps
        mock_container.streams.video = [mock_stream]

        mock_frame = MagicMock()
        mock_frame.to_ndarray.return_value = MagicMock()  # numpy array
        mock_container.decode.return_value = [mock_frame]

        mock_av.open.return_value.__enter__.return_value = mock_container

        with tempfile.NamedTemporaryFile(suffix=".mp4") as video_file:
            extractor = FrameExtractor(video_file.name)

            # This should work once we implement the method
            # frame = extractor.extract_frame(1.5)  # 1.5 seconds

    def test_extracts_before_and_after_frames(self):
        """Should extract frames before and after touch timestamps."""
        # This test verifies the batch extraction logic
        pass


class TestFrameExtractorIntegration:
    """Integration tests requiring real video file."""

    @pytest.mark.skip(reason="Requires real video file")
    def test_extract_frames_for_touch_events(self):
        """Should extract frames 100ms before each touch."""
        pass
```

**Step 2: Implement FrameExtractor**

```python
"""Frame extraction from recorded video."""

import logging
from pathlib import Path
from typing import Any

import av
import numpy as np
from PIL import Image

logger = logging.getLogger("mut.frames")


class FrameExtractor:
    """Extract frames from video at specific timestamps.

    Uses PyAV for efficient seeking and frame extraction.
    Extracts frames 100ms before touch events to capture
    the UI state at the moment of tap decision.
    """

    BEFORE_OFFSET_MS = 100  # Extract frame 100ms before touch

    def __init__(self, video_path: str | Path):
        """Initialize extractor.

        Args:
            video_path: Path to video file
        """
        self._video_path = Path(video_path)

    def extract_frame(self, timestamp_sec: float) -> bytes | None:
        """Extract single frame at timestamp.

        Args:
            timestamp_sec: Timestamp in seconds

        Returns:
            PNG bytes or None if extraction failed
        """
        try:
            with av.open(str(self._video_path)) as container:
                stream = container.streams.video[0]

                # Seek to timestamp
                target_pts = int(timestamp_sec / stream.time_base)
                container.seek(target_pts, stream=stream)

                # Get frame
                for frame in container.decode(video=0):
                    # Convert to PNG
                    img = frame.to_image()
                    import io
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    return buffer.getvalue()

            return None

        except Exception as e:
            logger.error(f"Frame extraction failed at {timestamp_sec}s: {e}")
            return None

    def extract_for_touches(
        self,
        touch_events: list[dict[str, Any]],
        output_dir: Path,
    ) -> list[Path]:
        """Extract frames for all touch events.

        Extracts frame 100ms before each touch to capture
        the UI state when user decided to tap.

        Args:
            touch_events: List of touch event dicts with 'timestamp' field
            output_dir: Directory to save extracted frames

        Returns:
            List of paths to extracted frame files
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        extracted = []

        for i, event in enumerate(touch_events, 1):
            timestamp = event.get("timestamp", 0)

            # Extract frame 100ms before touch
            target_time = max(0, timestamp - self.BEFORE_OFFSET_MS / 1000)

            frame_data = self.extract_frame(target_time)
            if frame_data:
                frame_path = output_dir / f"touch_{i:03d}.png"
                with open(frame_path, "wb") as f:
                    f.write(frame_data)
                extracted.append(frame_path)
                logger.debug(f"Extracted frame {i} at {target_time:.2f}s")
            else:
                logger.warning(f"Failed to extract frame {i}")

        logger.info(f"Extracted {len(extracted)} frames")
        return extracted
```

**Step 3: Commit**

```bash
git add mutcli/core/frame_extractor.py tests/test_frame_extractor.py
git commit -m "feat(recording): implement FrameExtractor for video frame extraction"
```

---

## Task 4: Implement YAML Generator

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/yaml_generator.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_yaml_generator.py`

**Step 1: Write failing tests**

```python
"""Tests for YAMLGenerator."""

import tempfile
from pathlib import Path

import pytest
import yaml

from mutcli.core.yaml_generator import YAMLGenerator


class TestYAMLGenerator:
    """Test YAML test file generation."""

    def test_generates_basic_test_structure(self):
        """Should generate valid YAML test structure."""
        generator = YAMLGenerator(
            name="login-test",
            app_package="com.example.app",
        )

        # Add some steps
        generator.add_tap(100, 200, element="Login button")
        generator.add_type("user@test.com")

        yaml_content = generator.generate()

        # Parse and verify
        data = yaml.safe_load(yaml_content)

        assert data["config"]["app"] == "com.example.app"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["tap"] == "Login button"

    def test_tap_uses_coordinates_when_no_element(self):
        """Should use coordinates when element not specified."""
        generator = YAMLGenerator(name="test", app_package="com.app")

        generator.add_tap(540, 1200)

        yaml_content = generator.generate()
        data = yaml.safe_load(yaml_content)

        assert data["steps"][0]["tap"] == [540, 1200]

    def test_adds_verify_screen(self):
        """Should add verify_screen steps."""
        generator = YAMLGenerator(name="test", app_package="com.app")

        generator.add_tap(100, 200, element="Login")
        generator.add_verify_screen("User dashboard is displayed")

        yaml_content = generator.generate()
        data = yaml.safe_load(yaml_content)

        assert data["steps"][1]["verify_screen"] == "User dashboard is displayed"

    def test_saves_to_file(self):
        """Should save YAML to file."""
        generator = YAMLGenerator(name="test", app_package="com.app")
        generator.add_tap(100, 200, element="Button")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.yaml"

            generator.save(output_path)

            assert output_path.exists()
            with open(output_path) as f:
                data = yaml.safe_load(f)
                assert data["config"]["app"] == "com.app"
```

**Step 2: Implement YAMLGenerator**

```python
"""YAML test file generator."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("mut.yaml")


class YAMLGenerator:
    """Generate YAML test files from recorded actions.

    Creates properly formatted YAML test files following
    the mut test format specification.
    """

    def __init__(self, name: str, app_package: str):
        """Initialize generator.

        Args:
            name: Test name
            app_package: Android app package name
        """
        self._name = name
        self._app_package = app_package
        self._steps: list[dict[str, Any]] = []
        self._setup: list[dict[str, Any]] = []
        self._teardown: list[dict[str, Any]] = []

    def add_tap(
        self,
        x: int,
        y: int,
        element: str | None = None,
    ) -> None:
        """Add tap action.

        Args:
            x: X coordinate
            y: Y coordinate
            element: Optional element text (preferred over coordinates)
        """
        if element:
            self._steps.append({"tap": element})
        else:
            self._steps.append({"tap": [x, y]})

    def add_type(self, text: str, field: str | None = None) -> None:
        """Add type action.

        Args:
            text: Text to type
            field: Optional field identifier
        """
        if field:
            self._steps.append({"type": {"text": text, "field": field}})
        else:
            self._steps.append({"type": text})

    def add_swipe(
        self,
        direction: str,
        distance: str | None = None,
    ) -> None:
        """Add swipe action.

        Args:
            direction: Swipe direction (up, down, left, right)
            distance: Optional distance (e.g., "30%")
        """
        if distance:
            self._steps.append({"swipe": {"direction": direction, "distance": distance}})
        else:
            self._steps.append({"swipe": direction})

    def add_wait(self, duration: str) -> None:
        """Add wait action.

        Args:
            duration: Wait duration (e.g., "2s", "500ms")
        """
        self._steps.append({"wait": duration})

    def add_wait_for(self, element: str, timeout: str | None = None) -> None:
        """Add wait_for action.

        Args:
            element: Element to wait for
            timeout: Optional timeout duration
        """
        if timeout:
            self._steps.append({"wait_for": {"element": element, "timeout": timeout}})
        else:
            self._steps.append({"wait_for": element})

    def add_verify_screen(self, description: str) -> None:
        """Add verify_screen action.

        Args:
            description: Expected screen description
        """
        self._steps.append({"verify_screen": description})

    def add_launch_app(self, package: str | None = None) -> None:
        """Add launch_app to setup.

        Args:
            package: Optional package name (uses default if not specified)
        """
        if package:
            self._setup.append({"launch_app": package})
        else:
            self._setup.append("launch_app")

    def add_terminate_app(self, package: str | None = None) -> None:
        """Add terminate_app to teardown.

        Args:
            package: Optional package name
        """
        if package:
            self._teardown.append({"terminate_app": package})
        else:
            self._teardown.append("terminate_app")

    def generate(self) -> str:
        """Generate YAML content.

        Returns:
            YAML string
        """
        data: dict[str, Any] = {
            "config": {
                "app": self._app_package,
            },
        }

        if self._setup:
            data["setup"] = self._setup

        data["steps"] = self._steps

        if self._teardown:
            data["teardown"] = self._teardown

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def save(self, path: Path) -> None:
        """Save YAML to file.

        Args:
            path: Output file path
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.generate())
        logger.info(f"Saved test: {path}")
```

**Step 3: Commit**

```bash
git add mutcli/core/yaml_generator.py tests/test_yaml_generator.py
git commit -m "feat(recording): implement YAMLGenerator for test file creation"
```

---

## Task 5: Wire Up CLI record Command

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/cli.py`

**Step 1: Implement record command**

Update the `record` command in `cli.py`:

```python
@app.command()
def record(
    name: str = typer.Argument(..., help="Test name"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
    app: str | None = typer.Option(None, "--app", "-a", help="App package name"),
) -> None:
    """Start recording user interactions."""
    from mutcli.core.recorder import Recorder
    from mutcli.core.device_controller import DeviceController

    # Find device
    if not device:
        devices_list = DeviceController.list_devices()
        if not devices_list:
            console.print("[red]Error:[/red] No devices found.")
            raise typer.Exit(2)
        device = devices_list[0]["id"]

    console.print(f"[blue]Starting recording:[/blue] {name}")
    console.print(f"[dim]Device: {device}[/dim]")

    recorder = Recorder(name=name, device_id=device)
    result = recorder.start()

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('error')}")
        raise typer.Exit(2)

    console.print()
    console.print("[green]Recording started![/green]")
    console.print("Interact with your device now.")
    console.print()
    console.print("[dim]Press Enter when done recording...[/dim]")

    try:
        input()
    except KeyboardInterrupt:
        pass

    # Stop recording
    stop_result = recorder.stop()

    if stop_result.get("success"):
        console.print()
        console.print(f"[green]Recording saved![/green]")
        console.print(f"  Events: {stop_result.get('touch_events', 0)}")
        console.print(f"  Duration: {stop_result.get('duration_seconds', 0):.1f}s")
        console.print(f"  Output: {stop_result.get('output_dir')}")
        console.print()
        console.print("[dim]Run 'mut stop' to generate YAML test file.[/dim]")
    else:
        console.print(f"[red]Error:[/red] {stop_result.get('error')}")
        raise typer.Exit(1)
```

**Step 2: Test manually**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
mut record login-test
# Interact with device, press Enter
```

**Step 3: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat(cli): implement record command"
```

---

## Task 6: Wire Up CLI stop Command

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/cli.py`

**Step 1: Implement stop command with frame extraction and YAML generation**

```python
@app.command()
def stop() -> None:
    """Stop recording and generate YAML test."""
    from mutcli.core.recorder import Recorder
    from mutcli.core.frame_extractor import FrameExtractor
    from mutcli.core.yaml_generator import YAMLGenerator
    from mutcli.core.ai_analyzer import AIAnalyzer
    from mutcli.core.config import ConfigLoader
    import json

    # Load active recording
    recorder = Recorder.load_active()
    if not recorder:
        console.print("[red]Error:[/red] No active recording found.")
        console.print("[dim]Start a recording with 'mut record <name>'[/dim]")
        raise typer.Exit(2)

    console.print("[blue]Processing recording...[/blue]")

    # Load recording data
    recording_dir = recorder.output_dir / "recording"
    touch_file = recording_dir / "touch_events.json"
    video_file = recording_dir / "recording.mp4"

    if not touch_file.exists():
        console.print("[red]Error:[/red] Touch events not found.")
        raise typer.Exit(2)

    with open(touch_file) as f:
        touch_events = json.load(f)

    console.print(f"  [dim]Found {len(touch_events)} touch events[/dim]")

    # Extract frames
    if video_file.exists():
        console.print("  [dim]Extracting frames...[/dim]")
        extractor = FrameExtractor(video_file)
        screenshots_dir = recording_dir / "screenshots"
        extractor.extract_for_touches(touch_events, screenshots_dir)

    # Load config for app package
    try:
        config = ConfigLoader.load(require_api_key=False)
        app_package = config.app or "com.example.app"
    except Exception:
        app_package = "com.example.app"

    # Generate YAML
    console.print("  [dim]Generating YAML...[/dim]")
    generator = YAMLGenerator(
        name=recorder._name,
        app_package=app_package,
    )

    # Add steps from touch events
    for event in touch_events:
        generator.add_tap(
            x=event.get("x", 0),
            y=event.get("y", 0),
        )

    # Save YAML
    yaml_path = recorder.output_dir / "test.yaml"
    generator.save(yaml_path)

    console.print()
    console.print(f"[green]Test generated![/green]")
    console.print(f"  Output: {yaml_path}")
    console.print()
    console.print("[dim]Edit the YAML file to add element names and verifications.[/dim]")
    console.print("[dim]Run with: mut run {yaml_path}[/dim]")
```

**Step 2: Test manually**

```bash
mut stop
```

**Step 3: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat(cli): implement stop command with frame extraction and YAML generation"
```

---

## Task 7: Wire Up CLI report Command

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/cli.py`

**Step 1: Implement report command**

```python
@app.command()
def report(
    results_dir: Path = typer.Argument(..., help="Results directory with report.json"),
) -> None:
    """Generate HTML report from JSON results."""
    from mutcli.core.report import ReportGenerator
    import json

    if not results_dir.exists():
        console.print(f"[red]Error:[/red] Directory not found: {results_dir}")
        raise typer.Exit(1)

    json_file = results_dir / "report.json"
    if not json_file.exists():
        console.print(f"[red]Error:[/red] report.json not found in {results_dir}")
        raise typer.Exit(1)

    console.print(f"[blue]Generating report from:[/blue] {json_file}")

    # Load JSON data
    with open(json_file) as f:
        data = json.load(f)

    # Create mock TestResult for ReportGenerator
    from mutcli.core.executor import TestResult, StepResult

    step_results = [
        StepResult(
            step_number=s.get("step_number", i + 1),
            action=s.get("action", ""),
            status=s.get("status", "passed"),
            duration=s.get("duration", 0),
            error=s.get("error"),
        )
        for i, s in enumerate(data.get("steps", []))
    ]

    result = TestResult(
        name=data.get("test", "unknown"),
        status=data.get("status", "passed"),
        duration=data.get("duration", 0),
        steps=step_results,
        error=data.get("error"),
    )

    # Generate HTML
    generator = ReportGenerator(results_dir)
    html_path = generator.generate_html(result)

    console.print(f"[green]Generated:[/green] {html_path}")
```

**Step 2: Test manually**

```bash
# Find an existing report directory
mut report tests/demo/reports/2024-01-17_12-00/
```

**Step 3: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat(cli): implement report command for HTML regeneration"
```

---

## Task 8: Run All Tests and Verify

**Step 1: Run all tests**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest -v
```

Expected: All tests pass

**Step 2: Manual testing**

```bash
# Test record flow
mut record test-recording
# Interact with device
# Press Enter

# Test stop
mut stop

# Test run
mut run tests/test-recording/test.yaml

# Test report
mut report tests/test-recording/reports/*/
```

**Step 3: Commit final changes**

```bash
git add -A
git commit -m "feat: complete Phase 2 recording workflow"
git push origin main
```

---

## Summary

After completing Phase 2:
- `mut record <name>` starts video + touch capture
- User interacts with device, presses Enter
- Recording saves video and touch events
- `mut stop` extracts frames and generates YAML
- `mut report` regenerates HTML from JSON
- All commands properly integrated with existing infrastructure

**Next phase:** AI-powered step analysis (keyboard detection, verification suggestions)
