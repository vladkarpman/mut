# Report Gesture Visualization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add approval.html-quality animated gesture indicators to report.html with trajectory visualization for swipes.

**Architecture:** Synthesize swipe trajectories in executor from known start/end coordinates, pass through report.py to report.html, render with CSS animations copied from approval.html.

**Tech Stack:** Python (executor, report generator), HTML/CSS/JS (report template)

---

## Task 1: Add Trajectory Synthesis to Executor

**Files:**
- Modify: `mutcli/core/executor.py:568-618` (swipe action area)
- Test: `tests/test_executor.py` (add trajectory test)

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
def test_swipe_generates_trajectory():
    """Test that swipe action generates trajectory points in details."""
    from mutcli.core.executor import TestExecutor
    from mutcli.models.test import Step
    from unittest.mock import MagicMock, patch

    # Mock device controller
    mock_device = MagicMock()
    mock_device.get_screen_size.return_value = (1080, 2400)
    mock_device.swipe_async.return_value = MagicMock()  # Mock process

    with patch.object(TestExecutor, '_capture_screenshot', return_value=None):
        executor = TestExecutor.__new__(TestExecutor)
        executor._device = mock_device
        executor._config = MagicMock()
        executor._ai = MagicMock()
        executor._scrcpy = None
        executor._screen_size = (1080, 2400)
        executor._step_number = 0
        executor._test_start = 0.0
        executor._step_coords = None
        executor._step_end_coords = None
        executor._step_direction = None
        executor._step_action_screenshot = None
        executor._step_action_end_screenshot = None

        step = Step(action="swipe", direction="up", distance=30)
        result = executor.execute_step(step)

        # Verify trajectory exists in details
        assert "trajectory" in result.details
        trajectory = result.details["trajectory"]
        assert len(trajectory) >= 10  # At least 10 points
        assert all("x" in p and "y" in p and "t" in p for p in trajectory)

        # Verify first point is start, last is end
        assert trajectory[0]["t"] == 0
        assert trajectory[-1]["t"] > 0

        # Verify duration_ms is set
        assert "duration_ms" in result.details
        assert result.details["duration_ms"] == 300  # Default swipe duration
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py::test_swipe_generates_trajectory -v`
Expected: FAIL with KeyError or assertion error (trajectory not in details)

**Step 3: Add trajectory synthesis method to executor**

Add after line ~425 in `mutcli/core/executor.py` (after `_coordinates_to_pixels`):

```python
def _synthesize_trajectory(
    self,
    start: tuple[int, int],
    end: tuple[int, int],
    duration_ms: int,
    num_points: int = 15,
) -> list[dict[str, float]]:
    """Generate trajectory points for swipe visualization.

    Uses ease-out-quad easing for natural finger motion.

    Args:
        start: Start coordinates (x, y) in pixels
        end: End coordinates (x, y) in pixels
        duration_ms: Swipe duration in milliseconds
        num_points: Number of trajectory points to generate

    Returns:
        List of trajectory points with x, y (percentages) and t (ms)
    """
    def ease_out_quad(t: float) -> float:
        return t * (2 - t)

    width, height = self._get_screen_size()
    points = []

    for i in range(num_points):
        t = i / (num_points - 1) if num_points > 1 else 0
        t_eased = ease_out_quad(t)

        x = start[0] + (end[0] - start[0]) * t_eased
        y = start[1] + (end[1] - start[1]) * t_eased

        points.append({
            "x": x / width * 100,
            "y": y / height * 100,
            "t": int(t * duration_ms),
        })

    return points
```

**Step 4: Add instance variable for trajectory**

In `__init__` around line 92, add:

```python
self._step_trajectory: list[dict[str, float]] | None = None  # Trajectory for swipes
```

**Step 5: Clear trajectory in execute_step**

In `execute_step` around line 218, add to the clear section:

```python
self._step_trajectory = None
```

**Step 6: Update _action_swipe to generate trajectory**

In `_action_swipe` (around line 602), after setting `self._step_end_coords`, add:

```python
# Generate trajectory for visualization
self._step_trajectory = self._synthesize_trajectory(
    (cx, cy), (end_x, end_y), duration_ms
)
```

**Step 7: Include trajectory in step details**

In `execute_step` around line 291, after the direction check, add:

```python
if self._step_trajectory:
    details["trajectory"] = self._step_trajectory
    details["duration_ms"] = 300  # Default swipe duration
```

**Step 8: Run test to verify it passes**

Run: `pytest tests/test_executor.py::test_swipe_generates_trajectory -v`
Expected: PASS

**Step 9: Commit**

```bash
git add mutcli/core/executor.py tests/test_executor.py
git commit -m "feat(executor): add trajectory synthesis for swipe visualization"
```

---

## Task 2: Update Report Data Model

**Files:**
- Modify: `mutcli/core/report.py:174-194` (step dict in _result_to_dict)

**Step 1: Add trajectory fields to step dict**

In `_result_to_dict`, update the step dict comprehension (around line 174-194) to include:

```python
# After "direction": s.details.get("direction"),
# Add:
"trajectory": s.details.get("trajectory"),
"duration_ms": s.details.get("duration_ms"),
```

**Step 2: Run existing tests to verify no regression**

Run: `pytest tests/test_report.py -v`
Expected: All existing tests PASS

**Step 3: Commit**

```bash
git add mutcli/core/report.py
git commit -m "feat(report): include trajectory data in report JSON"
```

---

## Task 3: Update Gesture Indicator HTML Generation

**Files:**
- Modify: `mutcli/core/report.py:337-376` (_generate_gesture_indicator_html)

**Step 1: Update swipe indicator HTML generation**

Replace the swipe section in `_generate_gesture_indicator_html` (lines ~352-374) with:

```python
if action == "swipe":
    end_coords = step.get("end_coords", {})
    end_x = end_coords.get("x", x)
    end_y = end_coords.get("y", y)
    trajectory = step.get("trajectory", [])
    direction = step.get("direction", "up")

    # Encode trajectory as JSON for JavaScript
    import json
    traj_json = html.escape(json.dumps(trajectory)) if trajectory else "[]"

    return f"""<div class="gesture-indicator-container">
<div class="swipe-indicator"
    data-x="{x:.1f}" data-y="{y:.1f}"
    data-end-x="{end_x:.1f}" data-end-y="{end_y:.1f}"
    data-trajectory="{traj_json}"
    data-direction="{direction}">
    <div class="swipe-trajectory-line"></div>
    <div class="swipe-dot"></div>
</div>
</div>"""
```

**Step 2: Add json import at top of file**

Verify `import json` is present at top of `report.py` (it already is on line 5).

**Step 3: Run tests**

Run: `pytest tests/test_report.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add mutcli/core/report.py
git commit -m "feat(report): generate swipe indicator HTML with trajectory data"
```

---

## Task 4: Copy Gesture CSS from approval.html to report.html

**Files:**
- Modify: `mutcli/templates/report.html` (CSS section)
- Reference: `mutcli/templates/approval.html:3775-4050` (gesture CSS)

**Step 1: Read the gesture CSS from approval.html**

The CSS to copy is in approval.html lines 3775-4050. Key sections:
- `.tap-indicator` with `::before` and `::after`
- `@keyframes tapBounce` and `tapRipple1`
- `.long-press-indicator` with animations
- `.double-tap-indicator`
- `.swipe-indicator` with trajectory line and dot
- `@keyframes swipeMove`, `swipeTrailPulse`

**Step 2: Replace gesture indicator CSS in report.html**

In `report.html`, find the existing gesture indicator CSS (around lines 631-695) and replace with the enhanced version from approval.html.

Replace lines 631-695 with:

```css
/* ═══════════════════════════════════════════════════════════
   Enhanced Gesture Indicators - Material Touch Feedback
   ═══════════════════════════════════════════════════════════ */

/* Tap indicator - High contrast with dark outline */
.tap-indicator {{
    position: absolute;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--md-primary);
    border: 3px solid #fff;
    box-shadow:
        0 0 0 2px rgba(0, 0, 0, 0.8),
        0 4px 12px rgba(0, 0, 0, 0.5),
        0 0 20px rgba(208, 188, 255, 0.6);
    transform: translate(-50%, -50%);
    pointer-events: none;
    animation: tapBounce 1.5s cubic-bezier(0.34, 1.56, 0.64, 1) infinite;
}}

/* Inner dot */
.tap-indicator::before {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 14px;
    height: 14px;
    background: #fff;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}}

/* Ripple ring */
.tap-indicator::after {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 60px;
    height: 60px;
    border: 3px solid #fff;
    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.5);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    animation: tapRipple1 1.5s ease-out infinite;
}}

@keyframes tapBounce {{
    0%, 100% {{
        transform: translate(-50%, -50%) scale(1);
        filter: drop-shadow(0 0 12px rgba(208, 188, 255, 1));
    }}
    50% {{
        transform: translate(-50%, -50%) scale(0.85);
        filter: drop-shadow(0 0 20px rgba(208, 188, 255, 1));
    }}
}}

@keyframes tapRipple1 {{
    0% {{
        transform: translate(-50%, -50%) scale(0.6);
        opacity: 1;
    }}
    100% {{
        transform: translate(-50%, -50%) scale(1.6);
        opacity: 0;
    }}
}}

/* Long press indicator - High contrast progress ring */
.long-press-indicator {{
    position: absolute;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.4);
    border: 3px solid #fff;
    box-shadow:
        0 0 0 2px rgba(0, 0, 0, 0.8),
        0 4px 16px rgba(0, 0, 0, 0.5),
        0 0 20px rgba(208, 188, 255, 0.5);
    transform: translate(-50%, -50%);
    pointer-events: none;
}}

/* Inner dot */
.long-press-indicator::before {{
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 18px;
    height: 18px;
    background: var(--md-primary);
    border: 2px solid #fff;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    animation: longPressPulse 1s ease-in-out infinite;
}}

/* Animated progress arc */
.long-press-indicator::after {{
    content: '';
    position: absolute;
    top: -3px;
    left: -3px;
    width: calc(100% + 6px);
    height: calc(100% + 6px);
    border-radius: 50%;
    border: 4px solid transparent;
    border-top-color: var(--md-primary);
    border-right-color: var(--md-primary);
    box-sizing: border-box;
    animation: longPressProgress 1.5s linear infinite;
    filter: drop-shadow(0 0 6px rgba(208, 188, 255, 0.8));
}}

@keyframes longPressPulse {{
    0%, 100% {{ transform: translate(-50%, -50%) scale(1); }}
    50% {{ transform: translate(-50%, -50%) scale(0.8); }}
}}

@keyframes longPressProgress {{
    0% {{ transform: rotate(0deg); }}
    100% {{ transform: rotate(360deg); }}
}}

/* Swipe indicator - Modern gradient trail */
.swipe-indicator {{
    position: absolute;
    pointer-events: none;
    z-index: 10;
    transform: translate(-50%, -50%);
}}

/* Trajectory line - smooth gradient with glow */
.swipe-indicator .swipe-trajectory-line {{
    position: absolute;
    left: 0;
    top: 0;
    width: var(--line-length, 100px);
    height: 3px;
    background: linear-gradient(
        90deg,
        rgba(208, 188, 255, 0.1) 0%,
        rgba(208, 188, 255, 0.4) 20%,
        rgba(208, 188, 255, 0.8) 80%,
        var(--md-primary) 100%
    );
    transform-origin: 0 50%;
    transform: rotate(var(--line-angle, 0deg));
    border-radius: 2px;
    filter: drop-shadow(0 0 6px rgba(208, 188, 255, 0.5));
    animation: swipeTrailPulse 1.8s ease-in-out infinite;
}}

/* Arrow at end of swipe */
.swipe-indicator .swipe-trajectory-line::after {{
    content: '';
    position: absolute;
    right: -6px;
    top: 50%;
    transform: translateY(-50%);
    width: 0;
    height: 0;
    border-left: 10px solid var(--md-primary);
    border-top: 6px solid transparent;
    border-bottom: 6px solid transparent;
    filter: drop-shadow(0 0 4px rgba(208, 188, 255, 0.8));
}}

/* Animated dot with glow */
.swipe-indicator .swipe-dot {{
    position: absolute;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: radial-gradient(circle, #fff 30%, var(--md-primary) 100%);
    transform: translate(-50%, -50%);
    left: 0;
    top: 0;
    animation: swipeMove 1.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
    filter: drop-shadow(0 0 10px rgba(208, 188, 255, 0.9));
}}

@keyframes swipeTrailPulse {{
    0%, 100% {{ opacity: 0.8; }}
    50% {{ opacity: 1; }}
}}

@keyframes swipeMove {{
    0%, 10% {{
        left: 0;
        top: 0;
    }}
    90%, 100% {{
        left: var(--end-left, 0);
        top: var(--end-top, 0);
    }}
}}
```

**Step 3: Verify the template renders**

Run: `python -c "from mutcli.core.report import ReportGenerator; print('Template loads OK')"`
Expected: "Template loads OK"

**Step 4: Commit**

```bash
git add mutcli/templates/report.html
git commit -m "feat(report): add enhanced gesture indicator CSS with animations"
```

---

## Task 5: Update JavaScript for Gesture Positioning

**Files:**
- Modify: `mutcli/templates/report.html` (JS section, around lines 820-908)

**Step 1: Update positionGestureIndicators function**

Replace the `positionIndicator` function (around line 888-904) with enhanced version that handles swipe trajectories:

```javascript
function positionIndicator(container, img, indicatorContainer) {{
    // Get the actual rendered image bounds (accounting for object-fit: contain)
    const bounds = getRenderedImageBounds(img);

    // Get position of img element relative to container (accounts for flex centering)
    const imgRect = img.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    const imgOffsetX = imgRect.left - containerRect.left;
    const imgOffsetY = imgRect.top - containerRect.top;

    // Position indicator container to match actual rendered image content
    indicatorContainer.style.left = (imgOffsetX + bounds.x) + 'px';
    indicatorContainer.style.top = (imgOffsetY + bounds.y) + 'px';
    indicatorContainer.style.width = bounds.width + 'px';
    indicatorContainer.style.height = bounds.height + 'px';

    // Position individual indicators within container
    indicatorContainer.querySelectorAll('.tap-indicator, .long-press-indicator').forEach(indicator => {{
        // These use percentage-based positioning from data attributes
        // CSS transform: translate(-50%, -50%) handles centering
    }});

    // Handle swipe indicators with trajectory
    indicatorContainer.querySelectorAll('.swipe-indicator').forEach(indicator => {{
        const startX = parseFloat(indicator.dataset.x) || 0;
        const startY = parseFloat(indicator.dataset.y) || 0;
        const endX = parseFloat(indicator.dataset.endX) || startX;
        const endY = parseFloat(indicator.dataset.endY) || startY;

        // Convert percentages to pixels within rendered bounds
        const sx = (startX / 100) * bounds.width;
        const sy = (startY / 100) * bounds.height;
        const ex = (endX / 100) * bounds.width;
        const ey = (endY / 100) * bounds.height;

        // Position indicator at start point
        indicator.style.left = sx + 'px';
        indicator.style.top = sy + 'px';

        // Calculate line angle and length
        const dx = ex - sx;
        const dy = ey - sy;
        const length = Math.sqrt(dx * dx + dy * dy);
        const angle = Math.atan2(dy, dx) * (180 / Math.PI);

        // Set CSS custom properties for trajectory line
        indicator.style.setProperty('--line-length', length + 'px');
        indicator.style.setProperty('--line-angle', angle + 'deg');

        // Set end position for dot animation
        indicator.style.setProperty('--end-left', dx + 'px');
        indicator.style.setProperty('--end-top', dy + 'px');
    }});
}}
```

**Step 2: Test manually with a report**

Run a test that includes swipes and view the report:
```bash
mut run tests/calculator-simple/test.yaml --output tests/calculator-simple/runs/test-gestures
```

Open the generated `report.html` and verify:
- Tap indicators show with bouncing animation
- Swipe indicators show trajectory line with animated dot

**Step 3: Commit**

```bash
git add mutcli/templates/report.html
git commit -m "feat(report): add JS for swipe trajectory positioning and animation"
```

---

## Task 6: Add Long Press Indicator Support

**Files:**
- Modify: `mutcli/core/report.py:337-376` (_generate_gesture_indicator_html)

**Step 1: Add long_press case to gesture indicator generation**

In `_generate_gesture_indicator_html`, update the tap section to also handle long_press:

```python
if action in ("tap", "double_tap"):
    return f"""<div class="gesture-indicator-container">
<div class="tap-indicator" style="left: {x:.1f}%; top: {y:.1f}%;"></div>
</div>"""

if action == "long_press":
    return f"""<div class="gesture-indicator-container">
<div class="long-press-indicator" style="left: {x:.1f}%; top: {y:.1f}%;"></div>
</div>"""
```

**Step 2: Run tests**

Run: `pytest tests/test_report.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add mutcli/core/report.py
git commit -m "feat(report): add long press indicator support"
```

---

## Task 7: Final Integration Test

**Step 1: Create a test file with all gesture types**

Create `tests/gesture-test/test.yaml`:

```yaml
config:
  app: com.google.android.calculator

setup:
  - launch_app

tests:
  - name: All Gestures Test
    steps:
      - tap: "7"
      - tap: "+"
      - tap: "3"
      - swipe:
          direction: up
          distance: 30
      - tap: "="
```

**Step 2: Run the test with report generation**

```bash
mut run tests/gesture-test/test.yaml --output tests/gesture-test/runs/final-test
```

**Step 3: Verify report**

Open `tests/gesture-test/runs/final-test/report.html` in browser:
- [ ] Tap indicators animate with purple glow and ripple
- [ ] Swipe indicator shows gradient trail with moving dot
- [ ] All indicators positioned correctly on before-frame images
- [ ] Animations are smooth and loop properly

**Step 4: Final commit**

```bash
git add -A
git commit -m "test: add gesture visualization integration test"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Trajectory synthesis in executor | executor.py |
| 2 | Include trajectory in report data | report.py |
| 3 | Swipe indicator HTML generation | report.py |
| 4 | Enhanced gesture CSS | report.html |
| 5 | JS trajectory positioning | report.html |
| 6 | Long press indicator support | report.py |
| 7 | Integration test | test.yaml |
