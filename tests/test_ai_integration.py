"""Integration tests for AIAnalyzer with real Gemini API.

These tests require GOOGLE_API_KEY to be set and will be skipped otherwise.
They also require a connected Android device for screenshot capture.
"""

import os

import pytest

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.device_controller import DeviceController
from mutcli.core.scrcpy_service import ScrcpyService


@pytest.fixture
def api_key():
    """Get API key from environment."""
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        pytest.skip("GOOGLE_API_KEY not set")
    return key


@pytest.fixture
def device_id():
    """Get first available device ID."""
    devices = DeviceController.list_devices()
    if not devices:
        pytest.skip("No Android device connected")
    return devices[0]["id"]


class TestAIIntegration:
    """Integration tests with real Gemini API."""

    def test_verify_screen_with_real_screenshot(self, api_key, device_id):
        """Test verify_screen with actual device screenshot."""
        # Connect to device
        scrcpy = ScrcpyService(device_id)
        scrcpy.connect()

        try:
            import time
            time.sleep(1)  # Wait for frames

            # Take screenshot
            screenshot = scrcpy.screenshot()

            # Create analyzer
            analyzer = AIAnalyzer(api_key=api_key)

            # Verify something generic that should be true
            result = analyzer.verify_screen(screenshot, "a mobile app screen")

            assert "pass" in result
            assert "reason" in result
            assert isinstance(result["pass"], bool)

        finally:
            scrcpy.disconnect()

    def test_if_screen_returns_boolean(self, api_key, device_id):
        """Test if_screen returns boolean with real API."""
        scrcpy = ScrcpyService(device_id)
        scrcpy.connect()

        try:
            import time
            time.sleep(1)

            screenshot = scrcpy.screenshot()
            analyzer = AIAnalyzer(api_key=api_key)

            result = analyzer.if_screen(screenshot, "any content visible")

            assert isinstance(result, bool)

        finally:
            scrcpy.disconnect()
