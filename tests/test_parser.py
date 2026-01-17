"""Tests for TestParser."""

import pytest

from mutcli.core.parser import ParseError, TestParser


class TestParserBasic:
    def test_parses_simple_test(self, tmp_path):
        """Parses basic YAML test file."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap: "Login"
  - type: "user@test.com"
  - verify_screen: "Welcome"
""")

        result = TestParser.parse(test_file)

        assert result.config.app == "com.example.app"
        assert len(result.steps) == 3
        assert result.steps[0].action == "tap"
        assert result.steps[0].target == "Login"

    def test_parses_rich_syntax(self, tmp_path):
        """Parses rich action syntax with options."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap:
      element: "Submit"
      coordinates: [50%, 75%]
      timeout: 10s
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "tap"
        assert step.target == "Submit"
        assert step.coordinates == (50.0, 75.0)
        assert step.coordinates_type == "percent"
        assert step.timeout == 10.0

    def test_parses_conditionals(self, tmp_path):
        """Parses conditional steps."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - if_present: "Cookie banner"
    then:
      - tap: "Accept"
    else:
      - tap: "Continue"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "if_present"
        assert step.condition_type == "if_present"
        assert step.condition_target == "Cookie banner"
        assert len(step.then_steps) == 1
        assert len(step.else_steps) == 1

    def test_validates_required_fields(self, tmp_path):
        """Raises error for missing required fields."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
steps:
  - tap: "Login"
""")

        with pytest.raises(ParseError, match="config.app"):
            TestParser.parse(test_file)

    def test_parses_coordinates_pixels(self, tmp_path):
        """Parses pixel coordinates (no % sign)."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap:
      coordinates: [540, 1200]
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.coordinates == (540, 1200)
        assert step.coordinates_type == "pixels"


class TestParserActions:
    """Test parsing of various action types."""

    def test_parses_type_action(self, tmp_path):
        """Parses type action with text."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - type: "Hello World"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "type"
        assert step.target == "Hello World"

    def test_parses_type_with_field(self, tmp_path):
        """Parses type action with field targeting."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - type:
      text: "user@test.com"
      field: "Email"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "type"
        assert step.text == "user@test.com"
        assert step.target_field == "Email"

    def test_parses_swipe_action(self, tmp_path):
        """Parses swipe action with direction."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - swipe:
      direction: up
      distance: 50%
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "swipe"
        assert step.direction == "up"
        assert step.distance == 50.0

    def test_parses_wait_action(self, tmp_path):
        """Parses wait action with duration."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - wait: 2s
  - wait: 500ms
""")

        result = TestParser.parse(test_file)

        assert result.steps[0].action == "wait"
        assert result.steps[0].timeout == 2.0
        assert result.steps[1].action == "wait"
        assert result.steps[1].timeout == 0.5

    def test_parses_wait_for_action(self, tmp_path):
        """Parses wait_for action."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - wait_for: "Loading complete"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "wait_for"
        assert step.target == "Loading complete"

    def test_parses_verify_screen(self, tmp_path):
        """Parses verify_screen action."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - verify_screen: "Dashboard should show user profile"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "verify_screen"
        assert step.target == "Dashboard should show user profile"

    def test_parses_simple_actions(self, tmp_path):
        """Parses simple string actions."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - launch_app
  - back
  - terminate_app
""")

        result = TestParser.parse(test_file)

        assert result.steps[0].action == "launch_app"
        assert result.steps[1].action == "back"
        assert result.steps[2].action == "terminate_app"


class TestParserSetupTeardown:
    """Test parsing of setup and teardown sections."""

    def test_parses_setup_section(self, tmp_path):
        """Parses setup section."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

setup:
  - launch_app
  - wait: 2s

steps:
  - tap: "Login"
""")

        result = TestParser.parse(test_file)

        assert len(result.setup) == 2
        assert result.setup[0].action == "launch_app"
        assert result.setup[1].action == "wait"

    def test_parses_teardown_section(self, tmp_path):
        """Parses teardown section."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap: "Login"

teardown:
  - terminate_app
""")

        result = TestParser.parse(test_file)

        assert len(result.teardown) == 1
        assert result.teardown[0].action == "terminate_app"


class TestParserConditionals:
    """Test parsing of conditional operators."""

    def test_parses_if_absent(self, tmp_path):
        """Parses if_absent conditional."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - if_absent: "Welcome message"
    then:
      - tap: "Login"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "if_absent"
        assert step.condition_type == "if_absent"
        assert step.condition_target == "Welcome message"
        assert len(step.then_steps) == 1
        assert len(step.else_steps) == 0

    def test_parses_if_screen(self, tmp_path):
        """Parses if_screen conditional with AI description."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - if_screen: "Login form is visible"
    then:
      - type: "user@test.com"
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "if_screen"
        assert step.condition_type == "if_screen"
        assert step.condition_target == "Login form is visible"

    def test_parses_nested_conditionals(self, tmp_path):
        """Parses nested conditional steps."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - if_present: "Cookie banner"
    then:
      - tap: "Accept"
      - if_present: "Newsletter popup"
        then:
          - tap: "No thanks"
""")

        result = TestParser.parse(test_file)

        outer = result.steps[0]
        assert outer.action == "if_present"
        assert len(outer.then_steps) == 2

        inner = outer.then_steps[1]
        assert inner.action == "if_present"
        assert inner.condition_type == "if_present"
        assert inner.condition_target == "Newsletter popup"


class TestParserRepeat:
    """Test parsing of repeat steps."""

    def test_parses_repeat(self, tmp_path):
        """Parses repeat step."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - repeat: 3
    steps:
      - swipe:
          direction: up
      - wait: 1s
""")

        result = TestParser.parse(test_file)

        step = result.steps[0]
        assert step.action == "repeat"
        assert step.repeat_count == 3
        assert len(step.repeat_steps) == 2


class TestParserDurations:
    """Test parsing of various duration formats."""

    def test_parses_seconds(self, tmp_path):
        """Parses seconds duration."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - wait: 5s
""")

        result = TestParser.parse(test_file)
        assert result.steps[0].timeout == 5.0

    def test_parses_milliseconds(self, tmp_path):
        """Parses milliseconds duration."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - wait: 500ms
""")

        result = TestParser.parse(test_file)
        assert result.steps[0].timeout == 0.5

    def test_parses_numeric_duration(self, tmp_path):
        """Parses numeric duration (assumes seconds)."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - wait: 3
""")

        result = TestParser.parse(test_file)
        assert result.steps[0].timeout == 3.0


class TestParserErrors:
    """Test parser error handling."""

    def test_raises_on_file_not_found(self, tmp_path):
        """Raises ParseError when file does not exist."""
        nonexistent = tmp_path / "does_not_exist.yaml"

        with pytest.raises(ParseError, match="Test file not found"):
            TestParser.parse(nonexistent)

    def test_raises_on_empty_file(self, tmp_path):
        """Raises ParseError for empty file."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("")

        with pytest.raises(ParseError, match="Test file is empty"):
            TestParser.parse(test_file)

    def test_raises_on_invalid_yaml(self, tmp_path):
        """Raises ParseError for invalid YAML."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
this is not valid yaml:
  - [unclosed bracket
""")

        with pytest.raises(ParseError, match="Invalid YAML"):
            TestParser.parse(test_file)

    def test_raises_on_unknown_action(self, tmp_path):
        """Raises ParseError for unknown action."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - unknown_action: "value"
""")

        with pytest.raises(ParseError, match="Unknown action"):
            TestParser.parse(test_file)

    def test_raises_on_invalid_coordinates(self, tmp_path):
        """Raises ParseError for invalid coordinates."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap:
      coordinates: [100]
""")

        with pytest.raises(ParseError, match="(?i)coordinates"):
            TestParser.parse(test_file)

    def test_raises_on_missing_config(self, tmp_path):
        """Raises ParseError when config section is missing."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
steps:
  - tap: "Button"
""")

        with pytest.raises(ParseError, match="config.app"):
            TestParser.parse(test_file)


class TestParserConfig:
    """Test parsing of config section."""

    def test_parses_device(self, tmp_path):
        """Parses device from config."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app
  device: emulator-5554
""")

        result = TestParser.parse(test_file)
        assert result.config.device == "emulator-5554"

    def test_parses_timeouts(self, tmp_path):
        """Parses timeouts from config."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app
  timeouts:
    tap: 10s
    wait_for: 30s
""")

        result = TestParser.parse(test_file)
        assert result.config.timeouts == {"tap": 10.0, "wait_for": 30.0}

    def test_stores_path(self, tmp_path):
        """Stores file path in result."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("""
config:
  app: com.example.app

steps:
  - tap: "Button"
""")

        result = TestParser.parse(test_file)
        assert result.path == str(test_file)
