# Report Action Screenshots Design

Add before/action/after 3-column layout to test runner HTML reports, matching the approval UI.

## Overview

Currently, test reports show 2-column before/after screenshots. This change adds a middle "action" column that captures the moment of interaction, matching the approval.html UI.

## Data Model Changes

**`StepResult` in `executor.py`:**

```python
@dataclass
class StepResult:
    # ... existing fields ...
    screenshot_before: bytes | None = None
    screenshot_after: bytes | None = None
    # NEW: Action screenshots (varies by gesture type)
    screenshot_action: bytes | None = None      # For tap/double_tap: touch moment
    screenshot_action_end: bytes | None = None  # For swipe: end position; for long_press: held state
```

## Screenshot Capture by Gesture Type

| Gesture | Frames | Capture Strategy |
|---------|--------|------------------|
| `tap` | before, action, after | Capture immediately after tap returns |
| `double_tap` | before, action, after | Capture after second tap |
| `swipe` | before, swipe_start, swipe_end, after | Non-blocking swipe, capture at start + 90% duration |
| `long_press` | before, press_start, press_held, after | Non-blocking press, capture at start + 70% duration |
| `type` | before, after | No action frame (keyboard taps not useful) |
| others | before, after | No action frame |

## Implementation Steps

### Step 1: DeviceController async methods

Add non-blocking versions of swipe and long_press in `device_controller.py`:

```python
def swipe_async(self, x1, y1, x2, y2, duration_ms=300) -> subprocess.Popen:
    """Start swipe gesture without blocking. Returns process to wait on."""
    cmd = ["adb", "-s", self._device_id, "shell", "input", "swipe",
           str(x1), str(y1), str(x2), str(y2), str(duration_ms)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def long_press_async(self, x, y, duration_ms=500) -> subprocess.Popen:
    """Start long press without blocking. Returns process to wait on."""
    cmd = ["adb", "-s", self._device_id, "shell", "input", "swipe",
           str(x), str(y), str(x), str(y), str(duration_ms)]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```

### Step 2: Executor action screenshot capture

Update `executor.py` to capture action screenshots:

1. Add instance variables to track action screenshots during step execution:
   ```python
   self._step_action_screenshot: bytes | None = None
   self._step_action_end_screenshot: bytes | None = None
   ```

2. Update `execute_step()` to clear and collect action screenshots:
   ```python
   # Clear at start
   self._step_action_screenshot = None
   self._step_action_end_screenshot = None

   # Include in StepResult
   return StepResult(
       # ... existing fields ...
       screenshot_action=self._step_action_screenshot,
       screenshot_action_end=self._step_action_end_screenshot,
   )
   ```

3. Update action handlers:

   **`_action_tap`:**
   ```python
   self._device.tap(x, y)
   self._step_action_screenshot = self._capture_screenshot()
   ```

   **`_action_swipe`:**
   ```python
   self._step_action_screenshot = self._capture_screenshot()  # swipe_start
   process = self._device.swipe_async(x1, y1, x2, y2, duration_ms)
   time.sleep(duration_ms * 0.9 / 1000)
   self._step_action_end_screenshot = self._capture_screenshot()  # swipe_end
   process.wait()
   ```

   **`_action_long_press`:**
   ```python
   self._step_action_screenshot = self._capture_screenshot()  # press_start
   process = self._device.long_press_async(x, y, duration_ms)
   time.sleep(duration_ms * 0.7 / 1000)
   self._step_action_end_screenshot = self._capture_screenshot()  # press_held
   process.wait()
   ```

### Step 3: Report data generation

Update `report.py` `_result_to_dict()`:

```python
"steps": [
    {
        # ... existing fields ...
        "screenshot_action": self._encode_screenshot(s.screenshot_action),
        "screenshot_action_end": self._encode_screenshot(s.screenshot_action_end),
    }
    for s in result.steps
]
```

### Step 4: Report HTML generation

Update `report.py` screenshot rendering:

1. Add `_get_action_frame_for_step()` helper to select primary action frame
2. Update `_generate_screenshots_html()` to produce 3-column layout when action frame exists
3. Update `_generate_frame_html()` to support "action" column styling
4. Move gesture indicator from "before" to "action" column

### Step 5: Report HTML template

Update `report.html` CSS to match approval.html:

1. Change `.step-frames` from 2-column grid to 3-column flex
2. Add `.frame-column.action` styling with highlight treatment
3. Update header colors to match approval.html (before=muted, action=primary, after=success)

## Visual Result

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   BEFORE    │  │   ACTION    │  │    AFTER    │
├─────────────┤  ├─────────────┤  ├─────────────┤
│             │  │      ◉      │  │             │
│  [screen    │  │  [screen +  │  │  [screen    │
│   before]   │  │   gesture]  │  │   after]    │
│             │  │             │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
     muted          highlighted        success
```

## Fallback Behavior

Steps without action screenshots (wait, verify_screen, type, launch_app, etc.) fall back to 2-column before/after layout.

## Files Changed

| File | Changes |
|------|---------|
| `mutcli/core/device_controller.py` | Add `swipe_async()`, `long_press_async()` |
| `mutcli/core/executor.py` | Add action screenshot fields and capture logic |
| `mutcli/core/report.py` | Update dict generation, add 3-column HTML |
| `mutcli/templates/report.html` | 3-column CSS matching approval.html |
