"""Tests for ConfigLoader."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mutcli.core.config import ConfigLoader


class TestConfigLoader:
    """Test ConfigLoader behavior."""

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


class TestConfigDefaults:
    """Test default configuration values."""

    def test_timeout_defaults(self):
        """Verify all timeout defaults are set correctly."""
        with patch.object(Path, "exists", return_value=False):
            config = ConfigLoader.load()

        assert config.timeouts.tap == 5.0
        assert config.timeouts.wait_for == 10.0
        assert config.timeouts.verify_screen == 10.0
        assert config.timeouts.type == 3.0
        assert config.timeouts.swipe == 3.0

    def test_retry_defaults(self):
        """Verify retry defaults are set correctly."""
        with patch.object(Path, "exists", return_value=False):
            config = ConfigLoader.load()

        assert config.retry.count == 2
        assert config.retry.delay == 1.0

    def test_optional_fields_are_none_by_default(self):
        """Optional fields should be None when not specified."""
        # Clear environment to ensure no API key is present
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Path, "exists", return_value=False):
                config = ConfigLoader.load()

            assert config.app is None
            assert config.device is None
            assert config.google_api_key is None


class TestConfigMerging:
    """Test configuration merging from multiple sources."""

    def test_global_config_overrides_defaults(self, tmp_path):
        """Global ~/.mut.yaml overrides defaults."""
        global_config = tmp_path / ".mut.yaml"
        global_config.write_text("""
timeouts:
  tap: 7
retry:
  count: 3
""")

        with patch("mutcli.core.config.GLOBAL_CONFIG", global_config):
            with patch("mutcli.core.config.PROJECT_CONFIG", Path("/nonexistent")):
                config = ConfigLoader.load()

        assert config.timeouts.tap == 7.0
        assert config.retry.count == 3
        assert config.timeouts.wait_for == 10.0  # Still default

    def test_project_overrides_global(self, tmp_path):
        """Project config overrides global config."""
        global_config = tmp_path / "global.mut.yaml"
        global_config.write_text("""
app: global.app
timeouts:
  tap: 7
""")

        project_config = tmp_path / "project.mut.yaml"
        project_config.write_text("""
app: project.app
""")

        with patch("mutcli.core.config.GLOBAL_CONFIG", global_config):
            with patch("mutcli.core.config.PROJECT_CONFIG", project_config):
                config = ConfigLoader.load()

        assert config.app == "project.app"
        assert config.timeouts.tap == 7.0  # From global (project didn't override)

    def test_env_overrides_all(self, tmp_path):
        """Environment variables have highest priority."""
        project_config = tmp_path / ".mut.yaml"
        project_config.write_text("""
device: config-device
verbose: false
""")

        env_vars = {
            "MUT_DEVICE": "env-device",
            "MUT_VERBOSE": "true",
            "GOOGLE_API_KEY": "test-key",
        }

        with patch("mutcli.core.config.PROJECT_CONFIG", project_config):
            with patch.dict(os.environ, env_vars, clear=True):
                config = ConfigLoader.load()

        assert config.device == "env-device"
        assert config.verbose is True
        assert config.google_api_key == "test-key"


class TestConfigValidation:
    """Test configuration validation."""

    def test_api_key_from_env(self):
        """Should read GOOGLE_API_KEY from environment."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "my-api-key"}):
                config = ConfigLoader.load()

        assert config.google_api_key == "my-api-key"

    def test_verbose_parsing(self, tmp_path):
        """Should parse verbose flag correctly."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("verbose: true")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            config = ConfigLoader.load()

        assert config.verbose is True

    def test_verbose_from_env(self):
        """Should parse MUT_VERBOSE from environment."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"MUT_VERBOSE": "1"}):
                config = ConfigLoader.load()

        assert config.verbose is True


class TestConfigErrorHandling:
    """Test configuration error handling for edge cases."""

    def test_malformed_yaml_returns_defaults(self, tmp_path):
        """Malformed YAML should be ignored, returning defaults."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("""
this is not valid yaml:
  - [unclosed bracket
  indentation: wrong
""")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                config = ConfigLoader.load()

        # Should get all defaults
        assert config.timeouts.tap == 5.0
        assert config.retry.count == 2
        assert config.app is None

    def test_null_values_use_defaults(self, tmp_path):
        """YAML with null values should use defaults instead of crashing."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("""
app: com.example.app
timeouts:
  tap: null
  wait_for: ~
  verify_screen: null
retry:
  count: null
  delay: ~
verbose: null
""")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                config = ConfigLoader.load()

        # Non-null values should be preserved
        assert config.app == "com.example.app"
        # Null values should fall back to defaults
        assert config.timeouts.tap == 5.0
        assert config.timeouts.wait_for == 10.0
        assert config.timeouts.verify_screen == 10.0
        assert config.retry.count == 2
        assert config.retry.delay == 1.0
        assert config.verbose is False

    def test_wrong_types_use_defaults(self, tmp_path):
        """YAML with wrong types should use defaults instead of crashing."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("""
timeouts:
  tap: "not a number"
  wait_for: [1, 2, 3]
  verify_screen: {key: value}
retry:
  count: "three"
  delay: invalid
verbose: "maybe"
""")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                config = ConfigLoader.load()

        # Invalid types should fall back to defaults
        assert config.timeouts.tap == 5.0
        assert config.timeouts.wait_for == 10.0
        assert config.timeouts.verify_screen == 10.0
        assert config.retry.count == 2
        assert config.retry.delay == 1.0
        # "maybe" is a string, _parse_bool returns False for non-truthy strings
        assert config.verbose is False

    def test_verbose_string_parsing_from_yaml(self, tmp_path):
        """YAML verbose as string should be parsed correctly."""
        for truthy_value in ["true", "True", "TRUE", "1", "yes", "on"]:
            config_file = tmp_path / ".mut.yaml"
            config_file.write_text(f"verbose: {truthy_value}")

            with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
                with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                    config = ConfigLoader.load()

            assert config.verbose is True, f"Failed for value: {truthy_value}"

    def test_verbose_false_string_parsing_from_yaml(self, tmp_path):
        """YAML verbose as false string should be parsed correctly."""
        for falsy_value in ["false", "False", "0", "no", "off", "random"]:
            config_file = tmp_path / ".mut.yaml"
            config_file.write_text(f"verbose: {falsy_value}")

            with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
                with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                    config = ConfigLoader.load()

            assert config.verbose is False, f"Failed for value: {falsy_value}"

    def test_empty_yaml_file_returns_defaults(self, tmp_path):
        """Empty YAML file should return defaults."""
        config_file = tmp_path / ".mut.yaml"
        config_file.write_text("")

        with patch("mutcli.core.config.PROJECT_CONFIG", config_file):
            with patch("mutcli.core.config.GLOBAL_CONFIG", Path("/nonexistent")):
                config = ConfigLoader.load()

        assert config.timeouts.tap == 5.0
        assert config.retry.count == 2
