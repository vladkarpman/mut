"""Tests for ScrcpyService."""

import pytest
from unittest.mock import MagicMock, patch
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
        with patch("mut.core.scrcpy_service.adb") as mock_adb:
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
