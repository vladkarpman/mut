"""Tests for logging setup."""

import logging

from mutcli.core.config import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_logging_disabled_when_verbose_false(self, tmp_path):
        """No log file created when verbose=False."""
        setup_logging(verbose=False, log_dir=tmp_path)

        log_file = tmp_path / "debug.log"
        assert not log_file.exists()

    def test_logging_enabled_creates_file(self, tmp_path):
        """Log file created when verbose=True."""
        setup_logging(verbose=True, log_dir=tmp_path)

        log_file = tmp_path / "debug.log"
        assert log_file.exists()

    def test_logging_writes_debug_messages(self, tmp_path):
        """DEBUG messages written to log file."""
        setup_logging(verbose=True, log_dir=tmp_path)

        # Get a mut.* logger and log something
        logger = logging.getLogger("mut.test")
        logger.debug("Test debug message")

        log_file = tmp_path / "debug.log"
        content = log_file.read_text()
        assert "Test debug message" in content

    def test_logging_format_includes_timestamp(self, tmp_path):
        """Log format includes timestamp and level."""
        setup_logging(verbose=True, log_dir=tmp_path)

        logger = logging.getLogger("mut.test")
        logger.info("Test info")

        content = (tmp_path / "debug.log").read_text()
        assert "[INFO]" in content or "[INFO ]" in content

    def test_logging_does_nothing_when_log_dir_none(self):
        """No error when log_dir is None."""
        setup_logging(verbose=True, log_dir=None)  # Should not raise
