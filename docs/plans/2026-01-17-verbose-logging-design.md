# Verbose Logging Design

**Date:** 2026-01-17
**Status:** Approved
**Goal:** Enable DEBUG-level file logging for all mut commands to aid debugging

## Summary

| Aspect | Decision |
|--------|----------|
| Scope | All mut commands (record, run, stop) |
| Output | File only (`debug.log` in appropriate directory) |
| Trigger | `.env` file, env var `MUT_VERBOSE=true`, or `.mut.yaml` config |
| Detail | DEBUG level (raw ADB, API calls, timings, coordinates) |

## Log File Locations

### Recording (`mut record my_test`)

```
tests/my_test/
├── video.mp4
├── touch_events.json
├── analysis.json
├── debug.log          ← Recording logs here
└── screenshots/
```

Logs live alongside other recording artifacts since they're part of the same session.

### Test Execution (`mut run tests/my_test.yaml`)

```
tests/my_test/
├── test.yaml          # Static test definition
└── runs/
    └── 2026-01-17_14-30-25/
        ├── debug.log          ← Run logs here
        └── screenshots/       ← Future: failure screenshots
```

Each run gets a timestamped folder (`YYYY-MM-DD_HH-MM-SS` format). This enables comparing logs across runs and preserves history.

## Enabling Verbose Mode

**Configuration sources (priority order):**
1. `MUT_VERBOSE=true` in shell environment (highest)
2. `.env` file in current directory
3. `verbose: true` in `.mut.yaml` config

**Usage examples:**

```bash
# Option 1: .env file (recommended for development)
echo "MUT_VERBOSE=true" >> .env
mut record my_test

# Option 2: Shell environment
MUT_VERBOSE=true mut run tests/my_test.yaml

# Option 3: Config file (.mut.yaml)
verbose: true
```

**Console feedback:** When verbose is enabled, show:
```
[dim]Verbose logging enabled → tests/my_test/debug.log[/dim]
```

## Log Format

```
2026-01-17 14:30:25.123 [DEBUG] mut.touch    | Touch DOWN at raw=(1234, 5678) → screen=(540, 1200)
2026-01-17 14:30:25.456 [DEBUG] mut.ai       | API request: analyze_tap with 3 frames (245KB)
2026-01-17 14:30:26.789 [DEBUG] mut.ai       | API response: element_text="Login", 1.3s
2026-01-17 14:30:27.001 [INFO]  mut.executor | Step 3: tap "Login" - PASSED
```

## Log Content by Module

| Module | DEBUG content |
|--------|---------------|
| `mut.touch` | Raw coordinates, gesture classification, trajectory points |
| `mut.ai` | API request/response summaries, token counts, latency |
| `mut.scrcpy` | Connection events, frame buffer stats, video encoding |
| `mut.frame_extractor` | Frame timestamps, extraction timing, file sizes |
| `mut.executor` | Step execution, element search results, retry attempts |
| `mut.recorder` | ADB commands, screen capture events |

**Security:** API keys are never logged. API responses are summarized, not full JSON dumps.

## Implementation

### New Dependency

- `python-dotenv` - Load `.env` files before config

### Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `python-dotenv` dependency |
| `mutcli/core/config.py` | Load `.env`, add `setup_logging()` function |
| `mutcli/cli.py` | Call `setup_logging()` early in each command |
| `mutcli/core/executor.py` | Add DEBUG logs for step execution |

### setup_logging() Function

```python
def setup_logging(verbose: bool, log_path: Path | None) -> None:
    """Configure logging based on verbose setting.

    Args:
        verbose: Enable DEBUG logging to file
        log_path: Where to write debug.log
    """
    if not verbose or not log_path:
        return  # Logging stays disabled (default)

    log_file = log_path / "debug.log"
    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Enable all mut.* loggers
    logging.getLogger("mut").setLevel(logging.DEBUG)
    logging.getLogger("mut").addHandler(handler)
```

### Run Folder Creation

For `mut run`:
1. Create `runs/` directory if missing
2. Create timestamped subfolder at start of run
3. Pass path to `setup_logging()`
