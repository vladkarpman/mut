"""Tests for Step model with conditional fields."""


from mutcli.models.test import Step


class TestStepModel:
    """Tests for Step dataclass."""

    def test_step_basic_creation(self):
        """Basic Step with action only."""
        step = Step(action="tap")

        assert step.action == "tap"
        assert step.target is None
        assert step.condition_type is None
        assert step.condition_target is None
        assert step.then_steps == []
        assert step.else_steps == []

    def test_step_with_conditional_fields(self):
        """Step with condition_type and condition_target."""
        step = Step(
            action="if_present",
            condition_type="if_present",
            condition_target="Login button",
        )

        assert step.action == "if_present"
        assert step.condition_type == "if_present"
        assert step.condition_target == "Login button"
        assert step.then_steps == []
        assert step.else_steps == []

    def test_step_with_then_steps(self):
        """Step with nested then_steps list."""
        inner_step = Step(action="tap", target="Continue")
        step = Step(
            action="if_present",
            condition_type="if_present",
            condition_target="Welcome dialog",
            then_steps=[inner_step],
        )

        assert step.condition_type == "if_present"
        assert step.condition_target == "Welcome dialog"
        assert len(step.then_steps) == 1
        assert step.then_steps[0].action == "tap"
        assert step.then_steps[0].target == "Continue"
        assert step.else_steps == []

    def test_step_with_else_branch(self):
        """Step with both then and else branches."""
        then_step = Step(action="tap", target="Accept")
        else_step = Step(action="tap", target="Skip")

        step = Step(
            action="if_present",
            condition_type="if_present",
            condition_target="Cookie banner",
            then_steps=[then_step],
            else_steps=[else_step],
        )

        assert step.condition_type == "if_present"
        assert step.condition_target == "Cookie banner"
        assert len(step.then_steps) == 1
        assert len(step.else_steps) == 1
        assert step.then_steps[0].target == "Accept"
        assert step.else_steps[0].target == "Skip"

    def test_step_nested_conditionals(self):
        """Conditional inside another conditional's then_steps."""
        # Inner conditional
        inner_then = Step(action="tap", target="Dismiss")
        inner_conditional = Step(
            action="if_present",
            condition_type="if_present",
            condition_target="Newsletter popup",
            then_steps=[inner_then],
        )

        # Outer conditional with nested conditional in then_steps
        outer_then = Step(action="tap", target="Accept cookies")
        outer_conditional = Step(
            action="if_present",
            condition_type="if_present",
            condition_target="Cookie banner",
            then_steps=[outer_then, inner_conditional],
        )

        # Verify outer structure
        assert outer_conditional.condition_type == "if_present"
        assert outer_conditional.condition_target == "Cookie banner"
        assert len(outer_conditional.then_steps) == 2

        # Verify nested conditional
        nested = outer_conditional.then_steps[1]
        assert nested.condition_type == "if_present"
        assert nested.condition_target == "Newsletter popup"
        assert len(nested.then_steps) == 1
        assert nested.then_steps[0].target == "Dismiss"


class TestStepConditionalTypes:
    """Tests for different conditional types."""

    def test_if_absent_conditional(self):
        """Step with if_absent condition type."""
        step = Step(
            action="if_absent",
            condition_type="if_absent",
            condition_target="Error message",
            then_steps=[Step(action="tap", target="Submit")],
        )

        assert step.condition_type == "if_absent"
        assert step.condition_target == "Error message"

    def test_if_screen_conditional(self):
        """Step with if_screen condition type for AI vision."""
        step = Step(
            action="if_screen",
            condition_type="if_screen",
            condition_target="Login form is visible with email and password fields",
            then_steps=[Step(action="type", text="user@test.com")],
        )

        assert step.condition_type == "if_screen"
        assert step.condition_target == "Login form is visible with email and password fields"
