# mut CLI Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Design a standalone Mobile UI Testing CLI that's better than Maestro - AI-native, smarter recording, better reports.

**Architecture:** Python CLI using Typer, AI-first verification with Gemini, scrcpy for fast screenshots/video, test-centric file organization.

**Tech Stack:** Python 3.11+, Typer, Rich, scrcpy, adb, Gemini API

---

## 1. CLI Commands

Four commands, each with clear purpose:

### `mut run <test.yaml>`

Execute a YAML test file.

```bash
mut run tests/login/test.yaml                    # Basic run
mut run tests/login/test.yaml --device emu-5554  # Specific device
mut run tests/login/test.yaml --junit results.xml # Add JUnit output
```

**Output:** Creates `tests/{name}/reports/{timestamp}/` containing:
- `report.json` - Machine-readable results
- `report.html` - Interactive human report
- `recording.mp4` - Full video of test run
- `screenshots/` - Before/after frames per step

**Exit codes:**
- 0 = pass
- 1 = test failed
- 2 = error (no device, no API key, invalid YAML)

### `mut record <name>`

Start interactive recording session.

```bash
mut record checkout-flow
```

Flow:
1. Connects to device
2. Shows "Press Enter when done..."
3. User interacts with device
4. User presses Enter
5. AI analyzes actions (5 intelligence layers)
6. Opens approval UI in browser (mandatory)
7. User reviews, edits, exports YAML

### `mut devices`

List connected Android devices.

```bash
mut devices
```

### `mut report <dir>`

Regenerate HTML report from existing `report.json`.

```bash
mut report tests/login/reports/2024-01-16_14-30/
```

---

## 2. Configuration

### Priority Order

```
CLI flags > env vars > .mut.yaml (project) > ~/.mut.yaml (global) > defaults
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | **Yes** | Gemini API key for AI features |
| `MUT_DEVICE` | No | Default device ID |

**No API key = immediate failure** with clear error message.

### Project Config (`.mut.yaml`)

```yaml
app: com.example.myapp
test_dir: tests/
report_dir: reports/
device: emulator-5554

timeouts:
  tap: 5s
  wait_for: 15s
  verify_screen: 10s

retry:
  count: 2
  delay: 1s
```

### Global Config (`~/.mut.yaml`)

```yaml
defaults:
  verbose: true
  video: true
```

---

## 3. File Structure

Test-centric organization - everything for a test lives together.

```
project/
├── .mut.yaml                    # Project config (committed)
├── .mut/                        # Runtime state (gitignored)
│   └── recording-state.json
│
└── tests/
    └── login/
        ├── test.yaml            # Test definition (committed)
        ├── approval.html        # Approval UI snapshot (gitignored)
        ├── recording.mp4        # Original recording (gitignored)
        ├── touch_events.json    # Touch events (gitignored)
        ├── screenshots/         # Frames from recording (gitignored)
        │   ├── step_001.png
        │   └── ...
        └── reports/             # Test runs (gitignored)
            └── 2024-01-16_14-30/
                ├── report.json
                ├── report.html
                ├── recording.mp4
                └── screenshots/
```

**Committed:** `test.yaml` only
**Gitignored:** Everything else

---

## 4. YAML Test Format

Three levels of sophistication, coordinates in percentages.

### Level 1: Simple

```yaml
config:
  app: com.example.myapp

setup:
  - launch_app
  - wait: 2s

steps:
  - tap: "Sign In"
  - type: "user@test.com"
  - tap: "Password"
  - type: "secret123"
  - tap: "Submit"
  - verify_screen: "Welcome screen with user greeting"

teardown:
  - terminate_app
```

### Level 2: Rich with fallbacks

```yaml
steps:
  - tap:
      element: "Login"
      coordinates: [50%, 75%]    # Fallback: 50% from left, 75% from top
      timeout: 5s

  - type:
      text: "user@test.com"
      field: "Email input"

  - swipe:
      direction: up
      distance: 30%
      from: [50%, 80%]

  - verify_screen:
      description: "User logged in"
      timeout: 10s
```

### Level 3: Conditionals and flow

```yaml
steps:
  - tap: "Login"

  - if_present: "Cookie banner"
    then:
      - tap: "Accept"

  - if_screen: "Two-factor auth prompt"
    then:
      - type: "123456"
      - tap: "Verify"
    else:
      - verify_screen: "Dashboard"

  - repeat: 3
    steps:
      - swipe: down
      - wait: 1s
```

### Core Actions

| Action | Example | Description |
|--------|---------|-------------|
| `tap` | `tap: "Button"` | Tap element by text |
| `type` | `type: "hello"` | Type text into focused field |
| `swipe` | `swipe: up` | Swipe direction |
| `wait` | `wait: 2s` | Fixed wait |
| `wait_for` | `wait_for: "Element"` | Wait until element appears |
| `verify_screen` | `verify_screen: "Login form visible"` | AI verifies screen state |
| `launch_app` | `launch_app` | Start the app |
| `terminate_app` | `terminate_app` | Kill the app |
| `back` | `back` | Press back button |
| `scroll_to` | `scroll_to: "Element"` | Scroll until element visible |
| `long_press` | `long_press: "Item"` | Long press element |
| `double_tap` | `double_tap: "Item"` | Double tap element |
| `hide_keyboard` | `hide_keyboard` | Dismiss keyboard |

### Coordinates

```yaml
# Percentage (recommended, device-independent)
coordinates: [50%, 75%]

# Pixels (fallback)
coordinates: [540, 1200]
```

---

## 5. Smart Recording (5 AI Intelligence Layers)

### Recording Flow

```
$ mut record login-test

📱 Connected to: Pixel 7 (emulator-5554)
🎥 Recording started...

   Interact with your device now.
   Press Enter when done recording...

[User interacts]
[User presses Enter]

⏹️  Recording stopped (18 raw touch events)

🧠 AI analyzing...
   ✓ Mistake detected: tap at 0:03 corrected at 0:04 → skipped
   ✓ Wait inferred: 3s pause before "Dashboard" → wait_for added
   ✓ Conditional detected: cookie banner dismissed → if_present added
   ✓ Scroll context: scrolled before "Submit" → scroll_to added
   ✓ Flow recognized: login flow → smart verifications suggested

📊 Result: 18 raw events → 8 clean steps + 2 verifications

🌐 Opening approval UI...
```

### The 5 Intelligence Layers

| Layer | Raw Input | Smart Output |
|-------|-----------|--------------|
| **Mistake detection** | tap A, tap B, tap A again | Just `tap: A` (B was mistake) |
| **Wait inference** | 3s pause before action | `wait_for: "Element"` |
| **Conditional detection** | Dismissed popup | `if_present: "Popup"` then tap |
| **Scroll context** | Scrolled, then tapped | `scroll_to: "Element"` then tap |
| **Smart verification** | Login flow completed | `verify_screen: "User logged in"` |

### Before/After Example

**Raw recording (18 events):**
```
tap [50%, 30%] → tap [50%, 35%] → tap [50%, 30%] → type "user@..."
→ wait 2s → tap [50%, 50%] → scroll down → tap [50%, 80%] → wait 3s
→ dismiss popup → tap [50%, 90%]
```

**AI-generated YAML (8 steps):**
```yaml
steps:
  - tap: "Email"                    # Mistake at 0:02 skipped
  - type: "user@test.com"
  - tap: "Password"
  - type: "secret123"
  - scroll_to: "Submit"             # Scroll context added
  - tap: "Submit"
  - wait_for: "Dashboard"           # Wait inferred from 3s pause
  - if_present: "Cookie banner"     # Conditional detected
    then:
      - tap: "Accept"
  - verify_screen: "User logged in" # Smart verification
```

---

## 6. Report Format

### Report Structure

```
tests/login/reports/2024-01-16_14-30/
├── report.json          # Machine-readable (CI)
├── report.html          # Interactive human report
├── recording.mp4        # Full test video
└── screenshots/
    ├── step_001_before.png
    ├── step_001_after.png
    └── ...
```

### HTML Report Features

1. **Video playback with step markers** - Click marker to jump to step
2. **Step-by-step timeline** - Before/after screenshots
3. **AI failure analysis** - Why it failed + how to fix
4. **Single HTML file** - Embedded images, works offline, shareable

### JSON Report

```json
{
  "test": "login",
  "status": "failed",
  "duration": "12.3s",
  "steps": [
    {"name": "tap Email", "status": "passed", "duration": "0.8s"},
    {"name": "tap Submit", "status": "failed", "error": "element obscured"}
  ],
  "summary": {
    "total": 8,
    "passed": 6,
    "failed": 1,
    "skipped": 1
  }
}
```

---

## 7. Error Handling

### Error Categories

| Error | Exit Code | Example Message |
|-------|-----------|-----------------|
| No device | 2 | "No device found. Run `adb devices` to check." |
| No API key | 2 | "GOOGLE_API_KEY not set." |
| Invalid YAML | 2 | "line 12: unknown action 'taap'. Did you mean 'tap'?" |
| Element not found | 1 | "'Submit' not found. Available: ['Cancel', 'Back']" |
| Verification failed | 1 | "Expected 'Dashboard' but screen shows error" |
| Timeout | 1 | "wait_for 'Loading' timed out after 10s" |

### Smart Suggestions

```
❌ Step 5 failed: tap "Submti"

   Element "Submti" not found.

   Did you mean?
   → "Submit" (likely typo)

   Available elements:
   → "Submit"
   → "Cancel"
```

### AI Failure Analysis

```
❌ Step 8: verify_screen "User logged in"

   🧠 AI Analysis:
   Screen shows "Invalid password" error.
   User is NOT logged in.

   Possible causes:
   → Test credentials incorrect
   → Password field not filled
```

---

## 8. Timeouts and Retries

### Default Timeouts

| Action | Default |
|--------|---------|
| `tap` | 5s |
| `wait_for` | 10s |
| `verify_screen` | 10s |
| `type` | 3s |
| `swipe` | 3s |

### Configuring Timeouts

**Per-action:**
```yaml
steps:
  - wait_for:
      element: "Large image"
      timeout: 30s
```

**Global in config:**
```yaml
# .mut.yaml
timeouts:
  wait_for: 15s
```

### Retry Logic

**In config:**
```yaml
retry:
  count: 2
  delay: 1s
```

**Per-step:**
```yaml
steps:
  - tap:
      element: "Flaky button"
      retry: 3
```

### What Gets Retried

| Failure | Retry? |
|---------|--------|
| Element not found | Yes |
| Tap didn't register | Yes |
| Verification failed | No |
| Timeout | Yes (once) |
| Device error | No |

---

## 9. CI/CD Integration

### GitHub Actions Example

```yaml
name: Mobile UI Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install mut
        run: pip install mutcli

      - name: Start emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 34
          script: |
            mut run tests/login/test.yaml --junit results.xml
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: tests/login/reports/

      - name: Publish JUnit
        if: always()
        uses: mikepenz/action-junit-report@v4
        with:
          report_paths: results.xml
```

### Self-hosted Runner

```yaml
jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - run: pip install mutcli
      - run: mut run tests/login/test.yaml --junit results.xml
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
```

---

## Differentiators vs Maestro

| Feature | Maestro | mut |
|---------|---------|-----|
| Verification | Brittle selectors | AI-native natural language |
| Recording | Records coordinates | AI understands intent |
| Reports | Basic HTML | Video + AI analysis + interactive |
| Debugging | Screenshots | Full video + before/after + AI explains why |
| Cloud | Vendor lock-in | Works anywhere |
| Complexity | 30+ commands | Fewer commands, AI handles complexity |
