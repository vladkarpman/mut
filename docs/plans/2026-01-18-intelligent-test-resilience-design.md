# Intelligent Test Resilience Design

**Date:** 2026-01-18
**Status:** Approved

## Problem

Tests fail too early due to:
- Elements not found immediately (app still loading/animating)
- Transient UI states causing false failures
- No automatic retry mechanism
- Strict verify_screen without tolerance

## Solution: Two-Layer Resilience

### Architecture

```
Step Execution
     │
     ▼
┌─────────────────────────────────────┐
│  Layer 1: Smart Waits (No AI)       │
│  - Implicit wait for elements       │
│  - Exponential backoff retries      │
│  - Screen stability detection       │
│  - Timeout: 5s default              │
└─────────────────────────────────────┘
     │
     │ Still failing after timeout?
     ▼
┌─────────────────────────────────────┐
│  Layer 2: AI Recovery               │
│  - Analyze screenshot               │
│  - Determine failure type:          │
│    • Similar element exists → find  │
│    • Screen loading → wait more     │
│    • Wrong screen → fail fast       │
│    • Element obscured → suggest fix │
└─────────────────────────────────────┘
     │
     ▼
  Pass / Fail with context
```

### Timing

- **Layer 1:** 5s implicit wait, 500ms polling interval
- **Layer 2:** Single AI call, decides: retry (max 3s more) | try alternative | fail
- **Total worst case:** ~8-10s per failing step

## Layer 1: Smart Waits

### Element Finding with Wait

```python
def _find_element_with_wait(self, target: str, timeout: float = 5.0) -> tuple[int, int] | None:
    """Find element with implicit wait and screen stability detection."""
    start = time.time()
    last_screenshot = None
    stable_count = 0

    while time.time() - start < timeout:
        # Check screen stability (avoid acting during animations)
        screenshot = self._capture_screenshot()
        if screenshot == last_screenshot:
            stable_count += 1
        else:
            stable_count = 0
            last_screenshot = screenshot

        # Only search when screen is stable (2+ identical frames)
        if stable_count >= 1:
            # Try accessibility tree first (fast)
            coords = self._device.find_element(target)
            if coords:
                return coords

            # Try AI vision
            coords = self._ai.find_element(screenshot, target, *self._get_screen_size())
            if coords:
                return coords

        time.sleep(0.5)  # Poll interval

    return None  # Timeout - trigger Layer 2
```

### Key Behaviors

- Waits for screen stability before searching (avoids finding elements mid-animation)
- Polls every 500ms
- Uses accessibility tree first (fast), AI vision as backup
- Returns None after timeout to trigger Layer 2

## Layer 2: AI Recovery

### Data Model

```python
@dataclass
class AIRecoveryResult:
    """Result of AI recovery analysis."""
    action: str  # "retry", "alternative", "fail"
    reason: str  # Human-readable explanation
    wait_seconds: float | None  # Additional wait if action="retry"
    alternative_target: str | None  # New target if action="alternative"
    alternative_coords: tuple[int, int] | None  # Direct coords if found
```

### AI Prompt

```
You are analyzing a mobile UI test failure.

Action attempted: {action} "{target}"
Result: Element not found after 5 seconds

Screenshot shows the current screen state.

Analyze and respond with JSON:
{
  "action": "retry" | "alternative" | "fail",
  "reason": "brief explanation",
  "wait_seconds": number or null,
  "alternative": "different element text" or null,
  "coordinates": [x%, y%] or null
}

Decision guide:
- "retry" + wait_seconds: Screen is loading, spinner visible, or transition in progress
- "alternative" + text: Similar element exists (e.g., "LOG IN" vs "Login")
- "alternative" + coordinates: Element found visually but text differs
- "fail": Element clearly doesn't exist, wrong screen, or unrecoverable state

Be decisive. If clearly wrong screen, fail fast.
```

### Recovery Flow

```
Element not found (Layer 1 timeout)
           │
           ▼
    AI analyzes screenshot
           │
    ┌──────┴──────┬─────────────┐
    ▼             ▼             ▼
 "retry"    "alternative"    "fail"
    │             │             │
    ▼             ▼             ▼
Wait N sec   Use new target   Return error
then retry   or coordinates   with AI reason
(max once)
```

## Integration

### Modified Step Execution

```python
def _execute_with_resilience(self, handler, step: Step) -> str | None:
    """Execute action with two-layer resilience."""

    # Layer 1: Try with smart waits (built into handlers)
    error = handler(step)

    if error is None:
        return None  # Success

    # Layer 2: AI recovery (if enabled and applicable)
    if not self._config.ai_recovery:
        return error

    if not self._is_recoverable_error(error):
        return error  # Not worth AI analysis

    recovery = self._ai_recovery.analyze_failure(
        screenshot=self._capture_screenshot(),
        step=step,
        error=error,
    )

    if recovery.action == "fail":
        return f"{error} (AI: {recovery.reason})"

    if recovery.action == "retry":
        time.sleep(recovery.wait_seconds or 2)
        return handler(step)  # One more attempt

    if recovery.action == "alternative":
        # Modify step with AI suggestion and retry
        modified_step = self._apply_alternative(step, recovery)
        return handler(modified_step)

    return error
```

### Recoverable vs Non-Recoverable Errors

**Recoverable (worth AI analysis):**
- "Element 'X' not found"
- "Timeout waiting for 'X'"
- "verify_screen failed: ..."

**Non-recoverable (fail fast):**
- "Unknown action: X"
- "No text to type"
- "No app package specified"

## Configuration

### Project Config (`.mut.yaml`)

```yaml
config:
  app: com.example.app

  # Resilience settings
  resilience:
    implicit_wait: 5s        # Layer 1 timeout (default: 5s)
    poll_interval: 500ms     # How often to retry (default: 500ms)
    stability_frames: 2      # Stable frames before action (default: 2)
    ai_recovery: true        # Enable Layer 2 (default: true)
    ai_retry_limit: 1        # Max AI-suggested retries (default: 1)
```

### Per-Step Overrides

```yaml
steps:
  - tap: "Submit"
    timeout: 10s          # Slow operation, wait longer

  - tap: "Cancel"
    timeout: 1s           # Known fast, fail quickly
    ai_recovery: false    # Don't bother with AI for this
```

### Environment Variables

```bash
MUT_IMPLICIT_WAIT=5       # Override default (seconds)
MUT_AI_RECOVERY=false     # Disable AI recovery globally
```

## File Changes

| File | Changes |
|------|---------|
| `mutcli/core/executor.py` | Add `_find_element_with_wait()`, `_execute_with_resilience()`, stability detection |
| `mutcli/core/ai_recovery.py` | **New file** - `AIRecovery` class with failure analysis |
| `mutcli/core/config.py` | Add `ResilienceConfig` dataclass, parse new options |
| `mutcli/models/test.py` | Add `timeout`, `ai_recovery` fields to `Step` |
| `tests/test_executor.py` | Tests for resilience behavior |
| `tests/test_ai_recovery.py` | **New file** - Tests for AI recovery |

## Implementation Order

1. **Config changes** - Add ResilienceConfig, parse new options
2. **Step model** - Add timeout/ai_recovery fields
3. **Layer 1** - Implement `_find_element_with_wait()` with stability detection
4. **Update handlers** - Integrate Layer 1 into tap, wait_for, scroll_to, etc.
5. **AI Recovery** - Create `ai_recovery.py` with analysis logic
6. **Integration** - Add `_execute_with_resilience()` wrapper
7. **Tests** - Unit tests for both layers
