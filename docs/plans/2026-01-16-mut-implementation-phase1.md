# mut Phase 1: Core Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Get `mut run` command working - execute YAML tests, generate JSON/HTML reports.

**Architecture:** ConfigLoader merges config sources, TestParser validates YAML, TestExecutor runs steps with video recording, ReportGenerator creates JSON/HTML output.

**Tech Stack:** Python 3.11+, Typer, PyYAML, Jinja2, scrcpy (video), adb

---

## Task 1: Configuration Loader

**Files:**
- Create: `mutcli/core/config.py`
- Test: `tests/test_config.py`

**Step 1: Write failing test for config loading**

```python
# tests/test_config.py
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mutcli.core.config import ConfigLoader, MutConfig


class TestConfigLoader:
    def test_loads_default_config_when_no_files(self):
        """Returns defaults when no config files exist."""
        with patch.object(Path, "exists", return_value=False):
            config = ConfigLoader.load()

        assert config.timeouts.tap == 5.0
        assert config.timeouts.wait_for == 10.0
        assert config.retry.count == 2

    def test_project_config_overrides_defaults(self, tmp_path):
        """Project .mut.yaml overrides defaults."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("""
app: com.example.app
timeouts:
  tap: 10
""")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            config = ConfigLoader.load()

        assert config.app == "com.example.app"
        assert config.timeouts.tap == 10.0
        assert config.timeouts.wait_for == 10.0  # Still default

    def test_env_var_overrides_config(self, tmp_path):
        """Environment variables override config files."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("device: from-file")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            with patch.dict(os.environ, {"MUT_DEVICE": "from-env"}):
                config = ConfigLoader.load()

        assert config.device == "from-env"

    def test_requires_google_api_key(self):
        """Raises error if GOOGLE_API_KEY not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                ConfigLoader.load(require_api_key=True)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'mutcli.core.config'"

**Step 3: Write minimal implementation**

```python
# mutcli/core/config.py
"""Configuration loading with layered priority."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Config file locations
GLOBAL_CONFIG = Path.home() / ".mut.yaml"
PROJECT_CONFIG = Path(".mut.yaml")


@dataclass
class TimeoutConfig:
    """Timeout settings in seconds."""
    tap: float = 5.0
    wait_for: float = 10.0
    verify_screen: float = 10.0
    type: float = 3.0
    swipe: float = 3.0


@dataclass
class RetryConfig:
    """Retry settings."""
    count: int = 2
    delay: float = 1.0


@dataclass
class MutConfig:
    """Complete mut configuration."""
    app: str | None = None
    device: str | None = None
    test_dir: str = "tests/"
    report_dir: str = "reports/"
    verbose: bool = False
    video: bool = True
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    api_key: str | None = None


class ConfigLoader:
    """Load and merge configuration from multiple sources."""

    @classmethod
    def load(cls, require_api_key: bool = False) -> MutConfig:
        """Load configuration with priority: env > project > global > defaults.

        Args:
            require_api_key: If True, raise error when GOOGLE_API_KEY not set.

        Returns:
            Merged MutConfig

        Raises:
            ValueError: If require_api_key=True and no API key found.
        """
        config = MutConfig()

        # Load global config
        if GLOBAL_CONFIG.exists():
            cls._merge_yaml(config, GLOBAL_CONFIG)

        # Load project config (overrides global)
        if PROJECT_CONFIG.exists():
            cls._merge_yaml(config, PROJECT_CONFIG)

        # Environment variables (highest priority)
        cls._merge_env(config)

        # Check API key requirement
        if require_api_key and not config.api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required.\n"
                "Get your API key at: https://makersuite.google.com/app/apikey"
            )

        return config

    @classmethod
    def _merge_yaml(cls, config: MutConfig, path: Path) -> None:
        """Merge YAML file into config."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return

        cls._merge_dict(config, data)

    @classmethod
    def _merge_dict(cls, config: MutConfig, data: dict[str, Any]) -> None:
        """Merge dictionary into config."""
        # Simple fields
        if "app" in data:
            config.app = data["app"]
        if "device" in data:
            config.device = data["device"]
        if "test_dir" in data:
            config.test_dir = data["test_dir"]
        if "report_dir" in data:
            config.report_dir = data["report_dir"]
        if "verbose" in data:
            config.verbose = data["verbose"]
        if "video" in data:
            config.video = data["video"]

        # Nested: timeouts
        if "timeouts" in data:
            t = data["timeouts"]
            if "tap" in t:
                config.timeouts.tap = float(t["tap"])
            if "wait_for" in t:
                config.timeouts.wait_for = float(t["wait_for"])
            if "verify_screen" in t:
                config.timeouts.verify_screen = float(t["verify_screen"])
            if "type" in t:
                config.timeouts.type = float(t["type"])
            if "swipe" in t:
                config.timeouts.swipe = float(t["swipe"])

        # Nested: retry
        if "retry" in data:
            r = data["retry"]
            if "count" in r:
                config.retry.count = int(r["count"])
            if "delay" in r:
                config.retry.delay = float(r["delay"])

    @classmethod
    def _merge_env(cls, config: MutConfig) -> None:
        """Merge environment variables into config."""
        if api_key := os.environ.get("GOOGLE_API_KEY"):
            config.api_key = api_key
        if device := os.environ.get("MUT_DEVICE"):
            config.device = device
        if os.environ.get("MUT_VERBOSE", "").lower() in ("1", "true"):
            config.verbose = True
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/config.py tests/test_config.py
git commit -m "feat: add ConfigLoader with layered priority"
```

---

## Task 2: YAML Test Parser

**Files:**
- Create: `mutcli/core/parser.py`
- Create: `mutcli/models/test.py`
- Test: `tests/test_parser.py`

**Step 1: Write failing test for YAML parsing**

```python
# tests/test_parser.py
import pytest
from pathlib import Path

from mutcli.core.parser import TestParser, ParseError
from mutcli.models.test import TestFile, Step


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
        assert step.condition == "Cookie banner"
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_parser.py -v
```

Expected: FAIL

**Step 3: Write models**

```python
# mutcli/models/test.py
"""Test file data models."""

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
    field: str | None = None

    # For swipe action
    direction: str | None = None
    distance: float | None = None
    from_coords: tuple[float, float] | None = None

    # For verify_screen
    description: str | None = None

    # For conditionals
    condition: str | None = None
    then_steps: list["Step"] = field(default_factory=list)
    else_steps: list["Step"] = field(default_factory=list)

    # For repeat
    repeat_count: int | None = None
    repeat_steps: list["Step"] = field(default_factory=list)

    # Raw data for debugging
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestFile:
    """Parsed test file."""
    config: TestConfig
    setup: list[Step] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    teardown: list[Step] = field(default_factory=list)
    path: str | None = None
```

**Step 4: Write parser implementation**

```python
# mutcli/core/parser.py
"""YAML test file parser."""

import re
from pathlib import Path
from typing import Any

import yaml

from mutcli.models.test import Step, TestConfig, TestFile


class ParseError(Exception):
    """Error parsing test file."""
    pass


class TestParser:
    """Parse YAML test files into TestFile objects."""

    ACTIONS = {
        "tap", "type", "swipe", "wait", "wait_for", "verify_screen",
        "launch_app", "terminate_app", "back", "scroll_to",
        "long_press", "double_tap", "hide_keyboard",
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

        return TestConfig(
            app=data["app"],
            device=data.get("device"),
            timeouts=data.get("timeouts", {}),
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

        # Simple syntax: `tap: "Button"`
        if isinstance(value, str):
            step.target = value
            return step

        # Simple syntax for wait: `wait: 2s`
        if action == "wait" and isinstance(value, (int, float, str)):
            step.timeout = cls._parse_duration(value)
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
            step.field = data["field"]
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
```

**Step 5: Run tests**

```bash
pytest tests/test_parser.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add mutcli/core/parser.py mutcli/models/test.py tests/test_parser.py
git commit -m "feat: add TestParser for YAML test files"
```

---

## Task 3: Test Executor - Basic Actions

**Files:**
- Create: `mutcli/core/executor.py`
- Test: `tests/test_executor.py`

**Step 1: Write failing test**

```python
# tests/test_executor.py
from unittest.mock import MagicMock, patch

import pytest

from mutcli.core.executor import TestExecutor, StepResult
from mutcli.models.test import Step, TestConfig, TestFile


class TestExecutorBasicActions:
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
            coordinates_type="percent"
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
```

**Step 2: Run test**

```bash
pytest tests/test_executor.py -v
```

Expected: FAIL

**Step 3: Write implementation**

```python
# mutcli/core/executor.py
"""Test execution engine."""

import time
from dataclasses import dataclass, field
from typing import Any

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.config import ConfigLoader, MutConfig
from mutcli.core.device_controller import DeviceController
from mutcli.models.test import Step, TestFile


@dataclass
class StepResult:
    """Result of executing a step."""
    step_number: int
    action: str
    status: str  # "passed", "failed", "skipped"
    duration: float = 0.0
    error: str | None = None
    screenshot_before: bytes | None = None
    screenshot_after: bytes | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Result of executing a test."""
    name: str
    status: str  # "passed", "failed", "error"
    duration: float
    steps: list[StepResult] = field(default_factory=list)
    error: str | None = None


class TestExecutor:
    """Execute test steps on device."""

    def __init__(
        self,
        device_id: str,
        config: MutConfig | None = None,
        ai_analyzer: AIAnalyzer | None = None,
    ):
        """Initialize executor.

        Args:
            device_id: ADB device identifier
            config: Configuration (loads from files if not provided)
            ai_analyzer: AI analyzer (creates new if not provided)
        """
        self._device = DeviceController(device_id)
        self._config = config or ConfigLoader.load()
        self._ai = ai_analyzer or AIAnalyzer()
        self._screen_size: tuple[int, int] | None = None
        self._step_number = 0

    def execute_test(self, test: TestFile) -> TestResult:
        """Execute a complete test file.

        Args:
            test: Parsed test file

        Returns:
            TestResult with all step results
        """
        start = time.time()
        results: list[StepResult] = []
        status = "passed"
        error = None

        try:
            # Setup
            for step in test.setup:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = f"Setup failed: {result.error}"
                    return TestResult(
                        name=test.path or "unknown",
                        status=status,
                        duration=time.time() - start,
                        steps=results,
                        error=error,
                    )

            # Main steps
            for step in test.steps:
                result = self.execute_step(step)
                results.append(result)
                if result.status == "failed":
                    status = "failed"
                    error = result.error
                    break

            # Teardown (always run)
            for step in test.teardown:
                result = self.execute_step(step)
                results.append(result)

        except Exception as e:
            status = "error"
            error = str(e)

        return TestResult(
            name=test.path or "unknown",
            status=status,
            duration=time.time() - start,
            steps=results,
            error=error,
        )

    def execute_step(self, step: Step) -> StepResult:
        """Execute a single step.

        Args:
            step: Step to execute

        Returns:
            StepResult
        """
        self._step_number += 1
        start = time.time()

        try:
            # Dispatch to action handler
            handler = getattr(self, f"_action_{step.action}", None)
            if handler is None:
                return StepResult(
                    step_number=self._step_number,
                    action=step.action,
                    status="failed",
                    error=f"Unknown action: {step.action}",
                )

            error = handler(step)

            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed" if error else "passed",
                duration=time.time() - start,
                error=error,
            )

        except Exception as e:
            return StepResult(
                step_number=self._step_number,
                action=step.action,
                status="failed",
                duration=time.time() - start,
                error=str(e),
            )

    def _get_screen_size(self) -> tuple[int, int]:
        """Get cached screen size."""
        if self._screen_size is None:
            self._screen_size = self._device.get_screen_size()
        return self._screen_size

    def _resolve_coordinates(self, step: Step) -> tuple[int, int] | None:
        """Resolve step coordinates to pixels."""
        # Try element text first
        if step.target:
            coords = self._device.find_element(step.target)
            if coords:
                return coords

        # Fall back to coordinates
        if step.coordinates:
            x, y = step.coordinates
            if step.coordinates_type == "percent":
                width, height = self._get_screen_size()
                return int(x * width / 100), int(y * height / 100)
            return int(x), int(y)

        return None

    # Action handlers

    def _action_tap(self, step: Step) -> str | None:
        """Execute tap action."""
        coords = self._resolve_coordinates(step)
        if coords is None:
            return f"Element '{step.target}' not found"

        self._device.tap(coords[0], coords[1])
        return None

    def _action_type(self, step: Step) -> str | None:
        """Execute type action."""
        text = step.text or step.target
        if not text:
            return "No text to type"

        self._device.type_text(text)
        return None

    def _action_swipe(self, step: Step) -> str | None:
        """Execute swipe action."""
        width, height = self._get_screen_size()

        # Default: center of screen
        cx, cy = width // 2, height // 2

        # Custom start point
        if step.from_coords:
            x, y = step.from_coords
            cx = int(x * width / 100)
            cy = int(y * height / 100)

        # Calculate end point based on direction
        distance = step.distance or 30  # Default 30%
        distance_px = int(distance * height / 100)

        direction = (step.direction or "up").lower()
        if direction == "up":
            self._device.swipe(cx, cy, cx, cy - distance_px)
        elif direction == "down":
            self._device.swipe(cx, cy, cx, cy + distance_px)
        elif direction == "left":
            self._device.swipe(cx, cy, cx - distance_px, cy)
        elif direction == "right":
            self._device.swipe(cx, cy, cx + distance_px, cy)
        else:
            return f"Unknown swipe direction: {direction}"

        return None

    def _action_wait(self, step: Step) -> str | None:
        """Execute wait action."""
        duration = step.timeout or 1.0
        time.sleep(duration)
        return None

    def _action_wait_for(self, step: Step) -> str | None:
        """Wait for element to appear."""
        target = step.target
        if not target:
            return "No element to wait for"

        timeout = step.timeout or self._config.timeouts.wait_for
        start = time.time()

        while time.time() - start < timeout:
            if self._device.find_element(target):
                return None
            time.sleep(0.5)

        return f"Timeout waiting for '{target}'"

    def _action_launch_app(self, step: Step) -> str | None:
        """Launch app."""
        package = step.target or self._config.app
        if not package:
            return "No app package specified"

        self._device.launch_app(package)
        return None

    def _action_terminate_app(self, step: Step) -> str | None:
        """Terminate app."""
        package = step.target or self._config.app
        if not package:
            return "No app package specified"

        self._device.terminate_app(package)
        return None

    def _action_back(self, step: Step) -> str | None:
        """Press back button."""
        self._device.press_key("BACK")
        return None

    def _action_verify_screen(self, step: Step) -> str | None:
        """Verify screen with AI."""
        # TODO: Implement with ScrcpyService for screenshots
        # For now, skip if no AI
        if not self._ai.is_available:
            return None

        return None  # Placeholder

    def _action_hide_keyboard(self, step: Step) -> str | None:
        """Hide keyboard."""
        self._device.press_key("BACK")
        return None
```

**Step 4: Run tests**

```bash
pytest tests/test_executor.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/executor.py tests/test_executor.py
git commit -m "feat: add TestExecutor with basic actions"
```

---

## Task 4: Report Generator

**Files:**
- Create: `mutcli/core/report.py`
- Create: `mutcli/templates/report.html`
- Test: `tests/test_report.py`

**Step 1: Write failing test**

```python
# tests/test_report.py
import json
from pathlib import Path

import pytest

from mutcli.core.report import ReportGenerator
from mutcli.core.executor import TestResult, StepResult


class TestReportGenerator:
    @pytest.fixture
    def test_result(self):
        """Sample test result."""
        return TestResult(
            name="login-test",
            status="passed",
            duration=5.2,
            steps=[
                StepResult(step_number=1, action="tap", status="passed", duration=0.5),
                StepResult(step_number=2, action="type", status="passed", duration=0.3),
                StepResult(step_number=3, action="verify_screen", status="passed", duration=1.0),
            ],
        )

    def test_generates_json_report(self, test_result, tmp_path):
        """Generates valid JSON report."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        json_path = generator.generate_json(test_result)

        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["test"] == "login-test"
        assert data["status"] == "passed"
        assert data["summary"]["total"] == 3
        assert data["summary"]["passed"] == 3

    def test_generates_html_report(self, test_result, tmp_path):
        """Generates HTML report."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        generator.generate_json(test_result)
        html_path = generator.generate_html(test_result)

        assert html_path.exists()
        content = html_path.read_text()
        assert "login-test" in content
        assert "passed" in content.lower()
```

**Step 2: Run test**

```bash
pytest tests/test_report.py -v
```

Expected: FAIL

**Step 3: Write implementation**

```python
# mutcli/core/report.py
"""Test report generation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mutcli.core.executor import StepResult, TestResult


class ReportGenerator:
    """Generate JSON and HTML test reports."""

    def __init__(self, output_dir: Path):
        """Initialize generator.

        Args:
            output_dir: Directory to write reports
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json(self, result: TestResult) -> Path:
        """Generate JSON report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.json
        """
        data = self._result_to_dict(result)

        path = self._output_dir / "report.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return path

    def generate_html(self, result: TestResult) -> Path:
        """Generate HTML report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.html
        """
        data = self._result_to_dict(result)
        html = self._render_html(data)

        path = self._output_dir / "report.html"
        with open(path, "w") as f:
            f.write(html)

        return path

    def _result_to_dict(self, result: TestResult) -> dict[str, Any]:
        """Convert TestResult to dictionary."""
        passed = sum(1 for s in result.steps if s.status == "passed")
        failed = sum(1 for s in result.steps if s.status == "failed")
        skipped = sum(1 for s in result.steps if s.status == "skipped")

        return {
            "test": result.name,
            "status": result.status,
            "duration": f"{result.duration:.1f}s",
            "timestamp": datetime.now().isoformat(),
            "error": result.error,
            "steps": [
                {
                    "number": s.step_number,
                    "action": s.action,
                    "status": s.status,
                    "duration": f"{s.duration:.1f}s",
                    "error": s.error,
                }
                for s in result.steps
            ],
            "summary": {
                "total": len(result.steps),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
        }

    def _render_html(self, data: dict[str, Any]) -> str:
        """Render HTML report from data."""
        status_color = {
            "passed": "#22c55e",
            "failed": "#ef4444",
            "error": "#ef4444",
            "skipped": "#f59e0b",
        }

        steps_html = ""
        for step in data["steps"]:
            color = status_color.get(step["status"], "#6b7280")
            icon = "✅" if step["status"] == "passed" else "❌" if step["status"] == "failed" else "⏭️"
            error_html = f'<div class="error">{step["error"]}</div>' if step["error"] else ""
            steps_html += f'''
            <div class="step">
                <span class="icon">{icon}</span>
                <span class="action">Step {step["number"]}: {step["action"]}</span>
                <span class="duration">{step["duration"]}</span>
                <span class="status" style="color: {color}">{step["status"]}</span>
                {error_html}
            </div>
            '''

        main_color = status_color.get(data["status"], "#6b7280")

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test Report: {data["test"]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #e2e8f0; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ color: #f8fafc; }}
        .summary {{ background: #1e293b; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 16px; }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: bold; }}
        .stat-label {{ color: #94a3b8; }}
        .status {{ font-weight: bold; }}
        .steps {{ background: #1e293b; padding: 20px; border-radius: 8px; }}
        .step {{ display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #334155; }}
        .step:last-child {{ border-bottom: none; }}
        .icon {{ font-size: 1.2rem; }}
        .action {{ flex: 1; }}
        .duration {{ color: #94a3b8; }}
        .error {{ color: #fca5a5; font-size: 0.9rem; margin-top: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Report</h1>

        <div class="summary">
            <div>
                <strong>Test:</strong> {data["test"]}<br>
                <strong>Status:</strong> <span class="status" style="color: {main_color}">{data["status"].upper()}</span><br>
                <strong>Duration:</strong> {data["duration"]}<br>
                <strong>Time:</strong> {data["timestamp"]}
            </div>

            <div class="summary-grid">
                <div class="stat">
                    <div class="stat-value">{data["summary"]["total"]}</div>
                    <div class="stat-label">Total</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #22c55e">{data["summary"]["passed"]}</div>
                    <div class="stat-label">Passed</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #ef4444">{data["summary"]["failed"]}</div>
                    <div class="stat-label">Failed</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #f59e0b">{data["summary"]["skipped"]}</div>
                    <div class="stat-label">Skipped</div>
                </div>
            </div>
        </div>

        <div class="steps">
            <h2>Steps</h2>
            {steps_html}
        </div>
    </div>
</body>
</html>'''
```

**Step 4: Run tests**

```bash
pytest tests/test_report.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/report.py tests/test_report.py
git commit -m "feat: add ReportGenerator for JSON/HTML reports"
```

---

## Task 5: Wire Up CLI Run Command

**Files:**
- Modify: `mutcli/cli.py`
- Test: Manual integration test

**Step 1: Update CLI**

```python
# Update the run command in mutcli/cli.py

@app.command()
def run(
    test_file: Path = typer.Argument(..., help="YAML test file to execute"),
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output directory"),
    junit: Path | None = typer.Option(None, "--junit", help="JUnit XML output path"),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose output"),
) -> None:
    """Execute a YAML test file."""
    from datetime import datetime
    from mutcli.core.config import ConfigLoader
    from mutcli.core.parser import TestParser, ParseError
    from mutcli.core.executor import TestExecutor
    from mutcli.core.report import ReportGenerator

    # Check test file exists
    if not test_file.exists():
        console.print(f"[red]Error:[/red] Test file not found: {test_file}")
        raise typer.Exit(2)

    # Load config
    try:
        config = ConfigLoader.load(require_api_key=True)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)

    # Override device from CLI
    if device:
        config.device = device

    # Determine device
    if not config.device:
        # Try to find a device
        from mutcli.core.device_controller import DeviceController
        devices = DeviceController.list_devices()
        if not devices:
            console.print("[red]Error:[/red] No devices found. Run 'mut devices' to check.")
            raise typer.Exit(2)
        config.device = devices[0]["id"]
        console.print(f"[dim]Using device: {config.device}[/dim]")

    # Parse test file
    try:
        test = TestParser.parse(test_file)
    except ParseError as e:
        console.print(f"[red]Parse error:[/red] {e}")
        raise typer.Exit(2)

    console.print(f"[blue]Running test:[/blue] {test_file}")

    # Execute test
    executor = TestExecutor(device_id=config.device, config=config)
    result = executor.execute_test(test)

    # Generate report
    test_name = test_file.stem
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Determine output directory
    if output:
        report_dir = output
    else:
        # Default: tests/{name}/reports/{timestamp}/
        report_dir = test_file.parent / "reports" / timestamp

    generator = ReportGenerator(report_dir)
    json_path = generator.generate_json(result)
    html_path = generator.generate_html(result)

    # Show result
    if result.status == "passed":
        console.print(f"[green]✅ PASSED[/green] ({result.duration:.1f}s)")
    else:
        console.print(f"[red]❌ FAILED[/red] ({result.duration:.1f}s)")
        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")

    console.print(f"\n[dim]Report: {html_path}[/dim]")

    # Generate JUnit if requested
    if junit:
        _generate_junit(result, junit)
        console.print(f"[dim]JUnit: {junit}[/dim]")

    # Exit code
    if result.status == "passed":
        raise typer.Exit(0)
    else:
        raise typer.Exit(1)


def _generate_junit(result, path: Path) -> None:
    """Generate JUnit XML report."""
    from xml.etree.ElementTree import Element, SubElement, tostring

    testsuite = Element("testsuite", {
        "name": result.name,
        "tests": str(len(result.steps)),
        "failures": str(sum(1 for s in result.steps if s.status == "failed")),
        "time": str(result.duration),
    })

    for step in result.steps:
        testcase = SubElement(testsuite, "testcase", {
            "name": f"Step {step.step_number}: {step.action}",
            "time": str(step.duration),
        })

        if step.status == "failed":
            failure = SubElement(testcase, "failure", {"message": step.error or "Failed"})
            failure.text = step.error or ""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(tostring(testsuite))
```

**Step 2: Test manually**

Create a test file:
```yaml
# tests/demo/test.yaml
config:
  app: com.android.calculator2

setup:
  - launch_app

steps:
  - tap: "5"
  - tap: "+"
  - tap: "3"
  - tap: "="

teardown:
  - terminate_app
```

Run:
```bash
mut run tests/demo/test.yaml
```

**Step 3: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat: wire up run command with full execution pipeline"
```

---

## Task 6: Update Core __init__.py

**Files:**
- Modify: `mutcli/core/__init__.py`

**Step 1: Export new modules**

```python
# mutcli/core/__init__.py
"""Core mut functionality."""

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.config import ConfigLoader, MutConfig
from mutcli.core.device_controller import DeviceController
from mutcli.core.executor import TestExecutor, TestResult, StepResult
from mutcli.core.parser import TestParser, ParseError
from mutcli.core.report import ReportGenerator
from mutcli.core.scrcpy_service import ScrcpyService

__all__ = [
    "AIAnalyzer",
    "ConfigLoader",
    "MutConfig",
    "DeviceController",
    "TestExecutor",
    "TestResult",
    "StepResult",
    "TestParser",
    "ParseError",
    "ReportGenerator",
    "ScrcpyService",
]
```

**Step 2: Commit**

```bash
git add mutcli/core/__init__.py
git commit -m "chore: export new core modules"
```

---

## Summary

Phase 1 complete. `mut run` now:
1. ✅ Loads layered configuration
2. ✅ Parses YAML test files (3 syntax levels)
3. ✅ Executes basic actions (tap, type, swipe, wait, etc.)
4. ✅ Generates JSON + HTML reports
5. ✅ Supports --junit for CI

**Not yet implemented:**
- Video recording during test
- verify_screen with AI
- Conditionals (if_present, if_screen)
- Smart error suggestions

These will be added in Phase 1.5 before moving to Phase 2 (Recording).
