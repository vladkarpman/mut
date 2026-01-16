"""Integration tests for mut."""

import io
import tempfile
import time
from pathlib import Path

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

    def test_multiple_recordings(self, device_id):
        """Should be able to start/stop recording multiple times."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(0.5)

            with tempfile.TemporaryDirectory() as tmpdir:
                # First recording
                path1 = Path(tmpdir) / "test1.mp4"
                result1 = service.start_recording(str(path1))
                assert result1["success"]
                time.sleep(1)
                stop1 = service.stop_recording()
                assert stop1["success"]
                assert path1.exists()

                # Second recording
                path2 = Path(tmpdir) / "test2.mp4"
                result2 = service.start_recording(str(path2))
                assert result2["success"]
                time.sleep(1)
                stop2 = service.stop_recording()
                assert stop2["success"]
                assert path2.exists()

                # Both files should exist with non-zero size
                assert path1.stat().st_size > 0
                assert path2.stat().st_size > 0

        finally:
            service.disconnect()

    def test_screenshot_consistency(self, device_id):
        """Screenshots should have consistent dimensions."""
        service = ScrcpyService(device_id)
        service.connect()

        try:
            time.sleep(0.5)

            # Take multiple screenshots
            screenshots = []
            for _ in range(3):
                screenshots.append(service.screenshot())
                time.sleep(0.1)

            # All should have the same dimensions
            dimensions = []
            for ss in screenshots:
                img = Image.open(io.BytesIO(ss))
                dimensions.append((img.width, img.height))

            # All dimensions should match
            first_dim = dimensions[0]
            for dim in dimensions[1:]:
                assert dim == first_dim, "Screenshot dimensions should be consistent"

        finally:
            service.disconnect()
