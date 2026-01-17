# mut - Mobile UI Testing CLI

Run YAML-based mobile UI tests anywhere - CI/CD, local development, or scripts.

## Features

- **Run anywhere** - No Claude Code dependency, works in CI/CD
- **Fast screenshots** - ~50ms via scrcpy frame buffer
- **AI verification** - Gemini 2.5 Flash for visual assertions
- **Video recording** - Capture test execution for debugging
- **Record tests** - Capture user interactions with approval UI
- **Conditional actions** - Branch based on screen state
- **Verbose logging** - Debug-level file logging for troubleshooting

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
mut record login-flow --app com.example.app
# Interact with your app...
mut stop
# Opens approval UI in browser
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

## Actions Reference

### Basic Actions

| Action | Description | Example |
|--------|-------------|---------|
| `tap` | Tap element by text or coordinates | `tap: "Submit"` or `tap: [540, 1200]` |
| `type` | Type text into focused field | `type: "hello@example.com"` |
| `swipe` | Swipe gesture | `swipe: {direction: up, distance: 300}` |
| `long_press` | Long press element | `long_press: "Item"` |
| `back` | Press back button | `back` |
| `hide_keyboard` | Dismiss keyboard | `hide_keyboard` |

### Wait Actions

| Action | Description | Example |
|--------|-------------|---------|
| `wait` | Wait fixed duration | `wait: 2s` |
| `wait_for` | Wait for element to appear | `wait_for: "Loading complete"` |
| `scroll_to` | Scroll until element visible | `scroll_to: "Terms of Service"` |

### App Lifecycle

| Action | Description | Example |
|--------|-------------|---------|
| `launch_app` | Launch configured app | `launch_app` |
| `terminate_app` | Force stop app | `terminate_app` |

### AI Verification

| Action | Description | Example |
|--------|-------------|---------|
| `verify_screen` | Assert screen matches description (deferred) | `verify_screen: "Login form visible"` |

### Conditional Actions

```yaml
# Execute steps if element is present
- if_present: "Skip Tutorial"
  then:
    - tap: "Skip Tutorial"

# Execute steps if element is absent
- if_absent: "Login Button"
  then:
    - tap: "Sign Up"

# Branch based on screen state (AI-powered)
- if_screen: "2FA prompt shown"
  then:
    - tap: "Skip for now"
  else:
    - tap: "Continue"
```

## Commands

### `mut run <test.yaml>`

Execute a YAML test file.

```bash
# Basic execution
mut run tests/login.yaml

# Specify device
mut run tests/login.yaml --device emulator-5554

# Custom output directory
mut run tests/login.yaml --output reports/

# Generate JUnit XML report
mut run tests/login.yaml --junit results.xml
```

### `mut record <name>`

Start recording user interactions.

```bash
mut record checkout-flow --app com.example.shop
```

### `mut stop`

Stop recording and generate YAML test.

```bash
mut stop
# Opens browser with approval UI
# Review and edit steps
# Export YAML when done
```

### `mut devices`

List connected devices.

```bash
mut devices
```

### `mut report <dir>`

Generate HTML report from JSON results.

```bash
mut report tests/reports/2026-01-16_login/
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Gemini API key for AI features |
| `MUT_DEVICE` | Default device ID |
| `MUT_VERBOSE` | Enable verbose file logging (`true`/`false`) |

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
verbose: true
```

### Verbose Logging

Enable debug-level file logging for troubleshooting:

```bash
# Via .env file (recommended)
echo "MUT_VERBOSE=true" >> .env

# Via environment variable
MUT_VERBOSE=true mut run tests/login.yaml
```

**Log file locations:**

- Recording: `tests/<name>/debug.log`
- Test run: `tests/<name>/runs/<timestamp>/debug.log`

Logs include: step execution, element search, AI calls, timing, retries.

## Recording Workflow

1. **Start recording**: `mut record my-test --app com.example.app`
2. **Interact with app**: Touch, type, swipe - all captured with video
3. **Stop recording**: `mut stop`
4. **Review in browser**: Approval UI opens automatically
5. **Edit steps**: Adjust descriptions, add verifications
6. **Export YAML**: Download the generated test file

**Recording folder structure:**

```
tests/my-test/
├── video.mp4              # Screen recording
├── video.timestamps.json  # Frame timing data
├── touch_events.json      # Raw touch data
├── analysis.json          # AI step analysis
└── debug.log              # Verbose logs (if enabled)
```

## Test Run Structure

Each test run creates a timestamped folder:

```
tests/my-test/
├── test.yaml              # Test definition
└── runs/
    └── 2026-01-17_14-30-25/
        └── debug.log      # Run-specific logs
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
          script: mut run tests/login.yaml --junit results.xml
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}

      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results
          path: results.xml
```

## License

MIT
