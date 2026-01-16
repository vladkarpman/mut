# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**mut** - Mobile UI Testing CLI

A standalone Python CLI tool for running YAML-based mobile UI tests. Works anywhere: CI/CD pipelines, local development, or scripts. No Claude Code dependency required.

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# List devices
mut devices

# Run a test
mut run tests/login.yaml

# Record a test
mut record mytest
mut stop
```

## Architecture

```
mut/
├── cli.py              # Typer CLI commands
└── core/
    ├── device_controller.py  # ADB device interaction
    ├── scrcpy_service.py     # Screenshots + video recording
    └── ai_analyzer.py        # Gemini 2.5 Flash vision
```

## Key Technologies

| Component | Technology |
|-----------|------------|
| CLI framework | Typer + Rich |
| Screenshots | MYScrcpy (scrcpy 3.x) |
| Video recording | MYScrcpy + PyAV |
| AI vision | Gemini 2.5 Flash |
| Device control | Direct adb commands |

## Commands

```bash
mut run <test.yaml>     # Execute test
mut record <name>       # Start recording
mut stop                # Stop and generate YAML
mut devices             # List devices
mut report <dir>        # Generate HTML report
```

## Development

### Running tests

```bash
pytest
```

### Code quality

```bash
ruff check .
mypy mut/
```

### Building

```bash
pip install build
python -m build
```

## Design Document

See `docs/DESIGN.md` for the full architecture and design decisions.

## Dependencies

- Python 3.11+
- scrcpy 3.x
- adb
- GOOGLE_API_KEY for AI features

## Implementation Status

### Phase 1: Core Infrastructure
- [x] Project setup
- [x] DeviceController (list, tap, swipe, type, elements)
- [ ] ScrcpyService (connect, screenshot, recording)
- [x] Basic CLI (devices command)

### Phase 2: Test Execution
- [ ] YAML parser
- [ ] TestExecutor
- [ ] Video recording
- [ ] Frame extraction

### Phase 3: AI Integration
- [ ] AIAnalyzer (Gemini client)
- [ ] verify_screen (deferred)
- [ ] if_screen (real-time)

### Phase 4: Recording
- [ ] Touch monitor
- [ ] mut record / stop
- [ ] Approval UI
- [ ] YAML generation

### Phase 5: Polish
- [ ] Report generator
- [ ] Documentation
- [ ] PyPI publish
