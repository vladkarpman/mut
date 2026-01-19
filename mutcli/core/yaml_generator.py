"""YAML test file generator."""

from pathlib import Path
from typing import Any

import yaml

from mutcli.core.step_analyzer import AnalyzedStep
from mutcli.core.typing_detector import TypingSequence
from mutcli.core.verification_suggester import VerificationPoint


class YAMLGenerator:
    """Generate YAML test files from recorded actions.

    Creates YAML test files following the mut test format with config,
    setup, steps, and teardown sections.

    Usage:
        gen = YAMLGenerator("login_test", "com.example.app", 1080, 1920)
        gen.add_launch_app()
        gen.add_tap(540, 1200, element="Login")
        gen.add_type("user@test.com")
        gen.add_terminate_app()
        gen.save(Path("tests/login.yaml"))
    """

    def __init__(
        self,
        name: str,
        app_package: str,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ):
        """Initialize generator.

        Args:
            name: Test name
            app_package: Android app package name
            screen_width: Screen width in pixels (for percentage conversion)
            screen_height: Screen height in pixels (for percentage conversion)
        """
        self._name = name
        self._app_package = app_package
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._steps: list[dict[str, Any]] = []
        self._setup: list[Any] = []
        self._teardown: list[Any] = []

    def _to_percent_coords(self, px: int, py: int) -> list[str]:
        """Convert pixel coordinates to percentage strings."""
        if self._screen_width and self._screen_height:
            x_pct = round(px / self._screen_width * 100, 1)
            y_pct = round(py / self._screen_height * 100, 1)
            return [f"{x_pct}%", f"{y_pct}%"]
        return [px, py]

    def add_tap(
        self,
        x: int = 0,
        y: int = 0,
        element: str | None = None,
        coords: tuple[int, int] | None = None,
    ) -> None:
        """Add tap action (simple format).

        Element text preferred over coordinates when available.
        Coordinates are converted to percentages if screen dimensions are set.

        Args:
            x: X coordinate in pixels (deprecated, use coords)
            y: Y coordinate in pixels (deprecated, use coords)
            element: Element text (optional, preferred over coordinates)
            coords: Coordinates as (x, y) tuple in pixels
        """
        if element:
            self._steps.append({"tap": element})
        else:
            px, py = coords if coords else (x, y)
            self._steps.append({"tap": self._to_percent_coords(px, py)})

    def add_rich_tap(
        self,
        element: str | None = None,
        coords: tuple[int, int] | None = None,
        description: str | None = None,
        verification: str | None = None,
    ) -> None:
        """Add tap action with full details.

        Includes element text, fallback coordinates, description, and optional
        verification step.

        Args:
            element: Element text for AI matching
            coords: Fallback coordinates as (x, y) tuple in pixels
            description: Human-readable description of the action
            verification: If provided, adds verify_screen after this step
        """
        step: dict[str, Any] = {}

        if element:
            step["tap"] = element
            # Add fallback coordinates if available
            if coords:
                step["at"] = self._to_percent_coords(coords[0], coords[1])
        elif coords:
            step["tap"] = self._to_percent_coords(coords[0], coords[1])
        else:
            step["tap"] = [0, 0]

        if description:
            step["description"] = description

        self._steps.append(step)

        # Add verification after the tap if provided
        if verification:
            self._steps.append({"verify_screen": verification})

    def add_type(
        self, text: str, field: str | None = None, submit: bool = False
    ) -> None:
        """Add type action.

        Args:
            text: Text to type
            field: Target field name (optional, uses rich syntax when provided)
            submit: Whether to press Enter after typing (optional)
        """
        if submit:
            self._steps.append({"type": {"text": text, "submit": True}})
        elif field:
            self._steps.append({"type": {"text": text, "field": field}})
        else:
            self._steps.append({"type": text})

    def add_swipe(
        self,
        direction: str,
        distance: str | None = None,
        description: str | None = None,
    ) -> None:
        """Add swipe action.

        Args:
            direction: Swipe direction (up, down, left, right)
            distance: Swipe distance (e.g., "50%", optional)
            description: Human-readable description of the action (optional)
        """
        swipe_data: dict[str, Any] = {"direction": direction}
        if distance:
            swipe_data["distance"] = distance
        step: dict[str, Any] = {"swipe": swipe_data}
        if description:
            step["description"] = description
        self._steps.append(step)

    def add_wait(self, duration: str) -> None:
        """Add wait action.

        Args:
            duration: Wait duration (e.g., "2s", "500ms")
        """
        self._steps.append({"wait": duration})

    def add_wait_for(self, element: str, timeout: str | None = None) -> None:
        """Add wait_for action.

        Args:
            element: Element text to wait for
            timeout: Maximum wait time (optional, uses rich syntax when provided)
        """
        if timeout:
            self._steps.append({"wait_for": {"element": element, "timeout": timeout}})
        else:
            self._steps.append({"wait_for": element})

    def add_verify_screen(self, description: str) -> None:
        """Add verify_screen action.

        Args:
            description: Description of expected screen state
        """
        self._steps.append({"verify_screen": description})

    def add_launch_app(self, package: str | None = None) -> None:
        """Add launch_app to setup section.

        Args:
            package: App package name (optional, uses config.app if not provided)
        """
        if package:
            self._setup.append({"launch_app": package})
        else:
            self._setup.append("launch_app")

    def add_terminate_app(self, package: str | None = None) -> None:
        """Add terminate_app to teardown section.

        Args:
            package: App package name (optional, uses config.app if not provided)
        """
        if package:
            self._teardown.append({"terminate_app": package})
        else:
            self._teardown.append("terminate_app")

    def generate(self) -> str:
        """Generate YAML content as string.

        Returns:
            YAML formatted string with config, setup, steps, and teardown sections.
            Empty sections (except steps) are omitted.
        """
        # Build document preserving key order
        doc: dict[str, Any] = {
            "config": {
                "app": self._app_package,
            },
        }

        if self._setup:
            doc["setup"] = self._setup

        doc["steps"] = self._steps

        if self._teardown:
            doc["teardown"] = self._teardown

        return yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def save(self, path: Path | str) -> None:
        """Save YAML to file.

        Creates parent directories if they don't exist.

        Args:
            path: Output file path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        content = self.generate()
        path.write_text(content, encoding="utf-8")

    def add_analyzed_step(self, step: AnalyzedStep) -> None:
        """Add step using AI-extracted element text with coordinates as fallback.

        Maestro-style: element text is primary, coordinates are secondary fallback.
        Always includes coordinates when available for resilience.

        Args:
            step: AnalyzedStep with element_text, action_description, and original_tap data
        """
        x = int(step.original_tap.get("x", 0))
        y = int(step.original_tap.get("y", 0))
        coords = (x, y) if x > 0 or y > 0 else None

        # Use rich tap format: element text primary, coordinates as fallback
        self.add_rich_tap(
            element=step.element_text,  # Primary (may be None)
            coords=coords,  # Fallback coordinates
            description=step.action_description,  # Human-readable description
        )

    def add_typing_sequence(self, sequence: TypingSequence) -> None:
        """Add type command for detected typing sequence.

        Only adds if text was provided (via interview).

        Args:
            sequence: TypingSequence with optional text field
        """
        if sequence.text:
            self.add_type(sequence.text)
        # If no text provided, skip (user didn't fill it in)

    def generate_from_analysis(
        self,
        analyzed_steps: list[AnalyzedStep],
        typing_sequences: list[TypingSequence],
        verifications: list[VerificationPoint],
    ) -> str:
        """Generate YAML from full analysis results.

        Merges steps, typing, and verifications in correct order:
        1. Typing sequences replace the taps they contain
        2. Verifications are inserted after specified steps

        Args:
            analyzed_steps: Steps with AI-extracted element text
            typing_sequences: Detected typing with user-provided text
            verifications: Suggested verification points

        Returns:
            Generated YAML string
        """
        # Create map of typing sequences by start_index
        typing_by_start: dict[int, TypingSequence] = {
            seq.start_index: seq for seq in typing_sequences
        }

        # Create set of indices covered by typing sequences (to skip)
        typing_indices: set[int] = set()
        for seq in typing_sequences:
            for i in range(seq.start_index, seq.end_index + 1):
                typing_indices.add(i)

        # Create map of verifications by after_step_index
        verifications_by_step: dict[int, VerificationPoint] = {
            v.after_step_index: v for v in verifications
        }

        # Process each analyzed step
        for step in analyzed_steps:
            idx = step.index

            # Check if this is the start of a typing sequence
            if idx in typing_by_start:
                seq = typing_by_start[idx]
                self.add_typing_sequence(seq)
            # Skip if this index is part of a typing sequence (but not the start)
            elif idx not in typing_indices:
                self.add_analyzed_step(step)

            # Check for verification after this step
            if idx in verifications_by_step:
                verification = verifications_by_step[idx]
                self.add_verify_screen(verification.description)

        return self.generate()
