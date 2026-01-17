"""Tests for Recorder session management."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.recorder import Recorder, RecordingState


class TestRecordingState:
    """Test RecordingState dataclass."""

    def test_creation(self):
        """RecordingState should store all fields correctly."""
        state = RecordingState(
            name="my-test",
            device_id="emulator-5554",
            output_dir=Path("/tmp/tests/my-test"),
            start_time=1234567890.123,
        )

        assert state.name == "my-test"
        assert state.device_id == "emulator-5554"
        assert state.output_dir == Path("/tmp/tests/my-test")
        assert state.start_time == 1234567890.123

    def test_save_creates_json_file(self):
        """save() should create a JSON file with state data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            state = RecordingState(
                name="test-recording",
                device_id="device-123",
                output_dir=Path("/tmp/tests/test-recording"),
                start_time=1000.5,
            )

            state.save(state_file)

            assert state_file.exists()

            with open(state_file) as f:
                data = json.load(f)

            assert data["name"] == "test-recording"
            assert data["device_id"] == "device-123"
            assert data["output_dir"] == "/tmp/tests/test-recording"
            assert data["start_time"] == 1000.5

    def test_save_creates_parent_directories(self):
        """save() should create parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "nested" / "dir" / "state.json"

            state = RecordingState(
                name="test",
                device_id="device",
                output_dir=Path("/tmp/test"),
                start_time=0,
            )

            state.save(state_file)

            assert state_file.exists()

    def test_load_restores_state(self):
        """load() should restore state from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            original = RecordingState(
                name="loaded-test",
                device_id="my-device",
                output_dir=Path("/path/to/output"),
                start_time=9999.99,
            )
            original.save(state_file)

            loaded = RecordingState.load(state_file)

            assert loaded.name == original.name
            assert loaded.device_id == original.device_id
            assert loaded.output_dir == original.output_dir
            assert loaded.start_time == original.start_time

    def test_load_raises_on_missing_file(self):
        """load() should raise FileNotFoundError if file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            RecordingState.load(Path("/nonexistent/path/state.json"))


class TestRecorderInitialization:
    """Test Recorder initialization."""

    def test_is_recording_false_initially(self):
        """is_recording should be False before start()."""
        recorder = Recorder(
            name="test",
            device_id="fake-device",
        )

        assert recorder.is_recording is False

    def test_output_dir_defaults_to_tests_name(self):
        """output_dir should default to tests/{name}/."""
        recorder = Recorder(
            name="my-test",
            device_id="fake-device",
        )

        assert recorder.output_dir == Path("tests/my-test")

    def test_output_dir_custom(self):
        """output_dir should use provided value."""
        custom_dir = Path("/custom/output/dir")
        recorder = Recorder(
            name="test",
            device_id="fake-device",
            output_dir=custom_dir,
        )

        assert recorder.output_dir == custom_dir


class TestRecorderStart:
    """Test Recorder start() method."""

    def test_start_creates_output_directory(self):
        """start() should create output directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "new-test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = True
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="new-test",
                        device_id="fake-device",
                        output_dir=output_dir,
                    )

                    result = recorder.start()

                    assert result["success"] is True
                    assert output_dir.exists()
                    assert (output_dir / "recording").exists()

    def test_start_connects_scrcpy_service(self):
        """start() should connect ScrcpyService."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = True
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="test",
                        device_id="test-device",
                        output_dir=output_dir,
                    )

                    recorder.start()

                    mock_scrcpy_cls.assert_called_once_with("test-device")
                    mock_scrcpy.connect.assert_called_once()

    def test_start_starts_video_recording(self):
        """start() should start video recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = True
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="test",
                        device_id="test-device",
                        output_dir=output_dir,
                    )

                    recorder.start()

                    expected_video_path = str(output_dir / "recording" / "recording.mp4")
                    mock_scrcpy.start_recording.assert_called_once_with(expected_video_path)

    def test_start_starts_touch_monitor(self):
        """start() should start TouchMonitor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = True
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="test",
                        device_id="test-device",
                        output_dir=output_dir,
                    )

                    recorder.start()

                    mock_touch_cls.assert_called_once_with("test-device")
                    mock_touch.start.assert_called_once()

    def test_start_saves_state_file(self):
        """start() should save state to .claude/recording-state.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()

                        assert state_file.exists()

                        with open(state_file) as f:
                            data = json.load(f)

                        assert data["name"] == "test"
                        assert data["device_id"] == "test-device"

    def test_start_sets_is_recording_true(self):
        """start() should set is_recording to True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = True
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="test",
                        device_id="test-device",
                        output_dir=output_dir,
                    )

                    recorder.start()

                    assert recorder.is_recording is True

    def test_start_returns_error_on_scrcpy_connect_failure(self):
        """start() should return error if ScrcpyService fails to connect."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                mock_scrcpy = MagicMock()
                mock_scrcpy.connect.return_value = False
                mock_scrcpy_cls.return_value = mock_scrcpy

                recorder = Recorder(
                    name="test",
                    device_id="bad-device",
                    output_dir=output_dir,
                )

                result = recorder.start()

                assert result["success"] is False
                assert "connect" in result["error"].lower()
                assert recorder.is_recording is False

    def test_start_returns_error_on_touch_monitor_failure(self):
        """start() should return error if TouchMonitor fails to start."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    mock_scrcpy = MagicMock()
                    mock_scrcpy.connect.return_value = True
                    mock_scrcpy.start_recording.return_value = {
                        "success": True,
                        "recording_start_time": time.time(),
                    }
                    mock_scrcpy_cls.return_value = mock_scrcpy

                    mock_touch = MagicMock()
                    mock_touch.start.return_value = False
                    mock_touch_cls.return_value = mock_touch

                    recorder = Recorder(
                        name="test",
                        device_id="test-device",
                        output_dir=output_dir,
                    )

                    result = recorder.start()

                    assert result["success"] is False
                    assert "touch" in result["error"].lower()


class TestRecorderStop:
    """Test Recorder stop() method."""

    def test_stop_saves_touch_events_json(self):
        """stop() should save touch events to touch_events.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {
                            "success": True,
                            "duration_seconds": 5.0,
                        }
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        # Create mock touch events
                        from mutcli.core.touch_monitor import TouchEvent

                        mock_events = [
                            TouchEvent(timestamp=1.0, x=100, y=200, event_type="tap"),
                            TouchEvent(timestamp=2.5, x=300, y=400, event_type="tap"),
                        ]

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = mock_events
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        recorder.stop()

                        touch_events_file = output_dir / "recording" / "touch_events.json"
                        assert touch_events_file.exists()

                        with open(touch_events_file) as f:
                            events_data = json.load(f)

                        assert len(events_data) == 2
                        assert events_data[0]["x"] == 100
                        assert events_data[0]["y"] == 200
                        assert events_data[1]["timestamp"] == 2.5

    def test_stop_returns_results_with_event_count(self):
        """stop() should return results dict with event count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {
                            "success": True,
                            "duration_seconds": 10.0,
                            "output_path": str(output_dir / "recording" / "recording.mp4"),
                        }
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        from mutcli.core.touch_monitor import TouchEvent

                        mock_events = [
                            TouchEvent(timestamp=1.0, x=100, y=200, event_type="tap"),
                            TouchEvent(timestamp=2.0, x=150, y=250, event_type="tap"),
                            TouchEvent(timestamp=3.0, x=200, y=300, event_type="tap"),
                        ]

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = mock_events
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        result = recorder.stop()

                        assert result["success"] is True
                        assert result["event_count"] == 3
                        assert result["duration_seconds"] == 10.0

    def test_stop_stops_touch_monitor(self):
        """stop() should stop TouchMonitor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {"success": True}
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = []
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        recorder.stop()

                        mock_touch.stop.assert_called_once()

    def test_stop_stops_scrcpy_recording(self):
        """stop() should stop ScrcpyService recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {"success": True}
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = []
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        recorder.stop()

                        mock_scrcpy.stop_recording.assert_called_once()

    def test_stop_cleans_up_state_file(self):
        """stop() should delete the state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {"success": True}
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = []
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        assert state_file.exists()

                        recorder.stop()
                        assert not state_file.exists()

    def test_stop_sets_is_recording_false(self):
        """stop() should set is_recording to False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "tests" / "test"
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch("mutcli.core.recorder.ScrcpyService") as mock_scrcpy_cls:
                with patch("mutcli.core.recorder.TouchMonitor") as mock_touch_cls:
                    with patch.object(Recorder, "STATE_FILE", state_file):
                        mock_scrcpy = MagicMock()
                        mock_scrcpy.connect.return_value = True
                        mock_scrcpy.start_recording.return_value = {
                            "success": True,
                            "recording_start_time": time.time(),
                        }
                        mock_scrcpy.stop_recording.return_value = {"success": True}
                        mock_scrcpy_cls.return_value = mock_scrcpy

                        mock_touch = MagicMock()
                        mock_touch.start.return_value = True
                        mock_touch.get_events.return_value = []
                        mock_touch_cls.return_value = mock_touch

                        recorder = Recorder(
                            name="test",
                            device_id="test-device",
                            output_dir=output_dir,
                        )

                        recorder.start()
                        assert recorder.is_recording is True

                        recorder.stop()
                        assert recorder.is_recording is False

    def test_stop_returns_error_when_not_recording(self):
        """stop() should return error if not currently recording."""
        recorder = Recorder(
            name="test",
            device_id="fake-device",
        )

        result = recorder.stop()

        assert result["success"] is False
        assert "not recording" in result["error"].lower()


class TestRecorderLoadActive:
    """Test Recorder.load_active() class method."""

    def test_load_active_returns_none_if_no_state_file(self):
        """load_active() should return None if state file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"

            with patch.object(Recorder, "STATE_FILE", state_file):
                result = Recorder.load_active()

                assert result is None

    def test_load_active_returns_recorder_if_state_exists(self):
        """load_active() should return Recorder if state file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"
            output_dir = Path(tmpdir) / "tests" / "restored-test"

            # Create state file
            state = RecordingState(
                name="restored-test",
                device_id="restored-device",
                output_dir=output_dir,
                start_time=1234567890.0,
            )
            state.save(state_file)

            with patch.object(Recorder, "STATE_FILE", state_file):
                with patch("mutcli.core.recorder.ScrcpyService"):
                    with patch("mutcli.core.recorder.TouchMonitor"):
                        recorder = Recorder.load_active()

                        assert recorder is not None
                        assert recorder._name == "restored-test"
                        assert recorder._device_id == "restored-device"
                        assert recorder.output_dir == output_dir

    def test_load_active_marks_recorder_as_recording(self):
        """load_active() should return recorder with is_recording True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / ".claude" / "recording-state.json"
            output_dir = Path(tmpdir) / "tests" / "active-test"

            state = RecordingState(
                name="active-test",
                device_id="device",
                output_dir=output_dir,
                start_time=time.time(),
            )
            state.save(state_file)

            with patch.object(Recorder, "STATE_FILE", state_file):
                with patch("mutcli.core.recorder.ScrcpyService"):
                    with patch("mutcli.core.recorder.TouchMonitor"):
                        recorder = Recorder.load_active()

                        assert recorder is not None
                        assert recorder.is_recording is True
