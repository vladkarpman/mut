"""YAML test file parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml

from mutcli.models.test import Step, TestConfig, TestFile


class ParseError(Exception):
    """Error parsing test file."""

    pass


class TestParser:
    """Parse YAML test files into TestFile objects."""

    ACTIONS = {
        "tap",
        "type",
        "swipe",
        "wait",
        "wait_for",
        "verify_screen",
        "launch_app",
        "terminate_app",
        "back",
        "scroll_to",
        "long_press",
        "double_tap",
        "hide_keyboard",
    }

    CONDITIONALS = {"if_present", "if_screen", "if_absent"}

    @classmethod
    def parse(cls, path: Path) -> TestFile:
        """Parse a YAML test file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed TestFile

        Raises:
            ParseError: If file is invalid
        """
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ParseError(f"Invalid YAML: {e}")

        if not isinstance(data, dict):
            raise ParseError("Test file must be a YAML mapping")

        # Parse config (required)
        config = cls._parse_config(data.get("config", {}))

        # Parse sections
        setup = cls._parse_steps(data.get("setup", []))
        steps = cls._parse_steps(data.get("steps", []))
        teardown = cls._parse_steps(data.get("teardown", []))

        return TestFile(
            config=config,
            setup=setup,
            steps=steps,
            teardown=teardown,
            path=str(path),
        )

    @classmethod
    def _parse_config(cls, data: dict[str, Any]) -> TestConfig:
        """Parse config section."""
        if not data.get("app"):
            raise ParseError("Missing required field: config.app")

        # Parse timeouts if present
        timeouts: dict[str, float] = {}
        if "timeouts" in data and isinstance(data["timeouts"], dict):
            for key, value in data["timeouts"].items():
                timeouts[key] = cls._parse_duration(value)

        return TestConfig(
            app=data["app"],
            device=data.get("device"),
            timeouts=timeouts,
        )

    @classmethod
    def _parse_steps(cls, data: list[Any]) -> list[Step]:
        """Parse a list of steps."""
        if not isinstance(data, list):
            return []

        return [cls._parse_step(item) for item in data]

    @classmethod
    def _parse_step(cls, data: Any) -> Step:
        """Parse a single step."""
        if isinstance(data, str):
            # Simple action like "launch_app" or "back"
            return Step(action=data, raw={"action": data})

        if not isinstance(data, dict):
            raise ParseError(f"Invalid step: {data}")

        # Check for conditional
        for cond in cls.CONDITIONALS:
            if cond in data:
                return cls._parse_conditional(cond, data)

        # Check for repeat
        if "repeat" in data:
            return cls._parse_repeat(data)

        # Regular action
        return cls._parse_action(data)

    @classmethod
    def _parse_action(cls, data: dict[str, Any]) -> Step:
        """Parse a regular action step."""
        # Find the action key
        action = None
        value = None

        for key in data:
            if key in cls.ACTIONS:
                action = key
                value = data[key]
                break

        if not action:
            raise ParseError(f"Unknown action in step: {data}")

        step = Step(action=action, raw=data)

        # Simple syntax for wait: `wait: 2s` or `wait: 500ms` or `wait: 3`
        if action == "wait" and isinstance(value, (int, float, str)):
            step.timeout = cls._parse_duration(value)
            return step

        # Simple syntax: `tap: "Button"`
        if isinstance(value, str):
            step.target = value
            return step

        # Rich syntax: `tap: {element: "Button", timeout: 5s}`
        if isinstance(value, dict):
            cls._parse_rich_action(step, value)

        return step

    @classmethod
    def _parse_rich_action(cls, step: Step, data: dict[str, Any]) -> None:
        """Parse rich action syntax."""
        # Common fields
        if "element" in data:
            step.target = data["element"]
        if "timeout" in data:
            step.timeout = cls._parse_duration(data["timeout"])
        if "retry" in data:
            step.retry = int(data["retry"])

        # Coordinates
        if "coordinates" in data:
            coords = data["coordinates"]
            step.coordinates, step.coordinates_type = cls._parse_coordinates(coords)

        # Type-specific
        if "text" in data:
            step.text = data["text"]
        if "field" in data:
            step.target_field = data["field"]
        if "description" in data:
            step.description = data["description"]

        # Swipe-specific
        if "direction" in data:
            step.direction = data["direction"]
        if "distance" in data:
            step.distance = cls._parse_percent(data["distance"])
        if "from" in data:
            step.from_coords, _ = cls._parse_coordinates(data["from"])

    @classmethod
    def _parse_conditional(cls, cond_type: str, data: dict[str, Any]) -> Step:
        """Parse conditional step."""
        condition = data[cond_type]

        step = Step(
            action=cond_type,
            condition=condition,
            then_steps=cls._parse_steps(data.get("then", [])),
            else_steps=cls._parse_steps(data.get("else", [])),
            raw=data,
        )

        return step

    @classmethod
    def _parse_repeat(cls, data: dict[str, Any]) -> Step:
        """Parse repeat step."""
        return Step(
            action="repeat",
            repeat_count=int(data["repeat"]),
            repeat_steps=cls._parse_steps(data.get("steps", [])),
            raw=data,
        )

    @classmethod
    def _parse_duration(cls, value: Any) -> float:
        """Parse duration like '5s' or '500ms' to seconds."""
        if isinstance(value, (int, float)):
            return float(value)

        s = str(value).strip().lower()

        if s.endswith("ms"):
            return float(s[:-2]) / 1000
        if s.endswith("s"):
            return float(s[:-1])

        return float(s)

    @classmethod
    def _parse_coordinates(
        cls, coords: list[Any]
    ) -> tuple[tuple[float, float], Literal["percent", "pixels"]]:
        """Parse coordinates list like [50%, 75%] or [540, 1200]."""
        if len(coords) != 2:
            raise ParseError(f"Coordinates must have 2 values: {coords}")

        x, y = coords

        # Check if percent
        if isinstance(x, str) and "%" in x:
            return (cls._parse_percent(x), cls._parse_percent(y)), "percent"

        # Pixels
        return (float(x), float(y)), "pixels"

    @classmethod
    def _parse_percent(cls, value: Any) -> float:
        """Parse percent value like '50%' or 50."""
        if isinstance(value, (int, float)):
            return float(value)

        s = str(value).strip()
        if s.endswith("%"):
            return float(s[:-1])

        return float(s)
