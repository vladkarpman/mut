"""Tests for TestExecutor."""

from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.executor import StepResult, TestExecutor
from mutcli.models.test import Step, TestConfig, TestFile


class TestExecutorBasicActions:
    """Test basic action execution."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.find_element.return_value = (540, 1200)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_executes_tap_by_text(self, executor, mock_device):
        """Tap finds element by text and taps."""
        step = Step(action="tap", target="Login")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Login")
        mock_device.tap.assert_called_with(540, 1200)

    def test_executes_tap_by_coordinates_percent(self, executor, mock_device):
        """Tap at percentage coordinates."""
        step = Step(
            action="tap",
            coordinates=(50.0, 75.0),
            coordinates_type="percent",
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        # 50% of 1080 = 540, 75% of 2340 = 1755
        mock_device.tap.assert_called_with(540, 1755)

    def test_executes_type(self, executor, mock_device):
        """Type enters text."""
        step = Step(action="type", text="hello@test.com")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.type_text.assert_called_with("hello@test.com")

    def test_executes_swipe(self, executor, mock_device):
        """Swipe in direction."""
        step = Step(action="swipe", direction="up")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.swipe.assert_called()

    def test_tap_fails_when_element_not_found(self, executor, mock_device):
        """Tap fails gracefully when element not found."""
        mock_device.find_element.return_value = None
        step = Step(action="tap", target="NonExistent")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "not found" in result.error.lower()


class TestExecutorWaitActions:
    """Test wait action execution."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_executes_wait(self, executor, mock_device):
        """Wait sleeps for duration."""
        step = Step(action="wait", timeout=0.1)

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Duration should be at least 0.1s
        assert result.duration >= 0.1

    def test_wait_for_succeeds_when_element_found(self, executor, mock_device):
        """wait_for succeeds when element appears."""
        mock_device.find_element.return_value = (540, 1200)
        step = Step(action="wait_for", target="Loading complete", timeout=1.0)

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Loading complete")

    def test_wait_for_fails_on_timeout(self, executor, mock_device):
        """wait_for fails when element doesn't appear within timeout."""
        mock_device.find_element.return_value = None
        step = Step(action="wait_for", target="Never appears", timeout=0.2)

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "timeout" in result.error.lower()


class TestExecutorAppActions:
    """Test app lifecycle actions."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            exec = TestExecutor(device_id="test-device")
            exec._config.app = "com.example.app"
            return exec

    def test_launch_app(self, executor, mock_device):
        """launch_app calls device launch."""
        step = Step(action="launch_app", target="com.example.app")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.launch_app.assert_called_with("com.example.app")

    def test_launch_app_uses_config_default(self, executor, mock_device):
        """launch_app uses config.app when no target specified."""
        step = Step(action="launch_app")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.launch_app.assert_called_with("com.example.app")

    def test_terminate_app(self, executor, mock_device):
        """terminate_app calls device terminate."""
        step = Step(action="terminate_app", target="com.example.app")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.terminate_app.assert_called_with("com.example.app")

    def test_back_button(self, executor, mock_device):
        """back presses back key."""
        step = Step(action="back")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.press_key.assert_called_with("BACK")


class TestExecutorCoordinateResolution:
    """Test coordinate resolution logic with AI-first approach."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.take_screenshot.return_value = b"fake_screenshot_bytes"
        return device

    @pytest.fixture
    def mock_ai(self):
        """Mock AIAnalyzer."""
        ai = MagicMock()
        ai.is_available = True
        ai.find_element.return_value = None  # Default: AI doesn't find element
        ai.validate_element_at.return_value = {"valid": True, "reason": "Found button"}
        return ai

    @pytest.fixture
    def executor(self, mock_device, mock_ai):
        """Create executor with mocked device and AI."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            with patch("mutcli.core.executor.AIAnalyzer", return_value=mock_ai):
                return TestExecutor(device_id="test-device")

    def test_tap_by_pixel_coordinates(self, executor, mock_device):
        """Tap at pixel coordinates (no text = no AI needed)."""
        step = Step(
            action="tap",
            coordinates=(100.0, 200.0),
            coordinates_type="pixels",
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.tap.assert_called_with(100, 200)

    def test_text_and_coordinates_validates_with_ai(self, executor, mock_device, mock_ai):
        """When both text and coordinates specified, AI validates then uses coordinates."""
        mock_ai.validate_element_at.return_value = {"valid": True, "reason": "Button found"}
        step = Step(
            action="tap",
            target="Button",
            coordinates=(50.0, 80.0),
            coordinates_type="percent",
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_ai.validate_element_at.assert_called_once()
        # Uses validated coordinates (50% of 1080 = 540, 80% of 2340 = 1872)
        mock_device.tap.assert_called_with(540, 1872)

    def test_text_only_uses_device_finder_first(self, executor, mock_device, mock_ai):
        """Text only: tries device finder first (faster than AI)."""
        mock_device.find_element.return_value = (540, 1200)
        step = Step(
            action="tap",
            target="Button",
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Button")
        mock_device.tap.assert_called_with(540, 1200)
        # AI finder not called since device finder succeeded
        mock_ai.find_element.assert_not_called()

    def test_text_only_falls_back_to_ai_finder(self, executor, mock_device, mock_ai):
        """Text only: falls back to AI vision when device finder fails."""
        mock_device.find_element.return_value = None
        mock_ai.find_element.return_value = (540, 1200)
        step = Step(
            action="tap",
            target="Button",
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Button")
        mock_ai.find_element.assert_called_once()
        mock_device.tap.assert_called_with(540, 1200)

    def test_text_only_fails_when_not_found(self, executor, mock_device, mock_ai):
        """Text only: fails when neither device nor AI finds element."""
        mock_device.find_element.return_value = None
        mock_ai.find_element.return_value = None
        step = Step(
            action="tap",
            target="Button",
        )

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "not found" in result.error.lower()


class TestExecutorSwipeActions:
    """Test swipe action variations."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_swipe_up(self, executor, mock_device):
        """Swipe up from center."""
        step = Step(action="swipe", direction="up")

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Should swipe from center upward
        args = mock_device.swipe.call_args[0]
        assert args[1] > args[3]  # y1 > y2 for up swipe

    def test_swipe_down(self, executor, mock_device):
        """Swipe down from center."""
        step = Step(action="swipe", direction="down")

        result = executor.execute_step(step)

        assert result.status == "passed"
        args = mock_device.swipe.call_args[0]
        assert args[1] < args[3]  # y1 < y2 for down swipe

    def test_swipe_left(self, executor, mock_device):
        """Swipe left from center."""
        step = Step(action="swipe", direction="left")

        result = executor.execute_step(step)

        assert result.status == "passed"
        args = mock_device.swipe.call_args[0]
        assert args[0] > args[2]  # x1 > x2 for left swipe

    def test_swipe_right(self, executor, mock_device):
        """Swipe right from center."""
        step = Step(action="swipe", direction="right")

        result = executor.execute_step(step)

        assert result.status == "passed"
        args = mock_device.swipe.call_args[0]
        assert args[0] < args[2]  # x1 < x2 for right swipe

    def test_swipe_with_custom_distance(self, executor, mock_device):
        """Swipe with custom distance percentage."""
        step = Step(action="swipe", direction="up", distance=50.0)

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.swipe.assert_called()


class TestExecutorErrorHandling:
    """Test error handling in executor."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_unknown_action_fails(self, executor):
        """Unknown action returns failed result."""
        step = Step(action="unknown_action")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "unknown action" in result.error.lower()

    def test_device_error_is_caught(self, executor, mock_device):
        """Device errors are caught and reported."""
        mock_device.tap.side_effect = RuntimeError("Device disconnected")
        mock_device.find_element.return_value = (540, 1200)
        step = Step(action="tap", target="Button")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "disconnected" in result.error.lower()


class TestExecutorTypeAction:
    """Test type action variations."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_type_with_text_field(self, executor, mock_device):
        """Type uses text field."""
        step = Step(action="type", text="hello@test.com")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.type_text.assert_called_with("hello@test.com")

    def test_type_uses_target_as_fallback(self, executor, mock_device):
        """Type uses target when text not specified."""
        step = Step(action="type", target="fallback text")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.type_text.assert_called_with("fallback text")

    def test_type_fails_without_text(self, executor, mock_device):
        """Type fails when no text provided."""
        step = Step(action="type")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "no text" in result.error.lower()


class TestExecutorLongPressActions:
    """Test long_press action execution."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.find_element.return_value = (540, 1200)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_long_press_action(self, executor, mock_device):
        """long_press finds element by text and long presses with default duration."""
        step = Step(action="long_press", target="Hold Me")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Hold Me")
        mock_device.long_press.assert_called_with(540, 1200, 500)  # Default 500ms

    def test_long_press_with_custom_duration(self, executor, mock_device):
        """long_press respects custom duration."""
        step = Step(action="long_press", target="Hold Me", duration=2000)

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.long_press.assert_called_with(540, 1200, 2000)

    def test_long_press_element_not_found(self, executor, mock_device):
        """long_press fails when element not found."""
        mock_device.find_element.return_value = None
        step = Step(action="long_press", target="NonExistent")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "not found" in result.error.lower()

    def test_long_press_by_coordinates(self, executor, mock_device):
        """long_press works with coordinates."""
        step = Step(
            action="long_press",
            coordinates=(100.0, 200.0),
            coordinates_type="pixels",
            duration=1000,
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.long_press.assert_called_with(100, 200, 1000)


class TestExecutorScrollToActions:
    """Test scroll_to action execution."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_scroll_to_finds_element_immediately(self, executor, mock_device):
        """scroll_to succeeds when element is already visible."""
        mock_device.find_element.return_value = (540, 1200)
        step = Step(action="scroll_to", target="Target Element")

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Target Element")
        # No swipe needed if element found immediately
        mock_device.swipe.assert_not_called()

    def test_scroll_to_finds_element_after_scrolls(self, executor, mock_device):
        """scroll_to finds element after scrolling."""
        # Element not found first 2 times, then found
        mock_device.find_element.side_effect = [None, None, (540, 1500)]
        step = Step(action="scroll_to", target="Target Element")

        result = executor.execute_step(step)

        assert result.status == "passed"
        assert mock_device.find_element.call_count == 3
        assert mock_device.swipe.call_count == 2

    def test_scroll_to_max_scrolls_exceeded(self, executor, mock_device):
        """scroll_to fails after max scroll attempts."""
        mock_device.find_element.return_value = None
        step = Step(action="scroll_to", target="Never Found", max_scrolls=5)

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "not found after 5 scrolls" in result.error.lower()
        assert mock_device.swipe.call_count == 5

    def test_scroll_to_respects_direction_down(self, executor, mock_device):
        """scroll_to scrolls down by default."""
        mock_device.find_element.side_effect = [None, (540, 1500)]
        step = Step(action="scroll_to", target="Target Element", direction="down")

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Swipe down: start_y > end_y
        args = mock_device.swipe.call_args[0]
        assert args[1] > args[3]  # cy > cy - distance

    def test_scroll_to_respects_direction_up(self, executor, mock_device):
        """scroll_to respects up direction."""
        mock_device.find_element.side_effect = [None, (540, 1500)]
        step = Step(action="scroll_to", target="Target Element", direction="up")

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Swipe up: start_y < end_y
        args = mock_device.swipe.call_args[0]
        assert args[1] < args[3]  # cy < cy + distance

    def test_scroll_to_respects_direction_left(self, executor, mock_device):
        """scroll_to respects left direction."""
        mock_device.find_element.side_effect = [None, (540, 1500)]
        step = Step(action="scroll_to", target="Target Element", direction="left")

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Swipe left: start_x < end_x
        args = mock_device.swipe.call_args[0]
        assert args[0] < args[2]  # cx < cx + distance

    def test_scroll_to_respects_direction_right(self, executor, mock_device):
        """scroll_to respects right direction."""
        mock_device.find_element.side_effect = [None, (540, 1500)]
        step = Step(action="scroll_to", target="Target Element", direction="right")

        result = executor.execute_step(step)

        assert result.status == "passed"
        # Swipe right: start_x > end_x
        args = mock_device.swipe.call_args[0]
        assert args[0] > args[2]  # cx > cx - distance

    def test_scroll_to_fails_without_target(self, executor, mock_device):
        """scroll_to fails when no element specified."""
        step = Step(action="scroll_to")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "no element specified" in result.error.lower()


class TestExecutorConditionalActions:
    """Test conditional action execution with AI-first approach."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.take_screenshot.return_value = b"fake_screenshot_bytes"
        return device

    @pytest.fixture
    def mock_ai(self):
        """Mock AIAnalyzer."""
        ai = MagicMock()
        ai.is_available = True
        ai.find_element.return_value = None  # Default: AI doesn't find element
        ai.validate_element_at.return_value = {"valid": True}
        return ai

    @pytest.fixture
    def executor(self, mock_device, mock_ai):
        """Create executor with mocked device and AI."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            with patch("mutcli.core.executor.AIAnalyzer", return_value=mock_ai):
                return TestExecutor(device_id="test-device")

    def test_if_present_executes_then_when_element_found(self, executor, mock_device, mock_ai):
        """if_present executes then branch when element is found."""
        mock_device.find_element.return_value = (540, 1200)
        then_step = Step(action="tap", target="Next Button")
        step = Step(
            action="if_present",
            condition_target="Login Button",
            then_steps=[then_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_any_call("Login Button")
        mock_device.tap.assert_called()

    def test_if_present_executes_else_when_element_not_found(self, executor, mock_device, mock_ai):
        """if_present executes else branch when element not found by device AND AI."""
        # Device finder: returns None for condition, coords for else branch tap
        mock_device.find_element.side_effect = [None, (540, 1200)]
        # AI finder: also returns None for condition check
        mock_ai.find_element.return_value = None
        then_step = Step(action="tap", target="Then Target")
        else_step = Step(action="tap", target="Else Target")
        step = Step(
            action="if_present",
            condition_target="Login Button",
            then_steps=[then_step],
            else_steps=[else_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_any_call("Login Button")

    def test_if_present_skips_when_no_else_and_not_found(self, executor, mock_device, mock_ai):
        """if_present does nothing when element not found and no else branch."""
        mock_device.find_element.return_value = None
        mock_ai.find_element.return_value = None  # AI also doesn't find
        then_step = Step(action="tap", target="Then Target")
        step = Step(
            action="if_present",
            condition_target="Login Button",
            then_steps=[then_step],
            else_steps=[],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_called_with("Login Button")
        mock_device.tap.assert_not_called()

    def test_if_absent_executes_then_when_element_not_found(self, executor, mock_device, mock_ai):
        """if_absent executes then branch when element NOT found by device AND AI."""
        # Device finder: returns None for condition, coords for then branch tap
        mock_device.find_element.side_effect = [None, (540, 1200)]
        # AI finder: also returns None for condition check
        mock_ai.find_element.return_value = None
        then_step = Step(action="tap", target="Then Target")
        step = Step(
            action="if_absent",
            condition_target="Error Message",
            then_steps=[then_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_any_call("Error Message")

    def test_if_absent_executes_else_when_element_found(self, executor, mock_device):
        """if_absent executes else branch when element IS found."""
        mock_device.find_element.return_value = (540, 1200)
        then_step = Step(action="tap", target="Then Target")
        else_step = Step(action="tap", target="Else Target")
        step = Step(
            action="if_absent",
            condition_target="Error Message",
            then_steps=[then_step],
            else_steps=[else_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_device.find_element.assert_any_call("Error Message")
        mock_device.find_element.assert_any_call("Else Target")

    def test_if_screen_executes_then_on_match(self, executor, mock_device, mock_ai):
        """if_screen executes then branch when AI confirms screen matches."""
        mock_device.take_screenshot.return_value = b"fake_screenshot_data"
        mock_ai.verify_screen.return_value = {"pass": True, "confidence": 0.95}
        mock_device.find_element.return_value = (540, 1200)
        then_step = Step(action="tap", target="Continue")
        step = Step(
            action="if_screen",
            condition_target="Login page with email field visible",
            then_steps=[then_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        # take_screenshot called for: before, if_screen, nested before/after, outer after
        assert mock_device.take_screenshot.call_count >= 1
        mock_ai.verify_screen.assert_called_once_with(
            b"fake_screenshot_data", "Login page with email field visible"
        )
        mock_device.tap.assert_called()

    def test_if_screen_executes_else_on_no_match(self, executor, mock_device, mock_ai):
        """if_screen executes else branch when AI says screen doesn't match."""
        mock_device.take_screenshot.return_value = b"fake_screenshot_data"
        mock_ai.verify_screen.return_value = {"pass": False, "confidence": 0.3}
        mock_device.find_element.return_value = (540, 1200)
        then_step = Step(action="tap", target="Then Target")
        else_step = Step(action="tap", target="Else Target")
        step = Step(
            action="if_screen",
            condition_target="Login page with email field visible",
            then_steps=[then_step],
            else_steps=[else_step],
        )

        result = executor.execute_step(step)

        assert result.status == "passed"
        mock_ai.verify_screen.assert_called_once()
        mock_device.find_element.assert_called_with("Else Target")

    def test_nested_conditionals_execute_correctly(self, executor, mock_device, mock_ai):
        """Nested conditionals execute properly with AI fallback."""
        # Outer condition: element found by device
        # Inner condition: element not found (device None, AI None)
        # Tap: element found by device
        mock_device.find_element.side_effect = [
            (540, 1200),  # Outer if_present check - found
            None,  # Inner if_absent check - not found by device
            (540, 1200),  # Tap in inner then branch
        ]
        mock_ai.find_element.return_value = None  # AI also doesn't find "Error Dialog"

        inner_then_step = Step(action="tap", target="Inner Then Target")
        inner_conditional = Step(
            action="if_absent",
            condition_target="Error Dialog",
            then_steps=[inner_then_step],
        )
        outer_step = Step(
            action="if_present",
            condition_target="Main Screen",
            then_steps=[inner_conditional],
        )

        result = executor.execute_step(outer_step)

        assert result.status == "passed"
        mock_device.find_element.assert_any_call("Main Screen")
        mock_device.tap.assert_called()

    def test_if_present_fails_without_condition_target(self, executor, mock_device):
        """if_present fails when no element specified."""
        step = Step(action="if_present", condition_target=None)

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "no element specified" in result.error.lower()

    def test_if_absent_fails_without_condition_target(self, executor, mock_device):
        """if_absent fails when no element specified."""
        step = Step(action="if_absent", condition_target=None)

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "no element specified" in result.error.lower()

    def test_if_screen_fails_without_description(self, executor, mock_device):
        """if_screen fails when no screen description specified."""
        step = Step(action="if_screen", condition_target=None)

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "no screen description" in result.error.lower()

    def test_conditional_propagates_nested_step_failure(self, executor, mock_device, mock_ai):
        """Conditional returns error when nested step fails (element not found by device or AI)."""
        mock_device.find_element.side_effect = [
            (540, 1200),  # Condition check - found
            None,  # Tap target not found by device
        ]
        mock_ai.find_element.return_value = None  # AI also doesn't find tap target
        then_step = Step(action="tap", target="NonExistent Button")
        step = Step(
            action="if_present",
            condition_target="Login Button",
            then_steps=[then_step],
        )

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert "not found" in result.error.lower()


class TestStepResult:
    """Test StepResult dataclass."""

    def test_step_result_creation(self):
        """StepResult can be created with required fields."""
        result = StepResult(
            step_number=1,
            action="tap",
            status="passed",
        )

        assert result.step_number == 1
        assert result.action == "tap"
        assert result.status == "passed"
        assert result.error is None

    def test_step_result_with_error(self):
        """StepResult can store error message."""
        result = StepResult(
            step_number=1,
            action="tap",
            status="failed",
            error="Element not found",
        )

        assert result.status == "failed"
        assert result.error == "Element not found"


class TestExecutorScreenshots:
    """Tests for screenshot capture during execution."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.find_element.return_value = (540, 1200)
        device.take_screenshot.return_value = b"fake_screenshot_bytes"
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_captures_before_screenshot(self, executor, mock_device):
        """Should capture screenshot before executing step."""
        step = Step(action="tap", target="Button")

        result = executor.execute_step(step)

        assert result.screenshot_before == b"fake_screenshot_bytes"
        # take_screenshot should be called at least once for before
        assert mock_device.take_screenshot.call_count >= 1

    def test_captures_after_screenshot(self, executor, mock_device):
        """Should capture screenshot after executing step."""
        step = Step(action="tap", target="Button")

        result = executor.execute_step(step)

        assert result.screenshot_after == b"fake_screenshot_bytes"
        # take_screenshot should be called twice (before and after)
        assert mock_device.take_screenshot.call_count == 2

    def test_screenshot_failure_does_not_fail_step(self, executor, mock_device):
        """Screenshot capture failure should not fail the step."""
        mock_device.take_screenshot.side_effect = RuntimeError("Screenshot failed")
        step = Step(action="tap", target="Button")

        result = executor.execute_step(step)

        assert result.status == "passed"
        assert result.screenshot_before is None
        assert result.screenshot_after is None

    def test_step_includes_timestamp_in_details(self, executor, mock_device):
        """Step result should include timestamp relative to test start."""
        from mutcli.models.test import TestConfig, TestFile

        test = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[],
            steps=[
                Step(action="tap", target="Button1"),
                Step(action="tap", target="Button2"),
            ],
            teardown=[],
        )

        result = executor.execute_test(test)

        # All steps should have timestamps
        for step_result in result.steps:
            assert "timestamp" in step_result.details
            assert step_result.details["timestamp"] >= 0

        # Second step timestamp should be greater than first
        assert result.steps[1].details["timestamp"] >= result.steps[0].details["timestamp"]

    def test_before_screenshot_captured_on_unknown_action(self, executor, mock_device):
        """Before screenshot should be captured even for unknown actions."""
        step = Step(action="unknown_action_xyz")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert result.screenshot_before == b"fake_screenshot_bytes"
        # Only before screenshot captured for unknown action (fails early)
        assert mock_device.take_screenshot.call_count == 1

    def test_before_screenshot_captured_on_exception(self, executor, mock_device):
        """Before screenshot should be captured even when action raises exception."""
        mock_device.tap.side_effect = RuntimeError("Device disconnected")
        step = Step(action="tap", target="Button")

        result = executor.execute_step(step)

        assert result.status == "failed"
        assert result.screenshot_before == b"fake_screenshot_bytes"
        # Before captured, but after not captured due to exception
        assert mock_device.take_screenshot.call_count == 1


class TestExecuteTestMethod:
    """Test execute_test orchestration."""

    @pytest.fixture
    def mock_device(self):
        """Mock DeviceController."""
        device = MagicMock()
        device.get_screen_size.return_value = (1080, 2340)
        device.find_element.return_value = (540, 1200)
        return device

    @pytest.fixture
    def executor(self, mock_device):
        """Create executor with mocked device."""
        with patch("mutcli.core.executor.DeviceController", return_value=mock_device):
            return TestExecutor(device_id="test-device")

    def test_execute_test_runs_setup_before_steps(self, executor, mock_device):
        """Setup steps run before main steps."""
        call_order = []

        def track_launch(*args):
            call_order.append("launch")

        def track_tap(*args):
            call_order.append("tap")

        mock_device.launch_app.side_effect = track_launch
        mock_device.tap.side_effect = track_tap

        test = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[Step(action="launch_app", target="com.example.app")],
            steps=[Step(action="tap", target="Button")],
            teardown=[],
        )

        result = executor.execute_test(test)

        assert result.status == "passed"
        assert call_order == ["launch", "tap"]

    def test_execute_test_stops_on_setup_failure(self, executor, mock_device):
        """Setup failure prevents main steps from running."""
        mock_device.find_element.return_value = None

        test = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[Step(action="tap", target="NonExistent")],
            steps=[Step(action="tap", target="Button")],
            teardown=[],
        )

        result = executor.execute_test(test)

        assert result.status == "failed"
        assert "setup failed" in result.error.lower()
        # Only setup step should be in results (main steps not executed)
        assert len(result.steps) == 1
        assert result.steps[0].action == "tap"
        assert result.steps[0].status == "failed"

    def test_execute_test_runs_teardown_after_failure(self, executor, mock_device):
        """Teardown runs even when main steps fail."""
        call_order = []

        def track_launch(*args):
            call_order.append("launch")

        def track_terminate(*args):
            call_order.append("terminate")

        mock_device.launch_app.side_effect = track_launch
        mock_device.terminate_app.side_effect = track_terminate
        mock_device.find_element.return_value = None

        test = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[Step(action="launch_app", target="com.example.app")],
            steps=[Step(action="tap", target="NonExistent")],
            teardown=[Step(action="terminate_app", target="com.example.app")],
        )

        result = executor.execute_test(test)

        assert result.status == "failed"
        # Teardown should still run after main step failure
        assert call_order == ["launch", "terminate"]
        # All steps should be in results: 1 setup + 1 main + 1 teardown
        assert len(result.steps) == 3

    def test_execute_test_resets_step_number(self, executor, mock_device):
        """Step number resets for each test execution."""
        test1 = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[],
            steps=[
                Step(action="tap", target="Button1"),
                Step(action="tap", target="Button2"),
            ],
            teardown=[],
        )
        test2 = TestFile(
            config=TestConfig(app="com.example.app"),
            setup=[],
            steps=[Step(action="tap", target="Button3")],
            teardown=[],
        )

        result1 = executor.execute_test(test1)
        result2 = executor.execute_test(test2)

        # First test: steps numbered 1, 2
        assert result1.steps[0].step_number == 1
        assert result1.steps[1].step_number == 2
        # Second test: step should be numbered 1 (reset), not 3
        assert result2.steps[0].step_number == 1
