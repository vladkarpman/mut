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
mut stop                        # Stop recording, open approval UI

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
├── cli.py                     # Typer commands (run, record, stop, devices, report)
├── __init__.py                # Version
├── __main__.py                # Entry point
├── models/
│   └── test.py                # Test/Step data models
├── core/
│   ├── config.py              # ConfigLoader, setup_logging
│   ├── device_controller.py   # ADB wrapper: tap, swipe, type, elements
│   ├── scrcpy_service.py      # MYScrcpy: screenshots, video recording
│   ├── ai_analyzer.py         # Gemini 2.5 Flash: verify_screen, find_element
│   ├── executor.py            # TestExecutor: runs YAML tests
│   ├── parser.py              # YAML test file parser
│   ├── recorder.py            # Recording session manager
│   ├── touch_monitor.py       # ADB getevent touch capture
│   ├── frame_extractor.py     # Extract frames from video at timestamps
│   ├── step_analyzer.py       # AI analysis of recorded steps
│   ├── typing_detector.py     # Detect typing from touch patterns
│   ├── step_collapsing.py     # Collapse multiple taps into type actions
│   ├── verification_suggester.py  # Suggest verify_screen descriptions
│   ├── yaml_generator.py      # Generate YAML from analyzed steps
│   ├── preview_server.py      # HTTP server for approval UI
│   ├── analysis_io.py         # Save/load analysis JSON
│   └── report.py              # ReportGenerator: JSON + HTML reports
└── templates/
    └── approval.html          # Browser-based approval UI
```

### Key Patterns

**Dual interaction model**: `DeviceController` uses direct adb commands for device input (tap, swipe, type). `ScrcpyService` uses MYScrcpy for fast visual operations (screenshots ~50ms via frame buffer, video recording).

**Hybrid AI verification**:
- `verify_screen` - Deferred. Captures screenshot, continues test, batches AI calls at end. Fast execution, no state loss.
- `if_screen` - Real-time. Must call AI immediately for branching decisions.

**Frame buffer**: `ScrcpyService` maintains a 10-frame circular buffer. `screenshot()` returns the latest frame instantly without triggering capture.

**Recording pipeline**:
1. `Recorder` orchestrates recording session
2. `TouchMonitor` captures raw touch events via adb getevent
3. `ScrcpyService` records video with timestamps
4. `FrameExtractor` extracts before/after frames for each touch
5. `StepAnalyzer` uses AI to describe each step
6. `TypingDetector` + `StepCollapsing` convert tap sequences to type actions
7. `PreviewServer` serves approval UI for editing
8. `YamlGenerator` exports final test file

## External Dependencies

- `adb` in PATH (device communication)
- `scrcpy` 3.x (fast screenshots via MYScrcpy)
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
| `type` | Type text (supports `submit: true` to press Enter) |
| `swipe` | Swipe gesture with direction/distance |
| `long_press` | Long press element |
| `back` | Press back button |
| `hide_keyboard` | Dismiss keyboard |
| `wait` | Wait fixed duration |
| `wait_for` | Wait for element to appear |
| `scroll_to` | Scroll until element visible |
| `launch_app` | Launch configured app |
| `terminate_app` | Force stop app |
| `verify_screen` | AI verification (deferred) |
| `if_present` | Conditional on element presence |
| `if_absent` | Conditional on element absence |
| `if_screen` | Conditional on screen state (AI) |

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
└── debug.log              # Verbose logs (if enabled)
```

**Test run output:**
```
tests/my-test/
├── test.yaml
└── runs/
    └── 2026-01-17_14-30-25/
        └── debug.log      # Run-specific logs
```

## Design Decisions

See `docs/DESIGN.md` for rationale on:
- Why Gemini 2.5 Flash over Claude/GPT (cost: $0.30/1M tokens)
- Why MYScrcpy over mobile-mcp (no MCP overhead, single connection)
- Why direct adb over mobile-mcp (simpler, no dependency)
- AI-first element finding with semantic matching
- Hybrid verification strategy details
