# CLI Live Output Design

## Overview

Add Maestro-style live CLI output during test execution. Show each step's status in real-time with emoji indicators.

## Output Format

```
┌─ calculator-simple ──────────────────
│ ✅ terminate_app
│ ✅ launch_app
│ ✅ tap "7"
│ ✅ tap "+"
│ ✅ tap "3"
│ ✅ tap "="
│ ✅ 🔍 verify "Display shows 10"
└─ ✓ PASSED (3.2s) ────────────────────
```

**On failure:**
```
┌─ calculator-simple ──────────────────
│ ✅ terminate_app
│ ✅ launch_app
│ ✅ tap "7"
│ ❌ tap "Submit"
│    Element 'Submit' not found
│ ⏭️ tap "="  (skipped)
│ ⏭️ 🔍 verify "Display shows 10"  (skipped)
└─ ✗ FAILED (1.8s) ────────────────────
```

## Status Icons

| Status | Icon | Description |
|--------|------|-------------|
| Running | ⏳ | Step currently executing |
| Passed | ✅ | Step completed successfully |
| Failed | ❌ | Step failed |
| Skipped | ⏭️ | Step skipped (after failure) |
| Verify | 🔍 | Prefix for verify_screen steps |

## Architecture

### New File: `mutcli/core/console_reporter.py`

```python
from dataclasses import dataclass
from rich.live import Live
from rich.panel import Panel

@dataclass
class StepDisplay:
    step_num: int
    action: str
    target: str | None
    status: str  # pending, running, passed, failed, skipped
    error: str | None = None

class ConsoleReporter:
    """Live console output for test execution."""

    def __init__(self, test_name: str, total_steps: int):
        self._test_name = test_name
        self._total_steps = total_steps
        self._steps: list[StepDisplay] = []
        self._live: Live | None = None

    def start(self) -> None:
        """Start live display."""

    def step_started(self, step_num: int, action: str, target: str | None) -> None:
        """Called when a step begins executing."""

    def step_completed(self, step_num: int, status: str, error: str | None = None) -> None:
        """Called when a step finishes."""

    def mark_remaining_skipped(self, from_step: int) -> None:
        """Mark all steps from given index as skipped."""

    def finish(self, status: str, duration: float) -> None:
        """Called when test completes."""

    def _render(self) -> Panel:
        """Build the current display panel."""
```

### Executor Integration

Add optional reporter to `TestExecutor.__init__()`:

```python
def __init__(
    self,
    ...
    reporter: ConsoleReporter | None = None,
):
    self._reporter = reporter
```

Emit events in `execute_step()`:

```python
def execute_step(self, step: Step) -> StepResult:
    # Notify step starting
    if self._reporter:
        self._reporter.step_started(
            step_num=self._step_number,
            action=step.action,
            target=step.target or step.condition_target,
        )

    # ... existing execution logic ...

    # Notify step completed
    if self._reporter:
        self._reporter.step_completed(
            step_num=self._step_number,
            status=result.status,
            error=result.error,
        )
```

### CLI Integration

In `cli.py` run command:

```python
reporter = ConsoleReporter(test_name, total_steps)
executor = TestExecutor(..., reporter=reporter)

reporter.start()
result = executor.execute_test(test, record_video=video)
reporter.finish(result.status, result.duration)
```

## Design Decisions

1. **Always verbose** - Show every step by default (like Maestro)
2. **Minimal format** - Action + target only, no duration per step
3. **Distinct verify icon** - 🔍 makes AI verifications stand out
4. **Inline errors** - Error message immediately below failed step
5. **Framed output** - Visual container with test name
6. **Trust Rich** - Let Rich handle TTY detection for ANSI/plain text
7. **Flatten nested** - Nested steps (conditionals, repeat) shown at same level

## Files Changed

| File | Change |
|------|--------|
| `mutcli/core/console_reporter.py` | NEW (~100 lines) |
| `mutcli/core/executor.py` | Add reporter parameter and event calls |
| `mutcli/cli.py` | Wire up ConsoleReporter in run command |

## Backwards Compatibility

- `--verbose` flag kept as no-op (always verbose now)
- No changes to test execution logic
- No changes to report generation
