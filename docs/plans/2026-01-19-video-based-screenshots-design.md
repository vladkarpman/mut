# Video-Based Screenshot Extraction for Reports

## Problem

Current implementation has two issues:

1. **Large HTML reports** — Screenshots are base64-encoded and embedded directly in HTML, making report files very large (several MB for tests with many steps).

2. **Confused responsibilities** — Runtime screenshots (captured for AI verification) are also used for reports, mixing two different concerns with different requirements.

## Solution

Separate runtime screenshots from report screenshots:

- **Runtime**: Screenshots captured in memory for AI features (verify_screen, element finding). Discarded after use.
- **Reports**: Frames extracted from video recording, saved as PNG files, referenced by HTML via relative paths.

**Constraint**: No video recording → no HTML report. JSON results still generated.

## Design

### Data Flow

```
Test Execution
│
├── Runtime path (unchanged):
│   Execute step → capture screenshot in memory → AI verification → discard
│
└── Report path (new):
    Execute step → store timestamp in StepResult
         ↓
    Test ends → extract frames from video at timestamps
         ↓
    Save PNGs to screenshots/ folder
         ↓
    Generate HTML referencing files
```

### Output Structure

```
tests/my-test/runs/2026-01-17_14-30-25/
├── results.json              # Always generated (no screenshots)
├── report.html               # Only if video was recorded
├── recording/
│   └── video.mp4
└── screenshots/
    ├── 001_tap_before.png
    ├── 001_tap_action.png
    ├── 001_tap_after.png
    ├── 002_type_before.png
    ├── 002_type_after.png
    ├── 003_swipe_before.png
    ├── 003_swipe_action.png
    ├── 003_swipe_action_end.png
    ├── 003_swipe_after.png
    └── ...
```

### File Naming Convention

Format: `{step_number:03d}_{action}_{frame_type}.png`

- `step_number`: Zero-padded 3-digit step number
- `action`: Action type (tap, swipe, type, verify_screen, etc.)
- `frame_type`: One of `before`, `after`, `action`, `action_end`

### Changes by Component

#### 1. StepResult (executor.py)

Replace screenshot bytes with file paths:

```python
@dataclass
class StepResult:
    # ... existing fields ...

    # Remove these (bytes):
    # screenshot_before: bytes | None = None
    # screenshot_after: bytes | None = None
    # screenshot_action: bytes | None = None
    # screenshot_action_end: bytes | None = None

    # Add these (paths, populated after video extraction):
    screenshot_before_path: Path | None = None
    screenshot_after_path: Path | None = None
    screenshot_action_path: Path | None = None
    screenshot_action_end_path: Path | None = None

    # Keep timestamps (already exist):
    _ts_before: float | None = None
    _ts_after: float | None = None
    _ts_action: float | None = None
    _ts_action_end: float | None = None
```

#### 2. TestExecutor (executor.py)

- `_capture_screenshot_or_timestamp()`: Only return timestamp when recording. Screenshot captured separately for AI if needed.
- `_extract_frames_from_video()`: Save frames as files instead of storing bytes. Populate `screenshot_*_path` fields.
- Remove screenshot bytes from StepResult population.

#### 3. ReportGenerator (report.py)

- Remove `_encode_screenshot()` method (no more base64).
- `generate_html()`: Only callable when video was recorded.
- `_generate_screenshots_html()`: Reference files via relative paths.
- `_result_to_dict()`: Include paths instead of base64 data URIs.

#### 4. CLI (cli.py)

- `run` command: Skip HTML report generation if `--video` not specified.
- Log message explaining why HTML report was skipped.

### HTML Template Changes

Replace base64 `src` attributes with file references:

```html
<!-- Before -->
<img src="data:image/png;base64,..." alt="Before">

<!-- After -->
<img src="screenshots/001_tap_before.png" alt="Before">
```

### JSON Report (results.json)

Continue generating without screenshots. Add paths if available:

```json
{
  "steps": [
    {
      "number": 1,
      "action": "tap",
      "status": "passed",
      "screenshots": {
        "before": "screenshots/001_tap_before.png",
        "action": "screenshots/001_tap_action.png",
        "after": "screenshots/001_tap_after.png"
      }
    }
  ]
}
```

## Migration

No migration needed — this changes output format only. Existing test YAML files are unaffected.

## Testing

1. Run test with `--video` flag → verify screenshots folder created with correct files
2. Run test without `--video` → verify no HTML report, JSON still generated
3. Open HTML report → verify images load correctly
4. Verify AI features still work (verify_screen, element finding)
