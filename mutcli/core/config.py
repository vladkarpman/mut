"""Configuration loader with layered priority.

Priority order (highest to lowest):
1. Environment variables (MUT_DEVICE, MUT_VERBOSE, GOOGLE_API_KEY)
2. Project config (.mut.yaml in current directory)
3. Global config (~/.mut.yaml)
4. Default values
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Config file paths
GLOBAL_CONFIG = Path.home() / ".mut.yaml"
PROJECT_CONFIG = Path.cwd() / ".mut.yaml"


def _safe_float(value: Any, default: float) -> float:
    """Convert value to float, returning default if None or invalid."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    """Convert value to int, returning default if None or invalid."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parse boolean value from various formats.

    Handles:
    - None -> default
    - bool -> as-is
    - str -> "true", "1", "yes", "on" are True
    - other -> bool(value)
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


@dataclass
class TimeoutConfig:
    """Timeout settings for various operations."""

    tap: float = 5.0
    wait_for: float = 10.0
    verify_screen: float = 10.0
    type: float = 3.0
    swipe: float = 3.0


@dataclass
class RetryConfig:
    """Retry settings for failed operations."""

    count: int = 2
    delay: float = 1.0


def _parse_duration(value: Any, default: float) -> float:
    """Parse duration value from string (e.g., '5s', '500ms') or number.

    Args:
        value: Duration as string ('5s', '500ms', '1.5s') or number (seconds)
        default: Default value if parsing fails

    Returns:
        Duration in seconds as float
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value.endswith("ms"):
            try:
                return float(value[:-2]) / 1000
            except ValueError:
                return default
        if value.endswith("s"):
            try:
                return float(value[:-1])
            except ValueError:
                return default
        # Try parsing as plain number
        try:
            return float(value)
        except ValueError:
            return default
    return default


@dataclass
class ResilienceConfig:
    """Resilience settings for intelligent test execution."""

    # Layer 1: Smart waits
    implicit_wait: float = 5.0  # Seconds to wait for elements
    poll_interval: float = 0.5  # Seconds between retry attempts
    stability_frames: int = 2  # Consecutive identical frames before action

    # Layer 2: AI recovery
    ai_recovery: bool = True  # Enable AI-powered failure recovery
    ai_retry_limit: int = 1  # Max AI-suggested retries


@dataclass
class MutConfig:
    """Main configuration for mut CLI."""

    # Optional fields
    app: str | None = None
    device: str | None = None
    google_api_key: str | None = None
    verbose: bool = False

    # Nested configs with defaults
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)


class ConfigLoader:
    """Loads and merges configuration from multiple sources."""

    @classmethod
    def load(cls, require_api_key: bool = False) -> MutConfig:
        """Load configuration with layered priority.

        Args:
            require_api_key: If True, raises ValueError when GOOGLE_API_KEY is not set.

        Returns:
            Merged MutConfig instance.

        Raises:
            ValueError: If require_api_key is True and no API key is found.
        """
        # Start with defaults
        config_dict: dict[str, Any] = {}

        # Layer 1: Global config (~/.mut.yaml)
        if GLOBAL_CONFIG.exists():
            global_data = cls._load_yaml(GLOBAL_CONFIG)
            config_dict = cls._deep_merge(config_dict, global_data)

        # Layer 2: Project config (.mut.yaml)
        if PROJECT_CONFIG.exists():
            project_data = cls._load_yaml(PROJECT_CONFIG)
            config_dict = cls._deep_merge(config_dict, project_data)

        # Layer 3: Environment variables (highest priority)
        env_overrides = cls._get_env_overrides()
        config_dict = cls._deep_merge(config_dict, env_overrides)

        # Build the config object
        config = cls._build_config(config_dict)

        # Validate API key requirement
        if require_api_key and not config.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required. "
                "Set it with: export GOOGLE_API_KEY='your-api-key'"
            )

        return config

    @classmethod
    def _load_yaml(cls, path: Path) -> dict[str, Any]:
        """Load YAML file safely."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except (yaml.YAMLError, OSError):
            return {}

    @classmethod
    def _get_env_overrides(cls) -> dict[str, Any]:
        """Get configuration overrides from environment variables."""
        overrides: dict[str, Any] = {}

        # Direct mappings
        if "MUT_DEVICE" in os.environ:
            overrides["device"] = os.environ["MUT_DEVICE"]

        if "GOOGLE_API_KEY" in os.environ:
            overrides["google_api_key"] = os.environ["GOOGLE_API_KEY"]

        # Boolean parsing for verbose
        if "MUT_VERBOSE" in os.environ:
            overrides["verbose"] = _parse_bool(os.environ["MUT_VERBOSE"])

        # Resilience overrides
        resilience_overrides: dict[str, Any] = {}
        if "MUT_IMPLICIT_WAIT" in os.environ:
            resilience_overrides["implicit_wait"] = os.environ["MUT_IMPLICIT_WAIT"]
        if "MUT_AI_RECOVERY" in os.environ:
            resilience_overrides["ai_recovery"] = os.environ["MUT_AI_RECOVERY"]
        if resilience_overrides:
            overrides["resilience"] = resilience_overrides

        return overrides

    @classmethod
    def _deep_merge(cls, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    @classmethod
    def _build_config(cls, config_dict: dict[str, Any]) -> MutConfig:
        """Build MutConfig from dictionary."""
        # Extract nested configs
        timeouts_dict = config_dict.get("timeouts", {})
        retry_dict = config_dict.get("retry", {})
        resilience_dict = config_dict.get("resilience", {})

        # Build TimeoutConfig
        timeouts = TimeoutConfig(
            tap=_safe_float(timeouts_dict.get("tap"), 5.0),
            wait_for=_safe_float(timeouts_dict.get("wait_for"), 10.0),
            verify_screen=_safe_float(timeouts_dict.get("verify_screen"), 10.0),
            type=_safe_float(timeouts_dict.get("type"), 3.0),
            swipe=_safe_float(timeouts_dict.get("swipe"), 3.0),
        )

        # Build RetryConfig
        retry = RetryConfig(
            count=_safe_int(retry_dict.get("count"), 2),
            delay=_safe_float(retry_dict.get("delay"), 1.0),
        )

        # Build ResilienceConfig
        resilience = ResilienceConfig(
            implicit_wait=_parse_duration(resilience_dict.get("implicit_wait"), 5.0),
            poll_interval=_parse_duration(resilience_dict.get("poll_interval"), 0.5),
            stability_frames=_safe_int(resilience_dict.get("stability_frames"), 2),
            ai_recovery=_parse_bool(resilience_dict.get("ai_recovery"), True),
            ai_retry_limit=_safe_int(resilience_dict.get("ai_retry_limit"), 1),
        )

        # Build main config
        return MutConfig(
            app=config_dict.get("app"),
            device=config_dict.get("device"),
            google_api_key=config_dict.get("google_api_key"),
            verbose=_parse_bool(config_dict.get("verbose"), False),
            timeouts=timeouts,
            retry=retry,
            resilience=resilience,
        )


def setup_logging(verbose: bool, log_dir: Path | None) -> Path | None:
    """Configure file-based DEBUG logging.

    Args:
        verbose: Enable logging when True
        log_dir: Directory to write debug.log

    Returns:
        Path to log file if created, None otherwise
    """
    if not verbose or log_dir is None:
        return None

    log_file = log_dir / "debug.log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create file handler
    handler = logging.FileHandler(log_file, mode="w")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Configure root mut logger (clear existing handlers to prevent duplicates)
    mut_logger = logging.getLogger("mut")
    mut_logger.handlers.clear()
    mut_logger.setLevel(logging.DEBUG)
    mut_logger.addHandler(handler)

    return log_file
