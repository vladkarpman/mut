# MUT CLI Design

**Date:** 2026-01-16
**Status:** Approved

## Summary

Build a standalone CLI tool (`mut`) for mobile UI testing that can run anywhere (CI/CD, local development) without requiring Claude Code. Uses MYScrcpy for fast screenshots and recording, Gemini 2.5 Flash for AI vision analysis, and direct adb commands for device interaction.

## Final Decisions

| Decision | Choice |
|----------|--------|
| Package name | `mut` |
| AI provider | Gemini 2.5 Flash only (for now) |
| Approval UI | Web-based (browser) |
| Repository | Separate git repo (`mut`) |
| Screenshots | MYScrcpy frame buffer |
| Video recording | MYScrcpy + PyAV |
| Device interaction | Direct adb |
| Verification strategy | Hybrid (deferred + real-time) |

## Problem Statement

Current mobile-ui-testing plugin:
- Requires Claude Code to run
- Cannot run in CI/CD pipelines
- Depends on screen-buffer-mcp (external MCP server)
- Depends on mobile-mcp for device interaction
- Uses Claude API (requires separate subscription from Claude Code)

## Solution

Standalone Python CLI that:
- Runs anywhere (CI/CD, scripts, terminals)
- Uses MYScrcpy directly (no MCP overhead)
- Uses Gemini 2.5 Flash for AI (cheap, good vision at $0.30/1M tokens)
- Uses adb directly for device interaction
- Lives in its own git repository

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    mut CLI                               │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │                  Commands                        │    │
│  │  run  │  record  │  stop  │  devices  │  report │    │
│  └───────────────────────┬─────────────────────────┘    │
│                          │                               │
│  ┌───────────────────────┴─────────────────────────┐    │
│  │                   Core Engine                    │    │
│  │                                                  │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │    │
│  │  │ Test     │  │ Scrcpy   │  │ AI       │      │    │
│  │  │ Executor │  │ Service  │  │ Analyzer │      │    │
│  │  └──────────┘  └──────────┘  └──────────┘      │    │
│  │                                                  │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │    │
│  │  │ Device   │  │ Report   │  │ YAML     │      │    │
│  │  │ Controller│ │ Generator│  │ Parser   │      │    │
│  │  └──────────┘  └──────────┘  └──────────┘      │    │
│  └──────────────────────────────────────────────────┘    │
│                          │                               │
│  ┌───────────────────────┴─────────────────────────┐    │
│  │                 External Services                │    │
│  │                                                  │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │    │
│  │  │ MYScrcpy │  │ Gemini   │  │ ADB      │      │    │
│  │  │ (scrcpy) │  │ API      │  │          │      │    │
│  │  └──────────┘  └──────────┘  └──────────┘      │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Repository Structure

**New repository:** `github.com/vladkarpman/mut`

```
mut/                        # Standalone CLI tool
├── pyproject.toml
├── README.md
├── LICENSE
├── mut/
│   ├── __init__.py
│   ├── cli.py
│   └── core/
├── tests/
└── docs/
```

**Existing repository:** `vladkarpman-plugins` (optional thin wrapper)

```
plugins/mobile-ui-testing/  # Claude Code plugin (optional)
├── commands/
│   └── run-test.md         # Delegates to: mut run {file}
└── .claude-plugin/
    └── plugin.json         # dependency: mut>=1.0.0
```

## Key Decisions Rationale

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Screenshots | MYScrcpy frame buffer | ~50ms latency, no MCP overhead |
| Video recording | MYScrcpy + PyAV | Single connection, reliable, no process management |
| AI vision | Gemini 2.5 Flash | Cheapest with good vision ($0.30/1M input tokens) |
| Device interaction | Direct adb | No mobile-mcp dependency, simpler |
| Verification | Hybrid (deferred + real-time) | Fast execution, no state loss |
| Approval UI | Web-based | Visual review of screenshots essential, already have HTML template |
| Element finding | AI-first with coordinate fallback | Multi-language support, semantic understanding |

## AI-First Element Finding Architecture

**Date Updated:** 2026-01-17

### Problem

Traditional mobile testing tools like Maestro use literal text matching or resource IDs:
- **Text matching** fails when app is in different language (e.g., "Sign In" vs "Войти")
- **Resource IDs** are not universal - many apps don't have them, or they change between builds
- **Coordinates** are brittle and screen-size dependent

### Solution: AI-First with Coordinate Fallback

mut uses AI vision to find elements semantically, with optional coordinates for validation:

```
┌─────────────────────────────────────────────────────────────┐
│                    Element Resolution                        │
│                                                              │
│  Input: step with target text and/or coordinates            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Case 1: Coordinates only (no text)                    │  │
│  │         → Use coordinates directly (no AI needed)     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Case 2: Text + Coordinates (at: field)                │  │
│  │         → Validate with AI, use coordinates           │  │
│  │         → If validation fails, return error           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Case 3: Text only                                     │  │
│  │         → Try device finder first (accessibility)     │  │
│  │         → Fall back to AI vision if not found         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### YAML Syntax

```yaml
# Text only - AI finds element in any language
- tap: "Sign In button"     # Works: "Sign In", "Войти", "登录"

# Coordinates only - no AI, just tap
- tap: [50%, 85%]           # Percentage coordinates
- tap: [540, 1200]          # Pixel coordinates

# Text + Coordinates - AI validates, then uses coordinates
- tap: "Sign In"
  at: [50%, 85%]            # Validates button is at these coords
```

### How It Enables Multi-Language Support

Tests are written in English (intent-based), but AI understands semantics:

```yaml
# This test works on Russian device:
- tap: "Login button"       # AI finds "Войти" button
- type: "user@test.com"
- tap: "Submit"             # AI finds "Отправить"
- verify_screen: "Welcome screen"  # AI checks for welcome message
```

The AI understands that "Login button" semantically matches a button that performs login, regardless of the displayed text language.

### Comparison with Alternatives

| Approach | Multi-language | Maintenance | Speed |
|----------|---------------|-------------|-------|
| **mut (AI-first)** | ✅ Yes | Low (semantic) | ~200ms |
| Maestro (text/ID) | ❌ No | High (per-language) | Fast |
| mobile-mcp (coords) | ❌ Manual | Very High | Fast |
| Appium (XPath) | ⚠️ Partial | High (brittle) | Slow |

### Implementation Details

**AIAnalyzer Methods:**

```python
def find_element(screenshot: bytes, description: str, width: int, height: int) -> tuple[int, int] | None:
    """Find element on screen by semantic description.

    Returns center coordinates of matching element, or None if not found.
    """

def validate_element_at(screenshot: bytes, description: str, x_pct: float, y_pct: float) -> dict:
    """Validate that element at coordinates matches description.

    Returns {"valid": bool, "reason": str}.
    Used when 'at:' coordinates are provided with text.
    """
```

**Executor Resolution Logic:**

```python
def _resolve_coordinates_ai(step: Step) -> tuple[tuple[int, int] | None, str | None]:
    """Resolve coordinates using AI-first approach.

    Strategy:
    1. coordinates only (no text) → use coordinates directly
    2. text + coordinates → validate with AI, use coordinates
    3. text only → device finder first, AI vision fallback
    """
```

### When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| `tap: "Button"` | Most cases - let AI find element |
| `tap: [50%, 85%]` | Fixed UI position, no text needed |
| `tap: "Button" at: [50%, 85%]` | Known position but want validation |

### Performance Considerations

- Device accessibility tree lookup: ~100ms
- AI element finding: ~200-500ms
- AI validation: ~200-500ms

For performance-critical tests, use coordinates. For maintainability, use text descriptions.

## CLI Commands

### `mut run <test.yaml>`

Execute a YAML test file and generate report.

```bash
# Basic execution
$ mut run tests/login.yaml

# Skip AI verifications (CI mode, faster)
$ mut run tests/login.yaml --no-ai

# Specify device
$ mut run tests/login.yaml --device emulator-5554

# Custom output directory
$ mut run tests/login.yaml --output reports/
```

**Flags:**
- `--no-ai` - Skip verify_screen/if_screen (just execute actions)
- `--device <id>` - Target specific device
- `--output <dir>` - Report output directory
- `--no-video` - Skip video recording
- `--verbose` - Detailed logging

### `mut record <name>`

Start recording user interactions.

```bash
$ mut record login-flow
Recording started: login-flow
Device: Pixel 7 (emulator-5554)
Saving to: tests/login-flow/

Touch the screen to record actions...
Press Ctrl+C or run 'mut stop' to finish.
```

### `mut stop`

Stop recording and generate YAML test.

```bash
$ mut stop
Recording stopped.
Analyzing 12 steps...
Generated: tests/login-flow/test.yaml
```

### `mut devices`

List connected devices.

```bash
$ mut devices
ID              NAME                STATUS
emulator-5554   Pixel 7 (API 34)    connected
ABC123XYZ       Galaxy S24          connected
```

### `mut report <dir>`

Generate HTML report from JSON results.

```bash
$ mut report tests/reports/2026-01-16_login/
Generated: tests/reports/2026-01-16_login/report.html
```

## Component Design

### 1. Scrcpy Service

Single MYScrcpy connection handling both screenshots and recording.

```python
class ScrcpyService:
    """Unified scrcpy service for screenshots and recording."""

    def __init__(self, device_id: str):
        self._session: Session = None
        self._frame_buffer: deque = deque(maxlen=10)
        self._recording = False
        self._video_writer: av.OutputContainer = None
        self._lock = threading.Lock()

    async def connect(self) -> bool:
        """Connect to device via MYScrcpy."""
        pass

    def screenshot(self) -> bytes:
        """Get latest frame as PNG from buffer (~50ms)."""
        pass

    def start_recording(self, output_path: str) -> dict:
        """Start writing frames to video file."""
        pass

    def stop_recording(self) -> dict:
        """Stop recording and finalize video."""
        pass

    def _frame_loop(self):
        """Continuous frame capture and optional recording."""
        while self._running:
            frame = self._session.va.get_frame()
            if frame:
                with self._lock:
                    self._frame_buffer.append(frame)
                if self._recording:
                    self._write_frame(frame)
```

### 2. Device Controller

Direct adb commands for device interaction.

```python
class DeviceController:
    """Device interaction via adb."""

    def __init__(self, device_id: str):
        self._device_id = device_id

    def tap(self, x: int, y: int) -> None:
        """Tap at coordinates."""
        self._adb(f"shell input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe gesture."""
        self._adb(f"shell input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def type_text(self, text: str) -> None:
        """Type text."""
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        self._adb(f"shell input text '{escaped}'")

    def press_key(self, keycode: str) -> None:
        """Press key (BACK, HOME, ENTER, etc.)."""
        keycodes = {"BACK": 4, "HOME": 3, "ENTER": 66}
        self._adb(f"shell input keyevent {keycodes[keycode]}")

    def list_elements(self) -> list[dict]:
        """Get UI elements via uiautomator."""
        self._adb("shell uiautomator dump /sdcard/ui.xml")
        self._adb(f"pull /sdcard/ui.xml /tmp/ui_{self._device_id}.xml")
        return self._parse_ui_xml(f"/tmp/ui_{self._device_id}.xml")

    def find_element(self, text: str) -> tuple[int, int] | None:
        """Find element by text, return center coordinates."""
        elements = self.list_elements()
        for el in elements:
            if el.get("text") == text or el.get("content-desc") == text:
                bounds = el["bounds"]
                return ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
        return None

    def _adb(self, cmd: str) -> str:
        """Execute adb command."""
        result = subprocess.run(
            ["adb", "-s", self._device_id] + cmd.split(),
            capture_output=True, text=True
        )
        return result.stdout
```

### 3. AI Analyzer

Gemini 2.5 Flash for vision analysis.

```python
class AIAnalyzer:
    """AI vision analysis using Gemini 2.5 Flash."""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=self._api_key)
        self._model = "gemini-2.5-flash"

    def verify_screen(self, screenshot: bytes, description: str) -> dict:
        """Verify screen matches description. Returns {pass: bool, reason: str}."""
        prompt = f"""Analyze this mobile app screenshot.

Question: Does the screen show "{description}"?

Respond with JSON only:
{{"pass": true/false, "reason": "brief explanation"}}
"""
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                {"mime_type": "image/png", "data": base64.b64encode(screenshot).decode()},
                prompt
            ]
        )
        return json.loads(response.text)

    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition. Returns boolean."""
        result = self.verify_screen(screenshot, condition)
        return result["pass"]

    def analyze_step(self, before: bytes, after: bytes) -> dict:
        """Analyze before/after frames for step description."""
        prompt = """Compare these two mobile app screenshots (before and after an action).

Describe:
1. What was the UI state before?
2. What action was likely performed?
3. What changed after?

Respond with JSON:
{"before": "...", "action": "...", "after": "...", "suggested_verification": "..."}
"""
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                {"mime_type": "image/png", "data": base64.b64encode(before).decode()},
                {"mime_type": "image/png", "data": base64.b64encode(after).decode()},
                prompt
            ]
        )
        return json.loads(response.text)
```

### 4. Test Executor

Runs YAML tests with hybrid verification.

```python
class TestExecutor:
    """Execute YAML tests with hybrid verification strategy."""

    def __init__(self, device: DeviceController, scrcpy: ScrcpyService, ai: AIAnalyzer):
        self._device = device
        self._scrcpy = scrcpy
        self._ai = ai
        self._deferred_verifications: list[dict] = []

    async def run(self, test_path: str, options: dict) -> dict:
        """Run test and return results."""
        test = self._load_yaml(test_path)
        results = {"steps": [], "passed": True}

        # Start recording
        if not options.get("no_video"):
            self._scrcpy.start_recording(self._get_recording_path(test_path))

        # Execute steps
        for i, step in enumerate(test["steps"]):
            step_result = await self._execute_step(step, options)
            results["steps"].append(step_result)
            if not step_result["success"]:
                results["passed"] = False
                if not options.get("continue_on_failure"):
                    break

        # Stop recording
        if not options.get("no_video"):
            self._scrcpy.stop_recording()

        # Run deferred verifications
        if not options.get("no_ai"):
            await self._run_deferred_verifications(results)

        return results

    async def _execute_step(self, step: dict, options: dict) -> dict:
        """Execute single step."""
        if "tap" in step:
            return await self._execute_tap(step["tap"])
        elif "type" in step:
            return await self._execute_type(step["type"])
        elif "verify_screen" in step:
            return await self._execute_verify_screen(step["verify_screen"], options)
        elif "if_screen" in step:
            return await self._execute_if_screen(step, options)
        # ... other actions

    async def _execute_verify_screen(self, description: str, options: dict) -> dict:
        """Capture screenshot and defer verification."""
        screenshot = self._scrcpy.screenshot()

        # Save for deferred analysis
        self._deferred_verifications.append({
            "description": description,
            "screenshot": screenshot,
            "timestamp": time.time()
        })

        # Continue immediately (no AI call)
        return {"success": True, "action": "verify_screen", "deferred": True}

    async def _execute_if_screen(self, step: dict, options: dict) -> dict:
        """Real-time AI analysis for branching."""
        screenshot = self._scrcpy.screenshot()
        condition = step["if_screen"]

        # Must be real-time for branching decision
        result = self._ai.if_screen(screenshot, condition)

        if result:
            # Execute 'then' branch
            for sub_step in step.get("then", []):
                await self._execute_step(sub_step, options)
        else:
            # Execute 'else' branch
            for sub_step in step.get("else", []):
                await self._execute_step(sub_step, options)

        return {"success": True, "action": "if_screen", "condition_met": result}

    async def _run_deferred_verifications(self, results: dict) -> None:
        """Run all deferred verify_screen checks."""
        for verification in self._deferred_verifications:
            result = self._ai.verify_screen(
                verification["screenshot"],
                verification["description"]
            )
            if not result["pass"]:
                results["passed"] = False
            # Update step result
            # ...
```

## File Structure

```
mut/
├── pyproject.toml          # Package config
├── mut/
│   ├── __init__.py
│   ├── __main__.py         # CLI entry point
│   ├── cli.py              # Click/Typer commands
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scrcpy_service.py
│   │   ├── device_controller.py
│   │   ├── ai_analyzer.py
│   │   ├── test_executor.py
│   │   └── report_generator.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── test.py         # Test YAML model
│   │   └── result.py       # Result model
│   └── utils/
│       ├── __init__.py
│       └── adb.py
└── tests/
    └── ...
```

## Configuration

### Global config (`~/.mut.yaml`)

```yaml
ai:
  provider: google
  model: gemini-2.5-flash
  # API key from GOOGLE_API_KEY env var

defaults:
  video: true
  verbose: false
```

### Project config (`.mut.yaml`)

```yaml
# Override global settings
ai:
  model: gemini-2.5-flash

# Default device
device: emulator-5554

# Test directory
test_dir: tests/
report_dir: reports/
```

## Dependencies

```toml
[project]
dependencies = [
    "mysc>=0.5.0",           # MYScrcpy - scrcpy 3.x client
    "adbutils>=2.0.0",       # Device management
    "pillow>=10.0.0",        # Image processing
    "numpy>=1.24.0",         # Frame handling
    "av>=12.0.0",            # PyAV - video encoding
    "google-genai>=1.0.0",   # Gemini API client
    "pyyaml>=6.0",           # YAML parsing
    "typer>=0.12.0",         # CLI framework
    "rich>=13.0.0",          # Terminal output
]
```

## Flows

### `/run-test` Flow

```
mut run tests/login.yaml
│
├── Load test YAML
├── Connect to device (adb)
├── Start scrcpy service
├── Start video recording
│
├── For each step:
│   ├── tap: "Button"
│   │   └── list_elements → find coords → adb tap
│   ├── tap: [x, y]
│   │   └── adb tap directly
│   ├── type: "text"
│   │   └── adb input text
│   ├── verify_screen: "description"
│   │   └── screenshot → save to deferred list → continue
│   ├── if_screen: "condition"
│   │   └── screenshot → Gemini API → branch decision
│   └── wait_for: "element"
│       └── poll list_elements until found
│
├── Stop video recording
├── Extract frames from video (ffmpeg)
├── Run deferred verifications (Gemini API)
├── Generate report (JSON + HTML)
│
└── Exit with pass/fail code
```

### `/record-test` Flow

```
mut record mytest
│
├── Detect device
├── Start scrcpy service
├── Start video recording
├── Start touch monitor (adb getevent)
│
├── User interacts with app
│   └── Touch events saved with timestamps
│
└── (Ctrl+C or mut stop)

mut stop
│
├── Stop touch monitor
├── Stop video recording
├── Extract frames at touch timestamps
├── Analyze steps with AI (Gemini)
│   └── before/after frames → description
├── Open approval UI (browser)
│   ├── Review steps
│   ├── Edit verifications
│   └── Export YAML
│
└── Generate tests/mytest/test.yaml
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Mobile UI Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install mut
        run: pip install mut-cli

      - name: Start emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 34
          script: |
            mut run tests/login.yaml --output reports/
            mut run tests/checkout.yaml --output reports/

      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: test-reports
          path: reports/
```

## Implementation Tasks

### Phase 1: Core Infrastructure
- [ ] Project setup (pyproject.toml, structure)
- [ ] ScrcpyService (connect, screenshot, frame buffer)
- [ ] DeviceController (tap, swipe, type, elements)
- [ ] Basic CLI (mut devices)

### Phase 2: Test Execution
- [ ] YAML parser (test model)
- [ ] TestExecutor (basic actions)
- [ ] Video recording (PyAV encoding)
- [ ] Frame extraction

### Phase 3: AI Integration
- [ ] AIAnalyzer (Gemini client)
- [ ] verify_screen (deferred)
- [ ] if_screen (real-time)
- [ ] Step analysis

### Phase 4: Recording
- [ ] Touch monitor (adb getevent)
- [ ] mut record / mut stop
- [ ] Approval UI
- [ ] YAML generation

### Phase 5: Reports & Polish
- [ ] Report generator (JSON + HTML)
- [ ] CI/CD examples
- [ ] Documentation
- [ ] PyPI publish

## Success Criteria

- [ ] `mut run` executes tests without Claude Code
- [ ] `mut run --no-ai` works in CI without API key
- [ ] Screenshots < 100ms (scrcpy frame buffer)
- [ ] Video recording works for 30+ minutes
- [ ] Deferred verify_screen doesn't block test execution
- [ ] Real-time if_screen makes correct branching decisions
- [ ] Reports include video, screenshots, pass/fail status

## Migration Path

Existing mobile-ui-testing plugin users:
1. Install `mut` CLI: `pip install mut-cli`
2. Existing YAML tests work unchanged
3. Run with `mut run` instead of `/run-test`
4. Plugin becomes thin wrapper calling `mut` CLI

## Future Considerations

These are explicitly deferred for later:
- Multiple AI providers (Claude, OpenAI) — can add if Gemini proves insufficient
- Terminal-based approval UI — can add for SSH/headless scenarios
- iOS support — focus on Android first
