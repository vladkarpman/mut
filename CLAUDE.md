# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mut** (Mobile UI Testing) - Standalone Python CLI for running YAML-based mobile UI tests. Designed for CI/CD, local development, and scripting without Claude Code dependency.

## Development Commands

```bash
# Install
pip install -e ".[dev]"

# Run CLI
mut devices                     # List connected devices
mut run tests/login.yaml        # Execute test
mut record my-test --app com.example.app  # Start recording
mut analyze my-test             # Analyze recording, open approval UI

# Tests
pytest                          # Run all tests
pytest tests/test_executor.py   # Single file
pytest -k "test_tap"            # By pattern

# Code quality
ruff check .                    # Lint
ruff check . --fix              # Auto-fix
mypy mutcli/                    # Type check

# Build
python -m build
```

## Architecture

```
mutcli/
├── cli.py                     # Typer commands (run, record, analyze, preview, devices, report)
├── __init__.py                # Version
├── __main__.py                # Entry point
├── models/
│   └── test.py                # Test/Step data models
├── core/
│   ├── config.py              # ConfigLoader, setup_logging
│   ├── device_controller.py   # Touch gestures via ADB or scrcpy injection; ADB: type, elements
│   ├── scrcpy_service.py      # MYScrcpy: screenshots, video recording, touch injection
│   ├── ai_analyzer.py         # Gemini 2.5 Flash: verify_screen, find_element
│   ├── ai_recovery.py         # AI-based error recovery suggestions
│   ├── executor.py            # TestExecutor: runs YAML tests, captures action screenshots
│   ├── step_verifier.py       # StepVerifier: parallel AI analysis of executed steps
│   ├── parser.py              # YAML test file parser
│   ├── recorder.py            # Recording session manager
│   ├── interactive_recorder.py # Interactive recording with GUI window
│   ├── recording_window.py    # Recording control window UI
│   ├── touch_monitor.py       # ADB getevent touch capture
│   ├── touch_injector.py      # Touch injection via scrcpy
│   ├── adb_state_monitor.py   # Monitor ADB state (keyboard, activity, window)
│   ├── frame_extractor.py     # Extract frames from video at timestamps
│   ├── step_analyzer.py       # AI analysis of recorded steps
│   ├── typing_detector.py     # Detect typing from touch patterns
│   ├── step_collapsing.py     # Collapse multiple taps into type actions
│   ├── verification_suggester.py  # Suggest verify_screen descriptions
│   ├── yaml_generator.py      # Generate YAML from analyzed steps
│   ├── preview_server.py      # HTTP server for approval UI
│   ├── analysis_io.py         # Save/load analysis JSON
│   ├── report.py              # ReportGenerator: JSON + HTML with gesture visualization
│   ├── report_server.py       # Local HTTP server for viewing reports
│   ├── console_reporter.py    # Console output formatting for test results
│   ├── screenshot_saver.py    # Save screenshots to files
│   ├── ui_element_parser.py   # Parse UI hierarchy XML
│   └── ui_hierarchy_monitor.py # Monitor UI hierarchy during recording
├── templates/
│   ├── approval.html          # Browser-based approval UI
│   └── report.html            # Test report template with gesture indicators
└── utils/                     # Shared utilities
```

### Key Patterns

**Touch gestures**: `DeviceController` supports two modes for gestures (tap, swipe, long_press):
- **ADB mode** (default): Uses `adb shell input` commands. Simple and reliable.
- **Scrcpy mode**: Uses scrcpy control injection. Set `use_adb=False` when creating controller.

Text input always uses ADB. `ScrcpyService` provides fast screenshots (~50ms via frame buffer), video recording, and optional touch injection.

**Hybrid AI verification**:
- `verify_screen` - Real-time AI call during test execution. Returns error if screen doesn't match.
- `if_screen` - Real-time AI call for branching decisions.

**Post-execution AI analysis**: After test completes, `StepVerifier` analyzes all steps in parallel using before/after screenshots. Provides AI-verified outcomes and suggestions for failures.

**Frame buffer**: `ScrcpyService` maintains a 10-frame circular buffer. `screenshot()` returns the latest frame instantly without triggering capture.

**Action screenshot capture**: `TestExecutor` captures screenshots at key moments during gestures:
- tap/double_tap: screenshot_action captured immediately after touch
- swipe: screenshot_action at start, screenshot_action_end near end of swipe
- long_press: screenshot_action at press start, screenshot_action_end while held

**Touch visualization**: During video recording, `show_touches` is enabled to display native touch indicators on screen. Original setting is restored after recording.

**Recording pipeline** (getevent-based, touch physical device):
1. `Recorder` orchestrates recording session
2. `TouchMonitor` captures touch events via ADB getevent
3. `ScrcpyService` records video with timestamps
4. `UIHierarchyMonitor` captures UI dumps during recording (when `--app` provided)
5. `FrameExtractor` extracts before/after frames for each touch
6. `StepAnalyzer` uses AI to describe each step (with UI hierarchy context)
7. `TypingDetector` + `StepCollapsing` convert tap sequences to type actions
8. `PreviewServer` serves approval UI for editing
9. `YamlGenerator` exports final test file

**Test execution pipeline**:
1. `TestExecutor` runs each step, capturing before/after/action screenshots
2. `StepVerifier` runs parallel AI analysis on all steps post-execution
3. `ReportGenerator` creates JSON results and HTML report with gesture visualization

## External Dependencies

- `adb` in PATH (device communication, text input)
- `scrcpy` 3.x (required for test execution - screenshots, video, touch injection)
- `GOOGLE_API_KEY` env var (optional, for AI features)

## YAML Test Format

```yaml
config:
  app: com.example.app

setup:
  - terminate_app
  - launch_app
  - wait: 2s

tests:
  - name: Login flow
    steps:
      - tap: "Email"           # Find element by text
      - tap: [540, 1200]       # Or coordinates
      - type: "user@test.com"
      - tap: "Sign In"
      - verify_screen: "Welcome screen"  # Deferred AI check
      - if_screen: "2FA prompt"          # Real-time branch
        then:
          - tap: "Skip"
```

### Supported Actions

| Action | Description |
|--------|-------------|
| `tap` | Tap element by text or coordinates |
| `double_tap` | Double tap element |
| `type` | Type text (supports `submit: true` to press Enter) |
| `swipe` | Swipe gesture with direction/distance/duration |
| `long_press` | Long press element |
| `back` | Press back button |
| `hide_keyboard` | Dismiss keyboard |
| `wait` | Wait fixed duration |
| `wait_for` | Wait for element to appear |
| `scroll_to` | Scroll until element visible |
| `launch_app` | Launch configured app |
| `terminate_app` | Force stop app |
| `verify_screen` | AI verification (real-time, fails test if screen doesn't match) |
| `if_present` | Conditional on element presence |
| `if_absent` | Conditional on element absence |
| `if_screen` | Conditional on screen state (AI) |
| `repeat` | Execute nested steps multiple times |

## Configuration

**Priority order (highest to lowest):**
1. Environment variables (`MUT_DEVICE`, `MUT_VERBOSE`, `GOOGLE_API_KEY`)
2. Project config (`.mut.yaml` in current directory)
3. Global config (`~/.mut.yaml`)
4. Default values

**Verbose logging**: Set `MUT_VERBOSE=true` in `.env` to enable DEBUG-level file logging.

## Folder Structure

**Recording output:**
```
tests/my-test/
├── video.mp4              # Screen recording
├── video.timestamps.json  # Frame timing
├── touch_events.json      # Raw touch data
├── analysis.json          # AI step analysis
├── activity_states.json   # Activity state changes during recording
├── keyboard_states.json   # Keyboard visibility changes
├── window_states.json     # Window focus changes
├── screen_size.json       # Device screen dimensions
├── screenshots/           # Extracted frames for analysis
└── debug.log              # Verbose logs (if enabled)
```

**Test run output:**
```
tests/my-test/
├── test.yaml
└── reports/
    └── 2026-01-17_14-30-25/
        ├── debug.log           # Run-specific logs (if MUT_VERBOSE=true)
        ├── report.json         # Full test results with step data
        ├── report.html         # Interactive HTML report with gesture visualization
        ├── results.xml         # JUnit XML report (if --junit specified)
        ├── screenshots/        # Step screenshots (before, after, action)
        └── recording/          # Video recording (if --video specified)
            └── video.mp4
```

## Design Decisions

See `docs/DESIGN.md` for rationale on:
- Why Gemini 2.5 Flash over Claude/GPT (cost: $0.30/1M tokens)
- Why MYScrcpy over mobile-mcp (no MCP overhead, single connection)
- ADB vs scrcpy injection trade-offs (ADB is simpler, scrcpy offers tighter timing)
- AI-first element finding with semantic matching
- Hybrid verification strategy details
