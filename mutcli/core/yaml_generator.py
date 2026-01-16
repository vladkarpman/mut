"""YAML test file generator."""

from pathlib import Path
from typing import Any

import yaml


class YAMLGenerator:
    """Generate YAML test files from recorded actions.

    Creates YAML test files following the mut test format with config,
    setup, steps, and teardown sections.

    Usage:
        gen = YAMLGenerator("login_test", "com.example.app")
        gen.add_launch_app()
        gen.add_tap(540, 1200, element="Login")
        gen.add_type("user@test.com")
        gen.add_terminate_app()
        gen.save(Path("tests/login.yaml"))
    """

    def __init__(self, name: str, app_package: str):
        """Initialize generator.

        Args:
            name: Test name
            app_package: Android app package name
        """
        self._name = name
        self._app_package = app_package
        self._steps: list[dict[str, Any]] = []
        self._setup: list[Any] = []
        self._teardown: list[Any] = []

    def add_tap(self, x: int, y: int, element: str | None = None) -> None:
        """Add tap action.

        Element text preferred over coordinates when available.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            element: Element text (optional, preferred over coordinates)
        """
        if element:
            self._steps.append({"tap": element})
        else:
            self._steps.append({"tap": [x, y]})

    def add_type(self, text: str, field: str | None = None) -> None:
        """Add type action.

        Args:
            text: Text to type
            field: Target field name (optional, uses rich syntax when provided)
        """
        if field:
            self._steps.append({"type": {"text": text, "field": field}})
        else:
            self._steps.append({"type": text})

    def add_swipe(self, direction: str, distance: str | None = None) -> None:
        """Add swipe action.

        Args:
            direction: Swipe direction (up, down, left, right)
            distance: Swipe distance (e.g., "50%", optional)
        """
        swipe_data: dict[str, str] = {"direction": direction}
        if distance:
            swipe_data["distance"] = distance
        self._steps.append({"swipe": swipe_data})

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
