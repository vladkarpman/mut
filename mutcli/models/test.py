"""Test file data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TestConfig:
    """Test configuration section."""

    app: str
    device: str | None = None
    timeouts: dict[str, float] = field(default_factory=dict)


@dataclass
class Step:
    """A single test step."""

    action: str
    target: str | None = None
    coordinates: tuple[float, float] | None = None
    coordinates_type: Literal["percent", "pixels"] | None = None
    timeout: float | None = None
    retry: int | None = None

    # For type action
    text: str | None = None
    target_field: str | None = None  # Named target_field to avoid shadowing dataclasses.field

    # For swipe action
    direction: str | None = None
    distance: float | None = None
    from_coords: tuple[float, float] | None = None

    # For long_press action
    duration: int | None = None  # Duration in milliseconds

    # For scroll_to action
    max_scrolls: int | None = None

    # For verify_screen
    description: str | None = None

    # For conditionals
    condition_type: str | None = None  # "if_present", "if_absent", "if_screen", etc.
    condition_target: str | None = None  # Element name or screen description
    then_steps: list[Step] = field(default_factory=list)
    else_steps: list[Step] = field(default_factory=list)

    # For repeat
    repeat_count: int | None = None
    repeat_steps: list[Step] = field(default_factory=list)

    # Raw data for debugging
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MutSpec:
    """Parsed YAML test specification."""

    # Tell pytest not to collect this as a test class
    __test__ = False

    config: TestConfig
    setup: list[Step] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    teardown: list[Step] = field(default_factory=list)
    path: str | None = None


# Alias for compatibility with task spec
TestFile = MutSpec
