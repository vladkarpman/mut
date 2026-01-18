"""Tests for ADB state monitor."""

import time
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.adb_state_monitor import ADBStateMonitor


class TestADBStateMonitor:
    """Tests for ADBStateMonitor class."""

    def test_init(self):
        """Test monitor initialization."""
        monitor = ADBStateMonitor("test-device")
        assert monitor._device_id == "test-device"
        assert not monitor.is_running

    @patch("subprocess.run")
    def test_poll_keyboard_visibility(self, mock_run):
        """Test keyboard visibility polling."""
        mock_run.return_value = MagicMock(
            stdout="mInputShown=true\n",
            returncode=0,
        )
        monitor = ADBStateMonitor("test-device")
        visible = monitor._poll_keyboard()
        assert visible is True

    @patch("subprocess.run")
    def test_poll_keyboard_not_visible(self, mock_run):
        """Test keyboard not visible."""
        mock_run.return_value = MagicMock(
            stdout="mInputShown=false\n",
            returncode=0,
        )
        monitor = ADBStateMonitor("test-device")
        visible = monitor._poll_keyboard()
        assert visible is False

    @patch("subprocess.run")
    def test_poll_activity(self, mock_run):
        """Test activity polling."""
        mock_run.return_value = MagicMock(
            stdout="topResumedActivity=ActivityRecord{abc u0 com.example.app/.MainActivity}\n",
            returncode=0,
        )
        monitor = ADBStateMonitor("test-device")
        activity = monitor._poll_activity()
        assert activity == "com.example.app/.MainActivity"

    @patch("subprocess.run")
    def test_poll_windows(self, mock_run):
        """Test visible windows polling."""
        mock_run.return_value = MagicMock(
            stdout="Window #0 Window{abc Dialog}\n  isOnScreen=true\n",
            returncode=0,
        )
        monitor = ADBStateMonitor("test-device")
        windows = monitor._poll_windows()
        assert "Dialog" in windows[0]

    def test_get_keyboard_state_at_timestamp(self):
        """Test getting keyboard state at specific timestamp."""
        monitor = ADBStateMonitor("test-device")
        # Simulate recorded states
        monitor._keyboard_states = [
            (0.0, False),
            (0.5, True),
            (1.0, True),
            (1.5, False),
        ]
        assert monitor.get_keyboard_state_at(0.3) is False
        assert monitor.get_keyboard_state_at(0.7) is True
        assert monitor.get_keyboard_state_at(1.3) is True
        assert monitor.get_keyboard_state_at(2.0) is False
