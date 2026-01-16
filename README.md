# mut - Mobile UI Testing CLI

Run YAML-based mobile UI tests anywhere - CI/CD, local development, or scripts.

## Features

- **Run anywhere** - No Claude Code dependency, works in CI/CD
- **Fast screenshots** - ~50ms via scrcpy frame buffer
- **AI verification** - Gemini 2.5 Flash for visual assertions
- **Video recording** - Capture test execution for debugging
- **Record tests** - Capture user interactions to generate YAML

## Installation

```bash
pip install mut
```

### Requirements

- Python 3.11+
- Android device/emulator with USB debugging enabled
- `adb` in PATH
- `scrcpy` 3.x installed
- `GOOGLE_API_KEY` environment variable (for AI features)

## Quick Start

### Run a test

```bash
mut run tests/login.yaml
```

### Record a test

```bash
mut record login-flow
# Interact with your app...
mut stop
```

### List devices

```bash
mut devices
```

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
      - tap: "Email"
      - type: "user@test.com"
      - tap: "Password"
      - type: "secret123"
      - tap: "Sign In"
      - verify_screen: "Welcome screen with user greeting"
```

## Commands

### `mut run <test.yaml>`

Execute a YAML test file.

```bash
# Basic execution
mut run tests/login.yaml

# Skip AI verifications (faster, for CI)
mut run tests/login.yaml --no-ai

# Specify device
mut run tests/login.yaml --device emulator-5554

# Custom output
mut run tests/login.yaml --output reports/
```

### `mut record <name>`

Start recording user interactions.

```bash
mut record checkout-flow
```

### `mut stop`

Stop recording and generate YAML test.

```bash
mut stop
# Opens browser with approval UI
# Export YAML when done
```

### `mut devices`

List connected devices.

```bash
mut devices
```

## Configuration

### Global config (`~/.mut.yaml`)

```yaml
ai:
  model: gemini-2.5-flash

defaults:
  video: true
  verbose: false
```

### Project config (`.mut.yaml`)

```yaml
device: emulator-5554
test_dir: tests/
report_dir: reports/
```

## CI/CD Integration

### GitHub Actions

```yaml
name: Mobile UI Tests
on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install mut
        run: pip install mut

      - name: Run tests
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 34
          script: mut run tests/login.yaml --no-ai
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini API key for AI features |
| `MUT_DEVICE` | Default device ID |
| `MUT_VERBOSE` | Enable verbose logging |

## License

MIT
