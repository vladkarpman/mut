"""Tests for DeviceController."""

from unittest.mock import call, patch

import pytest

from mutcli.core.device_controller import DeviceController


@pytest.fixture
def controller():
    """Create a DeviceController instance for testing."""
    return DeviceController("test-device-123")


class TestLongPress:
    """Tests for long_press method."""

    def test_long_press_executes_adb_command(self, controller):
        """Verify long_press executes correct adb swipe command."""
        with patch.object(controller, "_adb") as mock_adb:
            controller.long_press(100, 200, duration_ms=1000)

            mock_adb.assert_called_once_with([
                "shell", "input", "swipe",
                "100", "200", "100", "200", "1000"
            ])

    def test_long_press_default_duration(self, controller):
        """Verify default duration is 500ms."""
        with patch.object(controller, "_adb") as mock_adb:
            controller.long_press(50, 75)

            mock_adb.assert_called_once_with([
                "shell", "input", "swipe",
                "50", "75", "50", "75", "500"
            ])

    def test_long_press_custom_duration(self, controller):
        """Verify custom duration is passed correctly."""
        with patch.object(controller, "_adb") as mock_adb:
            controller.long_press(300, 400, duration_ms=2000)

            mock_adb.assert_called_once_with([
                "shell", "input", "swipe",
                "300", "400", "300", "400", "2000"
            ])


class TestDoubleTap:
    """Tests for double_tap method."""

    def test_double_tap_executes_two_taps(self, controller):
        """Verify double_tap executes two tap commands in order."""
        with patch.object(controller, "_adb") as mock_adb:
            controller.double_tap(150, 250)

            assert mock_adb.call_count == 2
            mock_adb.assert_has_calls([
                call(["shell", "input", "tap", "150", "250"]),
                call(["shell", "input", "tap", "150", "250"]),
            ])

    def test_double_tap_default_delay(self, controller):
        """Verify default delay between taps is 100ms."""
        with patch.object(controller, "_adb"), \
             patch("mutcli.core.device_controller.time.sleep") as mock_sleep:
            controller.double_tap(100, 200)

            mock_sleep.assert_called_once_with(0.1)

    def test_double_tap_custom_delay(self, controller):
        """Verify custom delay is applied correctly."""
        with patch.object(controller, "_adb"), \
             patch("mutcli.core.device_controller.time.sleep") as mock_sleep:
            controller.double_tap(100, 200, delay_ms=50)

            mock_sleep.assert_called_once_with(0.05)

    def test_double_tap_raises_on_negative_coordinates(self, controller):
        """Verify double_tap raises ValueError for negative coordinates."""
        with pytest.raises(ValueError, match="Coordinates must be non-negative"):
            controller.double_tap(-10, 200)

        with pytest.raises(ValueError, match="Coordinates must be non-negative"):
            controller.double_tap(100, -20)

    def test_double_tap_raises_on_negative_delay(self, controller):
        """Verify double_tap raises ValueError for negative delay."""
        with pytest.raises(ValueError, match="Delay must be non-negative"):
            controller.double_tap(100, 200, delay_ms=-50)


class TestLongPressValidation:
    """Validation tests for long_press method."""

    def test_long_press_raises_on_negative_coordinates(self, controller):
        """Verify long_press raises ValueError for negative coordinates."""
        with pytest.raises(ValueError, match="Coordinates must be non-negative"):
            controller.long_press(-10, 200)

        with pytest.raises(ValueError, match="Coordinates must be non-negative"):
            controller.long_press(100, -20)

    def test_long_press_raises_on_invalid_duration(self, controller):
        """Verify long_press raises ValueError for non-positive duration."""
        with pytest.raises(ValueError, match="Duration must be positive"):
            controller.long_press(100, 200, duration_ms=0)

        with pytest.raises(ValueError, match="Duration must be positive"):
            controller.long_press(100, 200, duration_ms=-500)
