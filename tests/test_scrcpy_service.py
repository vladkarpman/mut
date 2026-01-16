"""Tests for ScrcpyService."""

import io
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from mutcli.core.device_controller import DeviceController
from mutcli.core.scrcpy_service import ScrcpyService


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


class TestScrcpyServiceUnit:
    """Unit tests for ScrcpyService (mocked, no device required)."""

    def test_is_connected_false_initially(self):
        """Should be False before connect() is called."""
        service = ScrcpyService("fake-device-id")

        assert service.is_connected is False

    def test_is_recording_false_initially(self):
        """Should be False before start_recording() is called."""
        service = ScrcpyService("fake-device-id")

        assert service.is_recording is False

    def test_connect_returns_false_when_device_not_found(self):
        """Should return False when device not in adb list."""
        with patch("mutcli.core.scrcpy_service.adb") as mock_adb:
            mock_adb.device_list.return_value = []

            service = ScrcpyService("nonexistent-device")
            result = service.connect()

            assert result is False
            assert service.is_connected is False

    def test_disconnect_clears_state(self):
        """Should clear all state on disconnect."""
        service = ScrcpyService("fake-device-id")
        # Manually set some state to verify cleanup
        service._running = True
        service._frame_buffer.append({"frame": None, "timestamp": 0})

        service.disconnect()

        assert service._running is False
        assert len(service._frame_buffer) == 0
        assert service._session is None


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
