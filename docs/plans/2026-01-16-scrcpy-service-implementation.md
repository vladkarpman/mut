# ScrcpyService Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement ScrcpyService with MYScrcpy for fast screenshots (~50ms) and video recording via PyAV.

**Architecture:** Single MYScrcpy connection maintains a 10-frame circular buffer. Screenshots return instantly from buffer. Recording writes frames to video file in parallel using PyAV h264 encoding.

**Tech Stack:** MYScrcpy (scrcpy 3.x Python client), PyAV (FFmpeg bindings), PIL/numpy (image conversion)

---

## Prerequisites

Before starting, ensure:
- Android device connected (`adb devices` shows device)
- scrcpy 3.x installed (`scrcpy --version`)
- Python 3.11+ with venv

---

## Task 1: Project Setup and Dependencies

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/pyproject.toml`

**Step 1: Create virtual environment and install dependencies**

```bash
cd /Users/vladislavkarpman/Projects/mut
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: Installation completes. Some dependencies may fail (mysc) - that's expected, we'll verify next.

**Step 2: Verify MYScrcpy is importable**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
python -c "from myscrcpy.core import Session, VideoArgs; print('MYScrcpy OK')"
```

Expected: `MYScrcpy OK` or import error. If error, we need to troubleshoot.

**Step 3: Verify PyAV is importable**

```bash
python -c "import av; print('PyAV OK')"
```

Expected: `PyAV OK`

**Step 4: Commit if setup works**

```bash
git add -A
git commit -m "chore: verify dependencies work"
```

---

## Task 2: Test ScrcpyService Connection

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_scrcpy_service.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/core/scrcpy_service.py`

**Step 1: Write the failing test for connection**

```python
"""Tests for ScrcpyService."""

import pytest
from mut.core.scrcpy_service import ScrcpyService
from mut.core.device_controller import DeviceController


@pytest.fixture
def device_id():
    """Get first available device ID."""
    devices = DeviceController.list_devices()
    if not devices:
        pytest.skip("No Android device connected")
    return devices[0]["id"]


class TestScrcpyServiceConnection:
    """Test ScrcpyService connection."""

    def test_connect_returns_true_when_device_available(self, device_id):
        """Should connect to device and return True."""
        service = ScrcpyService(device_id)

        result = service.connect()

        assert result is True
        assert service.is_connected is True

        service.disconnect()

    def test_is_connected_false_before_connect(self, device_id):
        """Should be False before connect() is called."""
        service = ScrcpyService(device_id)

        assert service.is_connected is False
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest tests/test_scrcpy_service.py -v
```

Expected: FAIL with `NotImplementedError` or connection fails

**Step 3: Implement connect() method**

Replace the entire `scrcpy_service.py`:

```python
"""Scrcpy service for fast screenshots and video recording."""

import io
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from adbutils import adb
from myscrcpy.core import Session, VideoArgs
from PIL import Image
import numpy as np

logger = logging.getLogger("mut.scrcpy")


class ScrcpyService:
    """Unified scrcpy service for screenshots and recording.

    Uses MYScrcpy for scrcpy 3.x support. Maintains a circular frame buffer
    for instant screenshots (~50ms) and handles video recording via PyAV.
    """

    FRAME_BUFFER_SIZE = 10

    def __init__(self, device_id: str):
        """Initialize service for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._session: Session | None = None
        self._frame_buffer: deque = deque(maxlen=self.FRAME_BUFFER_SIZE)
        self._lock = threading.Lock()
        self._running = False
        self._frame_thread: threading.Thread | None = None
        self._width = 0
        self._height = 0

        # Recording state
        self._recording = False
        self._video_writer = None
        self._video_stream = None
        self._recording_output_path: str | None = None
        self._recording_start_time: float | None = None

    @property
    def is_connected(self) -> bool:
        """Check if scrcpy is connected and receiving frames."""
        return (
            self._session is not None
            and self._running
            and self._session.va is not None
        )

    @property
    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._recording and self._video_writer is not None

    def connect(self) -> bool:
        """Connect to device via MYScrcpy.

        Returns:
            True if connected successfully
        """
        if self.is_connected:
            return True

        try:
            # Find device
            devices = adb.device_list()
            device = None
            for d in devices:
                if d.serial == self._device_id:
                    device = d
                    break

            if device is None:
                logger.error(f"Device {self._device_id} not found")
                return False

            logger.info(f"Connecting to {self._device_id}...")

            # Create session with video only
            self._session = Session(
                device,
                video_args=VideoArgs(fps=60),
                control_args=None,  # No control needed
            )

            # Wait for video stream to initialize
            time.sleep(1.0)

            if self._session.va is None:
                logger.error("Video stream failed to initialize")
                self._session = None
                return False

            # Start frame capture thread
            self._running = True
            self._frame_thread = threading.Thread(
                target=self._frame_loop,
                daemon=True,
            )
            self._frame_thread.start()

            # Wait for first frame
            time.sleep(0.5)

            logger.info(f"Connected to {self._device_id}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._session = None
            return False

    def disconnect(self) -> None:
        """Disconnect from device and clean up."""
        self._running = False

        if self._frame_thread:
            self._frame_thread.join(timeout=2)
            self._frame_thread = None

        if self._session:
            try:
                self._session.stop()
            except Exception:
                pass
            self._session = None

        with self._lock:
            self._frame_buffer.clear()

        self._width = 0
        self._height = 0
        logger.info("Disconnected")

    def _frame_loop(self) -> None:
        """Continuous frame capture loop."""
        while self._running and self._session and self._session.va:
            try:
                frame = self._session.va.get_frame()
                if frame is not None:
                    timestamp = time.time()

                    with self._lock:
                        self._frame_buffer.append({
                            "frame": frame,
                            "timestamp": timestamp,
                        })

                        # Update dimensions from first frame
                        if self._height == 0:
                            self._height, self._width = frame.shape[:2]

                    # Write to video if recording
                    if self._recording:
                        self._write_frame(frame)

                time.sleep(0.016)  # ~60 fps polling

            except Exception as e:
                logger.debug(f"Frame loop error: {e}")
                time.sleep(0.1)

    def screenshot(self) -> bytes:
        """Get latest frame as PNG from buffer.

        Returns:
            PNG image bytes

        Raises:
            RuntimeError: If not connected or no frames available
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to device")

        with self._lock:
            if not self._frame_buffer:
                raise RuntimeError("No frames available in buffer")

            frame_data = self._frame_buffer[-1]
            frame = frame_data["frame"]

        # Convert numpy array to PNG bytes
        img = Image.fromarray(frame)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def start_recording(self, output_path: str) -> dict[str, Any]:
        """Start writing frames to video file.

        Args:
            output_path: Path to output video file (.mp4)

        Returns:
            Dict with success status and recording_start_time
        """
        if self.is_recording:
            return {"success": False, "error": "Recording already in progress"}

        if not self.is_connected:
            return {"success": False, "error": "Not connected to device"}

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            import av

            self._video_writer = av.open(output_path, "w")
            self._video_stream = self._video_writer.add_stream("h264", rate=30)
            self._video_stream.width = self._width
            self._video_stream.height = self._height
            self._video_stream.pix_fmt = "yuv420p"

            self._recording = True
            self._recording_output_path = output_path
            self._recording_start_time = time.time()

            logger.info(f"Recording started: {output_path}")

            return {
                "success": True,
                "output_path": output_path,
                "recording_start_time": self._recording_start_time,
            }

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return {"success": False, "error": str(e)}

    def stop_recording(self) -> dict[str, Any]:
        """Stop recording and finalize video.

        Returns:
            Dict with recording info
        """
        if not self.is_recording:
            return {"success": False, "error": "No recording in progress"}

        duration = time.time() - (self._recording_start_time or 0)
        output_path = self._recording_output_path

        try:
            self._recording = False

            # Finalize video
            if self._video_writer:
                self._video_writer.close()

            file_size = Path(output_path).stat().st_size if output_path else 0

            logger.info(f"Recording stopped: {output_path} ({duration:.1f}s)")

            return {
                "success": True,
                "output_path": output_path,
                "duration_seconds": round(duration, 2),
                "file_size_bytes": file_size,
            }

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            return {"success": False, "error": str(e)}

        finally:
            self._video_writer = None
            self._video_stream = None
            self._recording_output_path = None
            self._recording_start_time = None

    def _write_frame(self, frame: np.ndarray) -> None:
        """Write frame to video file."""
        if not self._video_writer or not self._video_stream:
            return

        try:
            import av

            # Convert RGB to video frame
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")

            # Encode and write
            for packet in self._video_stream.encode(video_frame):
                self._video_writer.mux(packet)

        except Exception as e:
            logger.debug(f"Error writing frame: {e}")

    def get_buffer_info(self) -> dict[str, Any]:
        """Get info about current frame buffer state."""
        with self._lock:
            count = len(self._frame_buffer)
            oldest_ts = self._frame_buffer[0]["timestamp"] if count > 0 else None
            newest_ts = self._frame_buffer[-1]["timestamp"] if count > 0 else None

        return {
            "frame_count": count,
            "buffer_size": self.FRAME_BUFFER_SIZE,
            "width": self._width,
            "height": self._height,
            "oldest_frame_age_ms": int((time.time() - oldest_ts) * 1000) if oldest_ts else None,
            "newest_frame_age_ms": int((time.time() - newest_ts) * 1000) if newest_ts else None,
        }
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_scrcpy_service.py::TestScrcpyServiceConnection -v
```

Expected: PASS (both tests)

**Step 5: Commit**

```bash
git add tests/test_scrcpy_service.py mut/core/scrcpy_service.py
git commit -m "feat(scrcpy): implement connection with MYScrcpy"
```

---

## Task 3: Test Screenshot Functionality

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_scrcpy_service.py`

**Step 1: Add screenshot tests**

Append to `tests/test_scrcpy_service.py`:

```python
class TestScrcpyServiceScreenshot:
    """Test screenshot functionality."""

    def test_screenshot_returns_png_bytes(self, device_id):
        """Should return valid PNG image bytes."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            # Wait for frames to accumulate
            time.sleep(0.5)

            screenshot = service.screenshot()

            # Check it's bytes
            assert isinstance(screenshot, bytes)

            # Check PNG magic bytes
            assert screenshot[:8] == b'\x89PNG\r\n\x1a\n'

            # Check it's a valid image
            img = Image.open(io.BytesIO(screenshot))
            assert img.width > 0
            assert img.height > 0

        finally:
            service.disconnect()

    def test_screenshot_raises_when_not_connected(self, device_id):
        """Should raise RuntimeError when not connected."""
        service = ScrcpyService(device_id)

        with pytest.raises(RuntimeError, match="Not connected"):
            service.screenshot()

    def test_screenshot_is_fast(self, device_id):
        """Screenshot should complete in under 100ms."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(0.5)  # Wait for buffer

            start = time.perf_counter()
            service.screenshot()
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert elapsed_ms < 100, f"Screenshot took {elapsed_ms:.1f}ms, expected <100ms"

        finally:
            service.disconnect()
```

Also add imports at top of file:

```python
import io
import time
from PIL import Image
```

**Step 2: Run tests**

```bash
pytest tests/test_scrcpy_service.py::TestScrcpyServiceScreenshot -v
```

Expected: PASS (all 3 tests)

**Step 3: Commit**

```bash
git add tests/test_scrcpy_service.py
git commit -m "test(scrcpy): add screenshot tests"
```

---

## Task 4: Test Video Recording

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_scrcpy_service.py`

**Step 1: Add recording tests**

Append to `tests/test_scrcpy_service.py`:

```python
import tempfile
from pathlib import Path


class TestScrcpyServiceRecording:
    """Test video recording functionality."""

    def test_start_recording_creates_file(self, device_id):
        """Should start recording and create output file."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(0.5)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "test.mp4"

                result = service.start_recording(str(output_path))

                assert result["success"] is True
                assert service.is_recording is True

                # Record for 2 seconds
                time.sleep(2)

                stop_result = service.stop_recording()

                assert stop_result["success"] is True
                assert stop_result["duration_seconds"] >= 1.5
                assert output_path.exists()
                assert output_path.stat().st_size > 0

        finally:
            service.disconnect()

    def test_start_recording_fails_when_not_connected(self, device_id):
        """Should fail if not connected."""
        service = ScrcpyService(device_id)

        result = service.start_recording("/tmp/test.mp4")

        assert result["success"] is False
        assert "Not connected" in result["error"]

    def test_stop_recording_fails_when_not_recording(self, device_id):
        """Should fail if not recording."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            result = service.stop_recording()

            assert result["success"] is False
            assert "No recording" in result["error"]

        finally:
            service.disconnect()
```

**Step 2: Run tests**

```bash
pytest tests/test_scrcpy_service.py::TestScrcpyServiceRecording -v
```

Expected: PASS (all 3 tests)

**Step 3: Commit**

```bash
git add tests/test_scrcpy_service.py
git commit -m "test(scrcpy): add recording tests"
```

---

## Task 5: Integration Test - Full Flow

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_integration.py`

**Step 1: Write integration test**

```python
"""Integration tests for mut."""

import tempfile
import time
from pathlib import Path

import pytest
from PIL import Image
import io

from mut.core.scrcpy_service import ScrcpyService
from mut.core.device_controller import DeviceController


@pytest.fixture
def device_id():
    """Get first available device ID."""
    devices = DeviceController.list_devices()
    if not devices:
        pytest.skip("No Android device connected")
    return devices[0]["id"]


class TestFullFlow:
    """Test complete screenshot + recording flow."""

    def test_screenshot_during_recording(self, device_id):
        """Should be able to take screenshots while recording."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(0.5)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "test.mp4"

                # Start recording
                service.start_recording(str(output_path))

                # Take screenshots during recording
                screenshots = []
                for _ in range(5):
                    screenshot = service.screenshot()
                    screenshots.append(screenshot)
                    time.sleep(0.2)

                # Stop recording
                result = service.stop_recording()

                # Verify all screenshots are valid
                for i, ss in enumerate(screenshots):
                    img = Image.open(io.BytesIO(ss))
                    assert img.width > 0, f"Screenshot {i} invalid"

                # Verify recording
                assert result["success"]
                assert output_path.exists()

        finally:
            service.disconnect()

    def test_buffer_info(self, device_id):
        """Should report accurate buffer info."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(1)  # Let buffer fill

            info = service.get_buffer_info()

            assert info["frame_count"] > 0
            assert info["width"] > 0
            assert info["height"] > 0
            assert info["newest_frame_age_ms"] < 500

        finally:
            service.disconnect()
```

**Step 2: Run integration tests**

```bash
pytest tests/test_integration.py -v
```

Expected: PASS (both tests)

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for scrcpy service"
```

---

## Task 6: Update CLI devices Command

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mut/cli.py`

**Step 1: Test CLI devices command works**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
mut devices
```

Expected: Shows table with connected devices

**Step 2: Commit if any changes needed**

```bash
git add -A
git commit -m "chore: verify CLI works with scrcpy service"
```

---

## Task 7: Push All Changes

**Step 1: Run all tests**

```bash
pytest -v
```

Expected: All tests pass

**Step 2: Push to GitHub**

```bash
git push origin main
```

---

## Summary

After completing all tasks:
- ✅ ScrcpyService connects to device via MYScrcpy
- ✅ Frame buffer provides instant screenshots (~50ms)
- ✅ Video recording works via PyAV
- ✅ Screenshots work during recording
- ✅ All tests pass

**Next phase:** Implement AIAnalyzer (Gemini 2.5 Flash integration)
