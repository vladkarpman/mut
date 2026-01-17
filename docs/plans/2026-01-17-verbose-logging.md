# Verbose Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable DEBUG-level file logging for all mut commands via `MUT_VERBOSE=true` in `.env` or environment.

**Architecture:** Add `setup_logging()` to config module, call it early in each CLI command. For `mut run`, create timestamped run folders. Loggers already exist in modules - just need to enable them.

**Tech Stack:** Python logging, existing `python-dotenv` (already installed)

**Design Doc:** `docs/plans/2026-01-17-verbose-logging-design.md`

---

## Task 1: Add setup_logging Function

**Files:**
- Modify: `mutcli/core/config.py`
- Create: `tests/test_logging_setup.py`

**Step 1: Write the failing test**

```python
"""Tests for logging setup."""

import logging
from pathlib import Path

import pytest

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_logging_setup.py -v`
Expected: FAIL with "cannot import name 'setup_logging'"

**Step 3: Write the implementation**

Add to `mutcli/core/config.py` at the end:

```python
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

    import logging

    log_file = log_dir / "debug.log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create file handler
    handler = logging.FileHandler(log_file, mode="w")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Configure root mut logger
    mut_logger = logging.getLogger("mut")
    mut_logger.setLevel(logging.DEBUG)
    mut_logger.addHandler(handler)

    return log_file
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_logging_setup.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add mutcli/core/config.py tests/test_logging_setup.py
git commit -m "feat: add setup_logging function for verbose file logging"
```

---

## Task 2: Enable Logging in Record Command

**Files:**
- Modify: `mutcli/cli.py` (record command, around line 170)

**Step 1: Read current record command**

Understand where to add logging setup call.

**Step 2: Add logging setup to record command**

After config is loaded, before any processing:

```python
from mutcli.core.config import ConfigLoader, setup_logging

# ... existing code ...

# Load config
config = ConfigLoader.load()

# Setup verbose logging if enabled
log_file = setup_logging(verbose=config.verbose, log_dir=test_dir)
if log_file:
    console.print(f"[dim]Verbose logging → {log_file}[/dim]")
```

**Step 3: Manual test**

```bash
# Create .env with verbose enabled
echo "MUT_VERBOSE=true" > .env

# Run record (Ctrl+C to stop early)
mut record test_logging --app com.google.android.calculator

# Check log file exists
cat tests/test_logging/debug.log | head -20
```

**Step 4: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat: enable verbose logging in record command"
```

---

## Task 3: Create Run Folder Structure

**Files:**
- Modify: `mutcli/cli.py` (run command)
- Create: `tests/test_run_folders.py`

**Step 1: Write the failing test**

```python
"""Tests for run folder creation."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


class TestRunFolderCreation:
    """Tests for timestamped run folder creation."""

    def test_creates_runs_directory(self, tmp_path):
        """Creates runs/ subdirectory if missing."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        run_folder = _create_run_folder(test_dir)

        assert (test_dir / "runs").exists()
        assert run_folder.parent == test_dir / "runs"

    def test_creates_timestamped_folder(self, tmp_path):
        """Creates folder with timestamp format."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        with patch("mutcli.cli.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 17, 14, 30, 25)
            run_folder = _create_run_folder(test_dir)

        assert run_folder.name == "2026-01-17_14-30-25"

    def test_run_folder_is_created(self, tmp_path):
        """Run folder directory actually exists."""
        from mutcli.cli import _create_run_folder

        test_dir = tmp_path / "my_test"
        test_dir.mkdir()

        run_folder = _create_run_folder(test_dir)

        assert run_folder.exists()
        assert run_folder.is_dir()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_run_folders.py -v`
Expected: FAIL with "cannot import name '_create_run_folder'"

**Step 3: Write the implementation**

Add to `mutcli/cli.py` (near top, after imports):

```python
from datetime import datetime

def _create_run_folder(test_dir: Path) -> Path:
    """Create timestamped run folder for test execution.

    Args:
        test_dir: Test directory (e.g., tests/my_test/)

    Returns:
        Path to created run folder (e.g., tests/my_test/runs/2026-01-17_14-30-25/)
    """
    runs_dir = test_dir / "runs"
    runs_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_folder = runs_dir / timestamp
    run_folder.mkdir()

    return run_folder
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_run_folders.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add mutcli/cli.py tests/test_run_folders.py
git commit -m "feat: add _create_run_folder for timestamped run directories"
```

---

## Task 4: Enable Logging in Run Command

**Files:**
- Modify: `mutcli/cli.py` (run command)

**Step 1: Integrate run folder and logging into run command**

In the `run` command, after loading config and before executing:

```python
from mutcli.core.config import ConfigLoader, setup_logging

# ... existing code ...

# Determine test directory from test file path
test_dir = test_file.parent

# Create run folder for this execution
run_folder = _create_run_folder(test_dir)

# Setup verbose logging if enabled
log_file = setup_logging(verbose=config.verbose, log_dir=run_folder)
if log_file:
    console.print(f"[dim]Verbose logging → {log_file}[/dim]")
```

**Step 2: Manual test**

```bash
# Ensure .env has verbose enabled
echo "MUT_VERBOSE=true" > .env

# Run a test
mut run tests/calculator_demo/test.yaml

# Check run folder was created with log
ls tests/calculator_demo/runs/
cat tests/calculator_demo/runs/*/debug.log | head -20
```

**Step 3: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat: enable verbose logging in run command with timestamped folders"
```

---

## Task 5: Add More Debug Logging to Executor

**Files:**
- Modify: `mutcli/core/executor.py`

**Step 1: Read current executor to find logging opportunities**

Look for places where DEBUG logs would help: step execution, element search, retries.

**Step 2: Add debug logging calls**

Add logging at key points:

```python
logger = logging.getLogger("mut.executor")

# In execute_step or similar:
logger.debug(f"Executing step {step.index}: {step.action}")
logger.debug(f"Element search for '{element}' found at ({x}, {y})")
logger.debug(f"Step {step.index} completed in {elapsed:.2f}s")
logger.debug(f"Retry {attempt}/{max_retries} for step {step.index}")
```

**Step 3: Manual test**

Run a test with verbose and check logs contain executor details.

**Step 4: Commit**

```bash
git add mutcli/core/executor.py
git commit -m "feat: add debug logging to executor"
```

---

## Task 6: Verify End-to-End

**Files:** None (manual testing)

**Step 1: Test recording with verbose**

```bash
MUT_VERBOSE=true mut record e2e_verbose_test --app com.google.android.calculator
# Perform some taps, then stop

# Verify log file
cat tests/e2e_verbose_test/debug.log
# Should see: touch events, AI calls, frame extraction
```

**Step 2: Test run with verbose**

```bash
MUT_VERBOSE=true mut run tests/e2e_verbose_test/test.yaml

# Verify run folder and log
ls tests/e2e_verbose_test/runs/
cat tests/e2e_verbose_test/runs/*/debug.log
# Should see: step execution, element search
```

**Step 3: Run full test suite**

```bash
pytest
ruff check .
mypy mutcli/
```

**Step 4: Final commit if needed**

```bash
git add -A
git commit -m "test: verify verbose logging end-to-end"
```

---

## Summary

| Task | Description | New Files |
|------|-------------|-----------|
| 1 | Add setup_logging function | `tests/test_logging_setup.py` |
| 2 | Enable logging in record command | - |
| 3 | Create run folder structure | `tests/test_run_folders.py` |
| 4 | Enable logging in run command | - |
| 5 | Add debug logging to executor | - |
| 6 | End-to-end verification | - |
