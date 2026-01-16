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
mut run tests/login.yaml --no-ai  # Skip AI (faster, no API key needed)

# Tests
pytest                          # Run all tests
pytest tests/test_device.py     # Single file
pytest -k "test_tap"            # By pattern

# Code quality
ruff check .                    # Lint
ruff check . --fix              # Auto-fix
mypy mut/                       # Type check

# Build
python -m build
```

## Architecture

```
mut/
├── cli.py                     # Typer commands (run, record, stop, devices)
└── core/
    ├── device_controller.py   # ADB wrapper: tap, swipe, type, elements
    ├── scrcpy_service.py      # MYScrcpy: screenshots, video recording
    └── ai_analyzer.py         # Gemini 2.5 Flash: verify_screen, if_screen
```

### Key Patterns

**Dual interaction model**: `DeviceController` uses direct adb commands for device input (tap, swipe, type). `ScrcpyService` uses MYScrcpy for fast visual operations (screenshots ~50ms via frame buffer, video recording).

**Hybrid AI verification**:
- `verify_screen` - Deferred. Captures screenshot, continues test, batches AI calls at end. Fast execution, no state loss.
- `if_screen` - Real-time. Must call AI immediately for branching decisions.

**Frame buffer**: `ScrcpyService` maintains a 10-frame circular buffer. `screenshot()` returns the latest frame instantly without triggering capture.

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

## Design Decisions

See `docs/DESIGN.md` for rationale on:
- Why Gemini 2.5 Flash over Claude/GPT (cost: $0.30/1M tokens)
- Why MYScrcpy over mobile-mcp (no MCP overhead, single connection)
- Why direct adb over mobile-mcp (simpler, no dependency)
- Hybrid verification strategy details
