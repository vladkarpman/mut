"""Tests for TouchMonitor."""

import time
from unittest.mock import MagicMock, patch

from mutcli.core.touch_monitor import TouchEvent, TouchMonitor


class TestTouchEvent:
    """Test TouchEvent dataclass."""

    def test_creation(self):
        """TouchEvent should store all fields correctly."""
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

    def test_to_dict(self):
        """to_dict should return all fields."""
        event = TouchEvent(
            timestamp=2.5,
            x=100,
            y=200,
            event_type="swipe_start",
        )

        result = event.to_dict()

        assert result == {
            "timestamp": 2.5,
            "x": 100,
            "y": 200,
            "event_type": "swipe_start",
        }

    def test_to_dict_returns_new_dict(self):
        """to_dict should return a new dict each time."""
        event = TouchEvent(timestamp=0, x=0, y=0, event_type="tap")

        dict1 = event.to_dict()
        dict2 = event.to_dict()

        assert dict1 is not dict2


class TestTouchMonitorInitialization:
    """Test TouchMonitor initialization."""

    def test_is_running_false_initially(self):
        """is_running should be False before start()."""
        monitor = TouchMonitor("fake-device-id")

        assert monitor.is_running is False

    def test_get_events_empty_initially(self):
        """get_events should return empty list initially."""
        monitor = TouchMonitor("fake-device-id")

        events = monitor.get_events()

        assert events == []

    def test_device_id_stored(self):
        """Device ID should be stored."""
        monitor = TouchMonitor("test-device-123")

        assert monitor._device_id == "test-device-123"


class TestTouchMonitorStart:
    """Test TouchMonitor start/stop."""

    def test_start_launches_adb_getevent(self):
        """start() should launch adb getevent subprocess."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter([])  # Empty iterator
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            result = monitor.start()

            # Give thread time to start
            time.sleep(0.1)

            assert result is True
            assert monitor.is_running is True

            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            cmd = call_args[0][0]

            assert "adb" in cmd
            assert "-s" in cmd
            assert "test-device" in cmd
            assert "getevent" in cmd
            assert "-lt" in cmd

            monitor.stop()

    def test_start_returns_false_on_process_error(self):
        """start() should return False if subprocess fails."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = OSError("adb not found")

            monitor = TouchMonitor("test-device")
            result = monitor.start()

            assert result is False
            assert monitor.is_running is False

    def test_stop_clears_running_state(self):
        """stop() should set is_running to False."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.1)

            assert monitor.is_running is True

            monitor.stop()

            assert monitor.is_running is False

    def test_stop_terminates_process(self):
        """stop() should terminate the subprocess."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.1)

            monitor.stop()

            mock_process.terminate.assert_called()

    def test_stop_when_not_running(self):
        """stop() should be safe to call when not running."""
        monitor = TouchMonitor("test-device")

        # Should not raise
        monitor.stop()

        assert monitor.is_running is False


class TestTouchMonitorEventParsing:
    """Test getevent line parsing."""

    def test_parses_tap_event(self):
        """Should parse tap from getevent lines."""
        # Simulate getevent output for a tap
        getevent_lines = [
            "[   123.456789] /dev/input/event5: EV_ABS ABS_MT_POSITION_X 00000219",
            "[   123.456790] /dev/input/event5: EV_ABS ABS_MT_POSITION_Y 000004b0",
            "[   123.456791] /dev/input/event5: EV_KEY BTN_TOUCH DOWN",
            "[   123.456792] /dev/input/event5: EV_SYN SYN_REPORT 00000000",
            "[   123.556789] /dev/input/event5: EV_KEY BTN_TOUCH UP",
            "[   123.556790] /dev/input/event5: EV_SYN SYN_REPORT 00000000",
        ]

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter(getevent_lines)
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()

            # Wait for processing
            time.sleep(0.2)

            monitor.stop()

            events = monitor.get_events()

            assert len(events) == 1
            event = events[0]
            assert event.x == 0x219  # 537 decimal
            assert event.y == 0x4b0  # 1200 decimal
            assert event.event_type == "tap"

    def test_ignores_non_touch_events(self):
        """Should ignore non-touch events."""
        getevent_lines = [
            "[   123.456789] /dev/input/event5: EV_KEY KEY_VOLUMEDOWN DOWN",
            "[   123.456790] /dev/input/event5: EV_SYN SYN_REPORT 00000000",
            "[   123.556789] /dev/input/event5: EV_KEY KEY_VOLUMEDOWN UP",
        ]

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter(getevent_lines)
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.2)
            monitor.stop()

            events = monitor.get_events()

            assert len(events) == 0

    def test_parses_multiple_taps(self):
        """Should parse multiple consecutive taps."""
        getevent_lines = [
            # First tap
            "[   123.456789] /dev/input/event5: EV_ABS ABS_MT_POSITION_X 00000064",
            "[   123.456790] /dev/input/event5: EV_ABS ABS_MT_POSITION_Y 000000c8",
            "[   123.456791] /dev/input/event5: EV_KEY BTN_TOUCH DOWN",
            "[   123.556789] /dev/input/event5: EV_KEY BTN_TOUCH UP",
            # Second tap
            "[   124.456789] /dev/input/event5: EV_ABS ABS_MT_POSITION_X 000001f4",
            "[   124.456790] /dev/input/event5: EV_ABS ABS_MT_POSITION_Y 000003e8",
            "[   124.456791] /dev/input/event5: EV_KEY BTN_TOUCH DOWN",
            "[   124.556789] /dev/input/event5: EV_KEY BTN_TOUCH UP",
        ]

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = iter(getevent_lines)
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.2)
            monitor.stop()

            events = monitor.get_events()

            assert len(events) == 2
            assert events[0].x == 0x64   # 100
            assert events[0].y == 0xc8   # 200
            assert events[1].x == 0x1f4  # 500
            assert events[1].y == 0x3e8  # 1000


class TestTouchMonitorClearEvents:
    """Test clear_events functionality."""

    def test_clear_events_removes_all(self):
        """clear_events should remove all captured events."""
        monitor = TouchMonitor("test-device")

        # Manually add events for testing
        monitor._events.append(
            TouchEvent(timestamp=1.0, x=100, y=200, event_type="tap")
        )
        monitor._events.append(
            TouchEvent(timestamp=2.0, x=300, y=400, event_type="tap")
        )

        assert len(monitor.get_events()) == 2

        monitor.clear_events()

        assert len(monitor.get_events()) == 0

    def test_clear_events_when_empty(self):
        """clear_events should be safe when already empty."""
        monitor = TouchMonitor("test-device")

        # Should not raise
        monitor.clear_events()

        assert len(monitor.get_events()) == 0


class TestTouchMonitorThreadSafety:
    """Test thread safety of event access."""

    def test_get_events_returns_copy(self):
        """get_events should return a copy, not the internal list."""
        monitor = TouchMonitor("test-device")

        monitor._events.append(
            TouchEvent(timestamp=1.0, x=100, y=200, event_type="tap")
        )

        events1 = monitor.get_events()
        events2 = monitor.get_events()

        # Should be different list objects
        assert events1 is not events2
        assert events1 is not monitor._events

    def test_modifying_returned_list_doesnt_affect_internal(self):
        """Modifying returned list should not affect internal state."""
        monitor = TouchMonitor("test-device")

        monitor._events.append(
            TouchEvent(timestamp=1.0, x=100, y=200, event_type="tap")
        )

        events = monitor.get_events()
        events.clear()

        # Internal list should still have the event
        assert len(monitor.get_events()) == 1
