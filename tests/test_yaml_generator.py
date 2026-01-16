"""Tests for YAMLGenerator."""

from pathlib import Path

import yaml

from mutcli.core.yaml_generator import YAMLGenerator


class TestYAMLGeneratorInitialization:
    """Test YAMLGenerator initialization."""

    def test_stores_name_and_app_package(self):
        """Should store test name and app package."""
        gen = YAMLGenerator("login_test", "com.example.app")

        assert gen._name == "login_test"
        assert gen._app_package == "com.example.app"

    def test_initializes_empty_steps(self):
        """Should initialize with empty steps list."""
        gen = YAMLGenerator("test", "com.example.app")

        assert gen._steps == []

    def test_initializes_empty_setup_teardown(self):
        """Should initialize with empty setup and teardown."""
        gen = YAMLGenerator("test", "com.example.app")

        assert gen._setup == []
        assert gen._teardown == []


class TestAddTap:
    """Test add_tap method."""

    def test_tap_uses_element_when_provided(self):
        """tap should use element text when provided."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_tap(540, 1200, element="Login button")

        assert len(gen._steps) == 1
        assert gen._steps[0] == {"tap": "Login button"}

    def test_tap_uses_coordinates_when_no_element(self):
        """tap should use coordinates when no element provided."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_tap(540, 1200)

        assert len(gen._steps) == 1
        assert gen._steps[0] == {"tap": [540, 1200]}

    def test_tap_prefers_element_over_coordinates(self):
        """tap should prefer element text over coordinates."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_tap(100, 200, element="Submit")

        # Should use element, not coordinates
        assert gen._steps[0] == {"tap": "Submit"}


class TestAddType:
    """Test add_type method."""

    def test_type_with_just_text(self):
        """type with just text should use simple syntax."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_type("user@test.com")

        assert gen._steps[0] == {"type": "user@test.com"}

    def test_type_with_text_and_field(self):
        """type with text and field should use rich syntax."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_type("user@test.com", field="Email")

        assert gen._steps[0] == {"type": {"text": "user@test.com", "field": "Email"}}


class TestAddSwipe:
    """Test add_swipe method."""

    def test_swipe_direction_only(self):
        """swipe with direction only should use simple syntax."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_swipe("up")

        assert gen._steps[0] == {"swipe": {"direction": "up"}}

    def test_swipe_with_distance(self):
        """swipe with distance should include distance."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_swipe("down", distance="50%")

        assert gen._steps[0] == {"swipe": {"direction": "down", "distance": "50%"}}

    def test_swipe_validates_direction(self):
        """swipe should accept valid directions."""
        gen = YAMLGenerator("test", "com.example.app")

        for direction in ["up", "down", "left", "right"]:
            gen.add_swipe(direction)

        assert len(gen._steps) == 4


class TestAddWait:
    """Test add_wait method."""

    def test_wait_with_duration(self):
        """wait should store duration string."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_wait("2s")

        assert gen._steps[0] == {"wait": "2s"}

    def test_wait_with_milliseconds(self):
        """wait should accept milliseconds."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_wait("500ms")

        assert gen._steps[0] == {"wait": "500ms"}


class TestAddWaitFor:
    """Test add_wait_for method."""

    def test_wait_for_element(self):
        """wait_for should store element text."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_wait_for("Loading complete")

        assert gen._steps[0] == {"wait_for": "Loading complete"}

    def test_wait_for_with_timeout(self):
        """wait_for with timeout should use rich syntax."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_wait_for("Dashboard", timeout="30s")

        assert gen._steps[0] == {"wait_for": {"element": "Dashboard", "timeout": "30s"}}


class TestAddVerifyScreen:
    """Test add_verify_screen method."""

    def test_verify_screen(self):
        """verify_screen should store description."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_verify_screen("User is logged in")

        assert gen._steps[0] == {"verify_screen": "User is logged in"}


class TestAddLaunchApp:
    """Test add_launch_app method."""

    def test_launch_app_default(self):
        """launch_app without package should add simple action to setup."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_launch_app()

        assert len(gen._setup) == 1
        assert gen._setup[0] == "launch_app"

    def test_launch_app_with_package(self):
        """launch_app with package should include package."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_launch_app("com.other.app")

        assert gen._setup[0] == {"launch_app": "com.other.app"}


class TestAddTerminateApp:
    """Test add_terminate_app method."""

    def test_terminate_app_default(self):
        """terminate_app without package should add simple action to teardown."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_terminate_app()

        assert len(gen._teardown) == 1
        assert gen._teardown[0] == "terminate_app"

    def test_terminate_app_with_package(self):
        """terminate_app with package should include package."""
        gen = YAMLGenerator("test", "com.example.app")

        gen.add_terminate_app("com.other.app")

        assert gen._teardown[0] == {"terminate_app": "com.other.app"}


class TestGenerate:
    """Test generate method."""

    def test_generates_basic_structure(self):
        """generate should create valid YAML with config."""
        gen = YAMLGenerator("login_test", "com.example.app")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "config" in data
        assert data["config"]["app"] == "com.example.app"

    def test_generates_steps(self):
        """generate should include steps."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(540, 1200, element="Login")
        gen.add_type("user@test.com")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "steps" in data
        assert len(data["steps"]) == 2

    def test_generates_setup_section(self):
        """generate should include setup section when present."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_launch_app()
        gen.add_tap(100, 200, element="Start")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "setup" in data
        assert data["setup"] == ["launch_app"]

    def test_generates_teardown_section(self):
        """generate should include teardown section when present."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(100, 200, element="Done")
        gen.add_terminate_app()

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "teardown" in data
        assert data["teardown"] == ["terminate_app"]

    def test_omits_empty_setup(self):
        """generate should omit setup section when empty."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(100, 200, element="Button")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "setup" not in data

    def test_omits_empty_teardown(self):
        """generate should omit teardown section when empty."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(100, 200, element="Button")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "teardown" not in data

    def test_generates_empty_steps_list(self):
        """generate should include empty steps list when no steps added."""
        gen = YAMLGenerator("test", "com.example.app")

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert "steps" in data
        assert data["steps"] == []

    def test_preserves_key_order(self):
        """generate should preserve key order: config, setup, steps, teardown."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_launch_app()
        gen.add_tap(100, 200, element="Button")
        gen.add_terminate_app()

        yaml_str = gen.generate()

        # Check order by finding positions
        config_pos = yaml_str.find("config:")
        setup_pos = yaml_str.find("setup:")
        steps_pos = yaml_str.find("steps:")
        teardown_pos = yaml_str.find("teardown:")

        assert config_pos < setup_pos < steps_pos < teardown_pos


class TestSave:
    """Test save method."""

    def test_saves_to_file(self, tmp_path):
        """save should write YAML to file."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(540, 1200, element="Login")

        output_path = tmp_path / "test.yaml"
        gen.save(output_path)

        assert output_path.exists()
        content = output_path.read_text()
        data = yaml.safe_load(content)
        assert data["config"]["app"] == "com.example.app"

    def test_creates_parent_directory(self, tmp_path):
        """save should create parent directories if they don't exist."""
        gen = YAMLGenerator("test", "com.example.app")
        gen.add_tap(540, 1200)

        nested_path = tmp_path / "nested" / "dir" / "test.yaml"
        gen.save(nested_path)

        assert nested_path.exists()

    def test_accepts_string_path(self, tmp_path):
        """save should accept string path."""
        gen = YAMLGenerator("test", "com.example.app")

        path_str = str(tmp_path / "test.yaml")
        gen.save(path_str)

        assert Path(path_str).exists()


class TestCompleteWorkflow:
    """Test complete workflow scenarios."""

    def test_full_login_test(self, tmp_path):
        """Complete login test workflow."""
        gen = YAMLGenerator("login_test", "com.example.app")

        # Setup
        gen.add_launch_app()

        # Steps
        gen.add_wait_for("Login button")
        gen.add_tap(540, 1200, element="Login button")
        gen.add_type("user@test.com", field="Email")
        gen.add_type("password123", field="Password")
        gen.add_tap(540, 1400, element="Submit")
        gen.add_verify_screen("User is logged in and dashboard is visible")

        # Teardown
        gen.add_terminate_app()

        # Save and verify
        output = tmp_path / "login.yaml"
        gen.save(output)

        data = yaml.safe_load(output.read_text())

        assert data["config"]["app"] == "com.example.app"
        assert data["setup"] == ["launch_app"]
        assert len(data["steps"]) == 6
        assert data["teardown"] == ["terminate_app"]

    def test_swipe_navigation_test(self, tmp_path):
        """Swipe navigation test workflow."""
        gen = YAMLGenerator("carousel_test", "com.example.app")

        gen.add_launch_app()
        gen.add_wait("2s")
        gen.add_swipe("left")
        gen.add_swipe("left", distance="75%")
        gen.add_swipe("right")
        gen.add_terminate_app()

        yaml_str = gen.generate()
        data = yaml.safe_load(yaml_str)

        assert len(data["steps"]) == 4
        assert data["steps"][0] == {"wait": "2s"}
        assert data["steps"][1] == {"swipe": {"direction": "left"}}
        assert data["steps"][2] == {"swipe": {"direction": "left", "distance": "75%"}}
