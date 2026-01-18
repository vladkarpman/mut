# Report Gesture Visualization Design

**Date**: 2026-01-18
**Status**: Approved
**Goal**: Add approval.html-quality gesture indicators to report.html with trajectory visualization for swipes.

## Overview

Currently, `report.html` has basic static gesture indicators while `approval.html` has sophisticated animated indicators with trajectory visualization. This design brings visual parity to reports.

## Approach: Trajectory Synthesis

For programmatic test execution (`mut run`), we know exactly what gestures were sent to the device. Rather than capturing touches via TouchMonitor (which adds overhead for data we already have), we synthesize trajectory data from known parameters.

| Gesture | Data Available | Enhancement |
|---------|----------------|-------------|
| tap | (x, y) | Visual upgrade only |
| double_tap | (x, y) | Visual upgrade only |
| long_press | (x, y) + duration | Visual upgrade only |
| swipe | start + end + duration | Synthesize 15 intermediate trajectory points |

## Data Model

### StepResult.details (enhanced)

```python
details = {
    "timestamp": 1.234,  # seconds since test start
    "coords": {"x": 50.0, "y": 60.0},  # percentages
    "end_coords": {"x": 50.0, "y": 30.0},  # for swipes
    "direction": "up",
    # NEW fields:
    "trajectory": [
        {"x": 50.0, "y": 60.0, "t": 0},
        {"x": 50.0, "y": 55.0, "t": 30},
        # ... 13 more points ...
        {"x": 50.0, "y": 30.0, "t": 300}
    ],
    "duration_ms": 300
}
```

## Implementation

### 1. executor.py - Trajectory Synthesis

Add helper function:

```python
def _synthesize_trajectory(
    self,
    start: tuple[int, int],
    end: tuple[int, int],
    duration_ms: int,
    num_points: int = 15
) -> list[dict]:
    """Generate trajectory points for swipe visualization.

    Uses ease-out-quad easing for natural finger motion.
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
            "x": x / width * 100,  # Store as percentage
            "y": y / height * 100,
            "t": int(t * duration_ms)
        })

    return points
```

Update `_action_swipe()` to call this and store in `self._step_trajectory`.

Update `execute_step()` to include trajectory in details dict.

### 2. report.py - HTML Generation

Update `_result_to_dict()`:
```python
"trajectory": s.details.get("trajectory"),
"duration_ms": s.details.get("duration_ms"),
```

Update `_generate_gesture_indicator_html()` for swipes:
```python
if action == "swipe":
    trajectory = step.get("trajectory", [])
    traj_json = html.escape(json.dumps(trajectory))
    return f'''<div class="swipe-indicator"
        data-x="{x}" data-y="{y}"
        data-end-x="{end.get('x', x)}" data-end-y="{end.get('y', y)}"
        data-trajectory="{traj_json}">
        <div class="swipe-trajectory-line"></div>
        <div class="swipe-dot"></div>
    </div>'''
```

### 3. report.html - CSS

Copy from approval.html:
- `.tap-indicator` with `::before` (inner dot) and `::after` (ripple)
- `.long-press-indicator` with progress arc
- `.double-tap-indicator` with staggered circles
- `.swipe-indicator` with trajectory line and animated dot
- All `@keyframes`: `tapBounce`, `tapRipple1`, `longPressPulse`, `longPressProgress`, `doubleTap1`, `doubleTap2`, `swipeMove`, `swipeTrailPulse`

### 4. report.html - JavaScript

Update `positionGestureIndicators()` to handle trajectory data:
- Parse trajectory from data attribute
- Set CSS custom properties for animation endpoints
- Calculate line angle and length for trajectory visualization

## Files Changed

| File | Changes |
|------|---------|
| `mutcli/core/executor.py` | Add `_synthesize_trajectory()`, update `_action_swipe()` |
| `mutcli/core/report.py` | Update `_result_to_dict()`, update `_generate_gesture_indicator_html()` |
| `mutcli/templates/report.html` | Copy gesture CSS, update positioning JS |

## Testing

1. Run test with swipes: `mut run tests/calculator-simple/test.yaml`
2. Open generated `report.html`
3. Verify:
   - Tap indicators have bouncing animation with ripple
   - Long-press indicators have rotating progress arc
   - Swipe indicators show gradient trail with animated dot
   - All indicators positioned correctly on before-frame images
