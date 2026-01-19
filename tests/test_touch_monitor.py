"""Tests for TouchMonitor."""

import time
from unittest.mock import MagicMock, patch

from mutcli.core.touch_monitor import TouchEvent, TouchMonitor, TrajectoryPoint


def make_event(
    timestamp=1.0,
    x=100,
    y=200,
    gesture="tap",
    duration_ms=50,
    start_x=100,
    start_y=200,
    trajectory=None,
    path_distance=0.0,
):
    """Helper to create TouchEvent with defaults."""
    return TouchEvent(
        timestamp=timestamp,
        x=x,
        y=y,
        gesture=gesture,
        duration_ms=duration_ms,
        start_x=start_x,
        start_y=start_y,
        trajectory=trajectory or [],
        path_distance=path_distance,
    )


class TestTouchEvent:
    """Test TouchEvent dataclass."""

    def test_creation(self):
        """TouchEvent should store all fields correctly."""
        event = make_event(
            timestamp=1.5,
            x=540,
            y=1200,
            gesture="tap",
            duration_ms=100,
        )

        assert event.timestamp == 1.5
        assert event.x == 540
        assert event.y == 1200
        assert event.gesture == "tap"
        assert event.duration_ms == 100

    def test_to_dict_tap(self):
        """to_dict for tap should return core fields."""
        event = make_event(
            timestamp=2.5,
            x=100,
            y=200,
            gesture="tap",
            duration_ms=50,
            path_distance=10.5,
        )

        result = event.to_dict()

        assert result["timestamp"] == 2.5
        assert result["x"] == 100
        assert result["y"] == 200
        assert result["gesture"] == "tap"
        assert result["duration_ms"] == 50
        assert result["path_distance"] == 10.5
        assert "trajectory" not in result  # Not included for taps

    def test_to_dict_swipe_includes_trajectory(self):
        """to_dict for swipe should include trajectory."""
        trajectory = [
            TrajectoryPoint(0.0, 100, 200),
            TrajectoryPoint(0.1, 150, 250),
            TrajectoryPoint(0.2, 200, 300),
        ]
        event = make_event(
            gesture="swipe",
            trajectory=trajectory,
            path_distance=150.0,
        )

        result = event.to_dict()

        assert result["gesture"] == "swipe"
        assert "trajectory" in result
        assert len(result["trajectory"]) == 3
        assert result["trajectory"][0] == {"t": 0.0, "x": 100, "y": 200}

    def test_to_dict_returns_new_dict(self):
        """to_dict should return a new dict each time."""
        event = make_event()

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
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor"):
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

    def test_start_returns_false_on_device_info_failure(self):
        """start() should return False if device info fails."""
        with patch.object(TouchMonitor, "_get_device_info", return_value=False):
            monitor = TouchMonitor("test-device")
            result = monitor.start()

            assert result is False
            assert monitor.is_running is False

    def test_start_returns_false_on_process_error(self):
        """start() should return False if subprocess fails."""
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True):
            mock_popen.side_effect = OSError("adb not found")

            monitor = TouchMonitor("test-device")
            result = monitor.start()

            assert result is False
            assert monitor.is_running is False

    def test_stop_clears_running_state(self):
        """stop() should set is_running to False."""
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor"):
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
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor"):
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


class TestGestureClassification:
    """Test gesture classification logic."""

    def test_classify_tap(self):
        """Short duration + small distance = tap."""
        monitor = TouchMonitor("test-device")
        gesture = monitor._classify_gesture(duration_ms=100, path_distance=20)
        assert gesture == "tap"

    def test_classify_long_press(self):
        """Long duration + small distance = long_press."""
        monitor = TouchMonitor("test-device")
        gesture = monitor._classify_gesture(duration_ms=600, path_distance=30)
        assert gesture == "long_press"

    def test_classify_swipe(self):
        """Large distance = swipe (regardless of duration)."""
        monitor = TouchMonitor("test-device")
        gesture = monitor._classify_gesture(duration_ms=100, path_distance=150)
        assert gesture == "swipe"

    def test_swipe_takes_priority_over_long_press(self):
        """Swipe classification takes priority even with long duration."""
        monitor = TouchMonitor("test-device")
        gesture = monitor._classify_gesture(duration_ms=1000, path_distance=200)
        assert gesture == "swipe"

    def test_ambiguous_defaults_to_tap(self):
        """Ambiguous cases default to tap."""
        monitor = TouchMonitor("test-device")
        # 300ms duration, 60px distance - between thresholds
        gesture = monitor._classify_gesture(duration_ms=300, path_distance=60)
        assert gesture == "tap"


class TestPathDistanceCalculation:
    """Test path distance calculation from trajectory."""

    def test_empty_trajectory(self):
        """Empty trajectory should return 0."""
        monitor = TouchMonitor("test-device")
        distance = monitor._calculate_path_distance([])
        assert distance == 0.0

    def test_single_point(self):
        """Single point trajectory should return 0."""
        monitor = TouchMonitor("test-device")
        trajectory = [TrajectoryPoint(0.0, 100, 200)]
        distance = monitor._calculate_path_distance(trajectory)
        assert distance == 0.0

    def test_straight_line(self):
        """Straight line should calculate correct distance."""
        monitor = TouchMonitor("test-device")
        trajectory = [
            TrajectoryPoint(0.0, 0, 0),
            TrajectoryPoint(0.1, 100, 0),  # 100px right
        ]
        distance = monitor._calculate_path_distance(trajectory)
        assert distance == 100.0

    def test_diagonal_line(self):
        """Diagonal should use Pythagorean theorem."""
        monitor = TouchMonitor("test-device")
        trajectory = [
            TrajectoryPoint(0.0, 0, 0),
            TrajectoryPoint(0.1, 30, 40),  # 3-4-5 triangle = 50px
        ]
        distance = monitor._calculate_path_distance(trajectory)
        assert distance == 50.0

    def test_multi_segment_path(self):
        """Multi-segment path should sum all segments."""
        monitor = TouchMonitor("test-device")
        trajectory = [
            TrajectoryPoint(0.0, 0, 0),
            TrajectoryPoint(0.1, 100, 0),    # 100px right
            TrajectoryPoint(0.2, 100, 100),  # 100px down
            TrajectoryPoint(0.3, 0, 100),    # 100px left
        ]
        distance = monitor._calculate_path_distance(trajectory)
        assert distance == 300.0

    def test_curved_path_back_to_start(self):
        """Path returning to start should still measure full distance."""
        monitor = TouchMonitor("test-device")
        # Square path returning to origin
        trajectory = [
            TrajectoryPoint(0.0, 0, 0),
            TrajectoryPoint(0.1, 100, 0),
            TrajectoryPoint(0.2, 100, 100),
            TrajectoryPoint(0.3, 0, 100),
            TrajectoryPoint(0.4, 0, 0),  # Back to start
        ]
        distance = monitor._calculate_path_distance(trajectory)
        assert distance == 400.0  # Full perimeter, not 0


class TestCoordinateConversion:
    """Test raw touch coordinate to screen pixel conversion."""

    def test_converts_min_to_zero(self):
        """Touch at min value should map to screen coordinate 0."""
        monitor = TouchMonitor("test-device")
        monitor._touch_min_x = 0
        monitor._touch_min_y = 0
        monitor._touch_max_x = 4095
        monitor._touch_max_y = 4095
        monitor._screen_width = 1080
        monitor._screen_height = 2340

        screen_x, screen_y = monitor._raw_to_screen(0, 0)
        assert screen_x == 0
        assert screen_y == 0

    def test_converts_max_to_screen_max(self):
        """Touch at max value should map to screen max (size - 1)."""
        monitor = TouchMonitor("test-device")
        monitor._touch_min_x = 0
        monitor._touch_min_y = 0
        monitor._touch_max_x = 4095
        monitor._touch_max_y = 4095
        monitor._screen_width = 1080
        monitor._screen_height = 2340

        screen_x, screen_y = monitor._raw_to_screen(4095, 4095)
        assert screen_x == 1079  # width - 1
        assert screen_y == 2339  # height - 1

    def test_converts_center_correctly(self):
        """Touch at center should map to screen center."""
        monitor = TouchMonitor("test-device")
        monitor._touch_min_x = 0
        monitor._touch_min_y = 0
        monitor._touch_max_x = 4095
        monitor._touch_max_y = 4095
        monitor._screen_width = 1080
        monitor._screen_height = 2340

        # Midpoint of touch range
        screen_x, screen_y = monitor._raw_to_screen(2047, 2047)
        # Should be close to center
        assert 535 <= screen_x <= 545  # ~540
        assert 1165 <= screen_y <= 1175  # ~1170

    def test_handles_non_zero_min(self):
        """Should handle devices with non-zero min values."""
        monitor = TouchMonitor("test-device")
        monitor._touch_min_x = 100
        monitor._touch_min_y = 200
        monitor._touch_max_x = 4195
        monitor._touch_max_y = 4295
        monitor._screen_width = 1080
        monitor._screen_height = 2340

        # At min should be 0
        screen_x, screen_y = monitor._raw_to_screen(100, 200)
        assert screen_x == 0
        assert screen_y == 0

        # At max should be screen max
        screen_x, screen_y = monitor._raw_to_screen(4195, 4295)
        assert screen_x == 1079
        assert screen_y == 2339

    def test_clamps_out_of_range_values(self):
        """Should clamp values outside touch range to screen bounds."""
        monitor = TouchMonitor("test-device")
        monitor._touch_min_x = 0
        monitor._touch_min_y = 0
        monitor._touch_max_x = 4095
        monitor._touch_max_y = 4095
        monitor._screen_width = 1080
        monitor._screen_height = 2340

        # Value beyond max should clamp to screen max
        screen_x, screen_y = monitor._raw_to_screen(5000, 5000)
        assert screen_x == 1079
        assert screen_y == 2339

        # Negative value should clamp to 0
        screen_x, screen_y = monitor._raw_to_screen(-100, -100)
        assert screen_x == 0
        assert screen_y == 0

    def test_returns_raw_when_not_initialized(self):
        """Should return raw values when device info not available."""
        monitor = TouchMonitor("test-device")
        # Don't set any calibration values

        screen_x, screen_y = monitor._raw_to_screen(500, 600)
        assert screen_x == 500
        assert screen_y == 600


class TestTouchMonitorEventParsing:
    """Test getevent line parsing."""

    def test_ignores_non_touch_events(self):
        """Should ignore non-touch events."""
        getevent_lines = [
            "[   123.456789] /dev/input/event5: EV_KEY KEY_VOLUMEDOWN DOWN",
            "[   123.456790] /dev/input/event5: EV_SYN SYN_REPORT 00000000",
            "[   123.556789] /dev/input/event5: EV_KEY KEY_VOLUMEDOWN UP",
        ]

        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor"):
            mock_process = MagicMock()
            mock_process.stdout = iter(getevent_lines)
            mock_popen.return_value = mock_process

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.2)
            monitor.stop()

            events = monitor.get_events()

            assert len(events) == 0


class TestTouchMonitorClearEvents:
    """Test clear_events functionality."""

    def test_clear_events_removes_all(self):
        """clear_events should remove all captured events."""
        monitor = TouchMonitor("test-device")

        # Manually add events for testing
        monitor._events.append(make_event(timestamp=1.0, x=100, y=200))
        monitor._events.append(make_event(timestamp=2.0, x=300, y=400))

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

        monitor._events.append(make_event(timestamp=1.0, x=100, y=200))

        events1 = monitor.get_events()
        events2 = monitor.get_events()

        # Should be different list objects
        assert events1 is not events2
        assert events1 is not monitor._events

    def test_modifying_returned_list_doesnt_affect_internal(self):
        """Modifying returned list should not affect internal state."""
        monitor = TouchMonitor("test-device")

        monitor._events.append(make_event(timestamp=1.0, x=100, y=200))

        events = monitor.get_events()
        events.clear()

        # Internal list should still have the event
        assert len(monitor.get_events()) == 1


class TestTouchMonitorADBStateIntegration:
    """Test ADB state monitor integration."""

    def test_touch_monitor_has_adb_state_monitor_attribute(self):
        """TouchMonitor should have ADB state monitor attribute."""
        monitor = TouchMonitor("test-device")

        assert hasattr(monitor, "_adb_state_monitor")
        assert monitor._adb_state_monitor is None  # Not started yet

    def test_has_state_getter_methods(self):
        """TouchMonitor should have ADB state getter methods."""
        monitor = TouchMonitor("test-device")

        assert hasattr(monitor, "get_keyboard_states")
        assert hasattr(monitor, "get_activity_states")
        assert hasattr(monitor, "get_window_states")
        assert hasattr(monitor, "get_adb_state_at")

    def test_get_keyboard_states_returns_list_when_not_started(self):
        """get_keyboard_states should return empty list when monitor not started."""
        monitor = TouchMonitor("test-device")

        states = monitor.get_keyboard_states()

        assert isinstance(states, list)
        assert states == []

    def test_get_activity_states_returns_list_when_not_started(self):
        """get_activity_states should return empty list when monitor not started."""
        monitor = TouchMonitor("test-device")

        states = monitor.get_activity_states()

        assert isinstance(states, list)
        assert states == []

    def test_get_window_states_returns_list_when_not_started(self):
        """get_window_states should return empty list when monitor not started."""
        monitor = TouchMonitor("test-device")

        states = monitor.get_window_states()

        assert isinstance(states, list)
        assert states == []

    def test_get_adb_state_at_returns_empty_dict_when_not_started(self):
        """get_adb_state_at should return empty dict when monitor not started."""
        monitor = TouchMonitor("test-device")

        state = monitor.get_adb_state_at(1.0)

        assert isinstance(state, dict)
        assert state == {}

    def test_start_creates_adb_state_monitor(self):
        """start() should create and start ADB state monitor."""
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor") as mock_adb_monitor_class:
            mock_process = MagicMock()
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            mock_adb_monitor = MagicMock()
            mock_adb_monitor_class.return_value = mock_adb_monitor

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.1)

            # Verify ADB state monitor was created and started
            mock_adb_monitor_class.assert_called_once_with("test-device")
            mock_adb_monitor.start.assert_called_once()

            monitor.stop()

    def test_stop_stops_adb_state_monitor(self):
        """stop() should stop ADB state monitor."""
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(TouchMonitor, "_get_device_info", return_value=True), \
             patch("mutcli.core.touch_monitor.ADBStateMonitor") as mock_adb_monitor_class:
            mock_process = MagicMock()
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            mock_adb_monitor = MagicMock()
            mock_adb_monitor_class.return_value = mock_adb_monitor

            monitor = TouchMonitor("test-device")
            monitor.start()
            time.sleep(0.1)
            monitor.stop()

            # Verify ADB state monitor was stopped
            mock_adb_monitor.stop.assert_called_once()

    def test_get_adb_state_at_delegates_to_monitor(self):
        """get_adb_state_at should delegate to ADB state monitor."""
        monitor = TouchMonitor("test-device")

        # Manually set up a mock ADB state monitor
        mock_adb_monitor = MagicMock()
        mock_adb_monitor.get_keyboard_state_at.return_value = True
        mock_adb_monitor.get_activity_state_at.return_value = "com.example/.MainActivity"
        mock_adb_monitor.get_windows_state_at.return_value = ["StatusBar", "MainActivity"]
        monitor._adb_state_monitor = mock_adb_monitor

        state = monitor.get_adb_state_at(5.0)

        assert state["keyboard_visible"] is True
        assert state["activity"] == "com.example/.MainActivity"
        assert state["windows"] == ["StatusBar", "MainActivity"]
        mock_adb_monitor.get_keyboard_state_at.assert_called_once_with(5.0)
        mock_adb_monitor.get_activity_state_at.assert_called_once_with(5.0)
        mock_adb_monitor.get_windows_state_at.assert_called_once_with(5.0)
