"""Tests for YAMLGenerator."""

from pathlib import Path

import yaml

from mutcli.core.step_analyzer import AnalyzedStep
from mutcli.core.typing_detector import TypingSequence
from mutcli.core.verification_suggester import VerificationPoint
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


class TestAddAnalyzedStep:
    """Test add_analyzed_step method."""

    def test_uses_element_text_when_available(self):
        """add_analyzed_step should use element_text when provided."""
        gen = YAMLGenerator("test", "com.example.app")
        step = AnalyzedStep(
            index=0,
            original_tap={"x": 540, "y": 1200, "timestamp": 1.0},
            element_text="Login Button",
            before_description="Login screen",
            after_description="Loading",
            suggested_verification=None,
        )

        gen.add_analyzed_step(step)

        assert len(gen._steps) == 1
        assert gen._steps[0] == {"tap": "Login Button"}

    def test_falls_back_to_coordinates_when_no_element_text(self):
        """add_analyzed_step should use coordinates when element_text is None."""
        gen = YAMLGenerator("test", "com.example.app")
        step = AnalyzedStep(
            index=0,
            original_tap={"x": 540, "y": 1200, "timestamp": 1.0},
            element_text=None,
            before_description="Screen state",
            after_description="Changed state",
            suggested_verification=None,
        )

        gen.add_analyzed_step(step)

        assert len(gen._steps) == 1
        assert gen._steps[0] == {"tap": [540, 1200]}

    def test_handles_empty_element_text(self):
        """add_analyzed_step should treat empty string as no element_text."""
        gen = YAMLGenerator("test", "com.example.app")
        step = AnalyzedStep(
            index=0,
            original_tap={"x": 100, "y": 200, "timestamp": 1.0},
            element_text="",
            before_description="Screen",
            after_description="Screen",
            suggested_verification=None,
        )

        gen.add_analyzed_step(step)

        # Empty string is falsy, should use coordinates
        assert gen._steps[0] == {"tap": [100, 200]}


class TestAddTypingSequence:
    """Test add_typing_sequence method."""

    def test_adds_type_command_when_text_provided(self):
        """add_typing_sequence should add type command when text is provided."""
        gen = YAMLGenerator("test", "com.example.app")
        sequence = TypingSequence(
            start_index=2,
            end_index=10,
            tap_count=9,
            duration=3.5,
            text="user@test.com",
        )

        gen.add_typing_sequence(sequence)

        assert len(gen._steps) == 1
        assert gen._steps[0] == {"type": "user@test.com"}

    def test_skips_when_no_text_provided(self):
        """add_typing_sequence should skip when text is None."""
        gen = YAMLGenerator("test", "com.example.app")
        sequence = TypingSequence(
            start_index=2,
            end_index=10,
            tap_count=9,
            duration=3.5,
            text=None,
        )

        gen.add_typing_sequence(sequence)

        assert len(gen._steps) == 0

    def test_skips_when_text_is_empty(self):
        """add_typing_sequence should skip when text is empty string."""
        gen = YAMLGenerator("test", "com.example.app")
        sequence = TypingSequence(
            start_index=2,
            end_index=10,
            tap_count=9,
            duration=3.5,
            text="",
        )

        gen.add_typing_sequence(sequence)

        # Empty string is falsy, should skip
        assert len(gen._steps) == 0


class TestGenerateFromAnalysis:
    """Test generate_from_analysis method."""

    def test_generates_basic_yaml_from_analyzed_steps(self):
        """generate_from_analysis should create YAML from analyzed steps."""
        gen = YAMLGenerator("test", "com.example.app")
        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Login",
                before_description="Login screen",
                after_description="Form focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 300, "y": 400, "timestamp": 2.0},
                element_text="Submit",
                before_description="Form filled",
                after_description="Loading",
                suggested_verification=None,
            ),
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, [], [])
        data = yaml.safe_load(yaml_str)

        assert len(data["steps"]) == 2
        assert data["steps"][0] == {"tap": "Login"}
        assert data["steps"][1] == {"tap": "Submit"}

    def test_inserts_type_commands_at_correct_positions(self):
        """generate_from_analysis should replace typing sequence taps with type command."""
        gen = YAMLGenerator("test", "com.example.app")

        # Steps 0, 1, 2 where 1-2 are typing
        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Email field",
                before_description="Login screen",
                after_description="Field focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 50, "y": 1800, "timestamp": 2.0},
                element_text=None,
                before_description="Keyboard visible",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 60, "y": 1800, "timestamp": 2.5},
                element_text=None,
                before_description="Typing",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=3,
                original_tap={"x": 70, "y": 1800, "timestamp": 3.0},
                element_text=None,
                before_description="Typing",
                after_description="Typing complete",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=4,
                original_tap={"x": 200, "y": 500, "timestamp": 4.0},
                element_text="Submit",
                before_description="Form filled",
                after_description="Submitting",
                suggested_verification=None,
            ),
        ]

        # Typing sequence covers indices 1-3
        typing_sequences = [
            TypingSequence(
                start_index=1,
                end_index=3,
                tap_count=3,
                duration=1.0,
                text="test@email.com",
            )
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, typing_sequences, [])
        data = yaml.safe_load(yaml_str)

        # Should have: tap Email field, type text, tap Submit
        assert len(data["steps"]) == 3
        assert data["steps"][0] == {"tap": "Email field"}
        assert data["steps"][1] == {"type": "test@email.com"}
        assert data["steps"][2] == {"tap": "Submit"}

    def test_inserts_verify_screen_at_suggested_points(self):
        """generate_from_analysis should insert verify_screen after specified steps."""
        gen = YAMLGenerator("test", "com.example.app")

        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Login",
                before_description="Login screen",
                after_description="Form focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 300, "y": 400, "timestamp": 2.0},
                element_text="Submit",
                before_description="Form filled",
                after_description="Dashboard visible",
                suggested_verification=None,
            ),
        ]

        verifications = [
            VerificationPoint(
                after_step_index=1,
                description="Dashboard is displayed with welcome message",
                confidence=0.85,
                reason="Form submission detected",
            )
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, [], verifications)
        data = yaml.safe_load(yaml_str)

        # Should have: tap Login, tap Submit, verify_screen
        assert len(data["steps"]) == 3
        assert data["steps"][0] == {"tap": "Login"}
        assert data["steps"][1] == {"tap": "Submit"}
        assert data["steps"][2] == {"verify_screen": "Dashboard is displayed with welcome message"}

    def test_handles_overlapping_typing_and_verifications(self):
        """generate_from_analysis should handle typing sequences with verification at end."""
        gen = YAMLGenerator("test", "com.example.app")

        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Email field",
                before_description="Login screen",
                after_description="Field focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 50, "y": 1800, "timestamp": 2.0},
                element_text=None,
                before_description="Keyboard",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 60, "y": 1800, "timestamp": 2.5},
                element_text=None,
                before_description="Typing",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=3,
                original_tap={"x": 70, "y": 1800, "timestamp": 3.0},
                element_text=None,
                before_description="Typing",
                after_description="Email entered",
                suggested_verification=None,
            ),
        ]

        # Typing sequence covers indices 1-3
        typing_sequences = [
            TypingSequence(
                start_index=1,
                end_index=3,
                tap_count=3,
                duration=1.0,
                text="user@test.com",
            )
        ]

        # Verification after last typing step
        verifications = [
            VerificationPoint(
                after_step_index=3,
                description="Email field shows entered text",
                confidence=0.7,
                reason="Long pause detected",
            )
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, typing_sequences, verifications)
        data = yaml.safe_load(yaml_str)

        # Should have: tap Email field, type text, verify_screen
        assert len(data["steps"]) == 3
        assert data["steps"][0] == {"tap": "Email field"}
        assert data["steps"][1] == {"type": "user@test.com"}
        assert data["steps"][2] == {"verify_screen": "Email field shows entered text"}

    def test_handles_multiple_typing_sequences(self):
        """generate_from_analysis should handle multiple typing sequences."""
        gen = YAMLGenerator("test", "com.example.app")

        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Email",
                before_description="Form",
                after_description="Email focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 50, "y": 1800, "timestamp": 2.0},
                element_text=None,
                before_description="Keyboard",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 60, "y": 1800, "timestamp": 2.5},
                element_text=None,
                before_description="Typing",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=3,
                original_tap={"x": 70, "y": 1800, "timestamp": 3.0},
                element_text=None,
                before_description="Typing",
                after_description="Email done",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=4,
                original_tap={"x": 100, "y": 400, "timestamp": 4.0},
                element_text="Password",
                before_description="Email filled",
                after_description="Password focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=5,
                original_tap={"x": 80, "y": 1800, "timestamp": 5.0},
                element_text=None,
                before_description="Keyboard",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=6,
                original_tap={"x": 90, "y": 1800, "timestamp": 5.5},
                element_text=None,
                before_description="Typing",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=7,
                original_tap={"x": 95, "y": 1800, "timestamp": 6.0},
                element_text=None,
                before_description="Typing",
                after_description="Password done",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=8,
                original_tap={"x": 200, "y": 600, "timestamp": 7.0},
                element_text="Login",
                before_description="Form complete",
                after_description="Logging in",
                suggested_verification=None,
            ),
        ]

        typing_sequences = [
            TypingSequence(
                start_index=1,
                end_index=3,
                tap_count=3,
                duration=1.0,
                text="user@test.com",
            ),
            TypingSequence(
                start_index=5,
                end_index=7,
                tap_count=3,
                duration=1.0,
                text="secret123",
            ),
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, typing_sequences, [])
        data = yaml.safe_load(yaml_str)

        # Should have: tap Email, type email, tap Password, type password, tap Login
        assert len(data["steps"]) == 5
        assert data["steps"][0] == {"tap": "Email"}
        assert data["steps"][1] == {"type": "user@test.com"}
        assert data["steps"][2] == {"tap": "Password"}
        assert data["steps"][3] == {"type": "secret123"}
        assert data["steps"][4] == {"tap": "Login"}

    def test_handles_empty_inputs(self):
        """generate_from_analysis should handle empty inputs gracefully."""
        gen = YAMLGenerator("test", "com.example.app")

        yaml_str = gen.generate_from_analysis([], [], [])
        data = yaml.safe_load(yaml_str)

        assert data["config"]["app"] == "com.example.app"
        assert data["steps"] == []

    def test_skips_typing_sequence_without_text(self):
        """Skip typing sequences with no text (user skipped interview)."""
        gen = YAMLGenerator("test", "com.example.app")

        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Email",
                before_description="Form",
                after_description="Focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 50, "y": 1800, "timestamp": 2.0},
                element_text=None,
                before_description="Keyboard",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 60, "y": 1800, "timestamp": 2.5},
                element_text=None,
                before_description="Typing",
                after_description="Typing",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=3,
                original_tap={"x": 70, "y": 1800, "timestamp": 3.0},
                element_text=None,
                before_description="Typing",
                after_description="Done",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=4,
                original_tap={"x": 200, "y": 500, "timestamp": 4.0},
                element_text="Submit",
                before_description="Filled",
                after_description="Submitting",
                suggested_verification=None,
            ),
        ]

        # Typing sequence without text (user skipped)
        typing_sequences = [
            TypingSequence(
                start_index=1,
                end_index=3,
                tap_count=3,
                duration=1.0,
                text=None,  # User skipped interview
            )
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, typing_sequences, [])
        data = yaml.safe_load(yaml_str)

        # Without text, typing taps are skipped entirely (no type command generated)
        # Result: tap Email, tap Submit
        assert len(data["steps"]) == 2
        assert data["steps"][0] == {"tap": "Email"}
        assert data["steps"][1] == {"tap": "Submit"}

    def test_multiple_verifications_at_different_steps(self):
        """generate_from_analysis should insert multiple verifications at correct positions."""
        gen = YAMLGenerator("test", "com.example.app")

        analyzed_steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 1.0},
                element_text="Login",
                before_description="Login screen",
                after_description="Form",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 200, "y": 300, "timestamp": 2.0},
                element_text="Submit",
                before_description="Form",
                after_description="Loading",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 300, "y": 400, "timestamp": 5.0},
                element_text="Dashboard",
                before_description="Dashboard",
                after_description="Menu",
                suggested_verification=None,
            ),
        ]

        verifications = [
            VerificationPoint(
                after_step_index=1,
                description="Loading indicator appears",
                confidence=0.8,
                reason="Form submission",
            ),
            VerificationPoint(
                after_step_index=2,
                description="Menu is displayed",
                confidence=0.7,
                reason="Navigation",
            ),
        ]

        yaml_str = gen.generate_from_analysis(analyzed_steps, [], verifications)
        data = yaml.safe_load(yaml_str)

        # Should have: tap Login, tap Submit, verify, tap Dashboard, verify
        assert len(data["steps"]) == 5
        assert data["steps"][0] == {"tap": "Login"}
        assert data["steps"][1] == {"tap": "Submit"}
        assert data["steps"][2] == {"verify_screen": "Loading indicator appears"}
        assert data["steps"][3] == {"tap": "Dashboard"}
        assert data["steps"][4] == {"verify_screen": "Menu is displayed"}
