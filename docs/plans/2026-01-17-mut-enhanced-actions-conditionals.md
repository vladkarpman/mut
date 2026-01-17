# Enhanced Actions & Conditionals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add missing actions (`scroll_to`, `long_press`) and conditional execution (`if_present`, `if_absent`, `if_screen`) to the test executor.

**Architecture:** Extend DeviceController with new device operations, add action handlers to TestExecutor, extend Step model and parser for conditional YAML syntax.

**Tech Stack:** Existing mutcli architecture, adb commands via DeviceController

---

## Task 1: Add DeviceController Methods

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/device_controller.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_device_controller.py`

**Add two new methods:**

```python
def long_press(self, x: int, y: int, duration_ms: int = 500) -> None:
    """Long press at coordinates.

    Args:
        x: X coordinate in pixels
        y: Y coordinate in pixels
        duration_ms: Duration in milliseconds (default: 500)
    """
    # adb shell input swipe x y x y duration_ms
    # (swipe from same point to same point = long press)

def double_tap(self, x: int, y: int, delay_ms: int = 100) -> None:
    """Double tap at coordinates.

    Args:
        x: X coordinate in pixels
        y: Y coordinate in pixels
        delay_ms: Delay between taps (default: 100)
    """
    # Two taps with short delay
```

**Note:** We're adding `double_tap` to DeviceController for completeness even though we won't use it in executor yet.

**Tests:**
1. `test_long_press_executes_adb_command`
2. `test_long_press_default_duration`
3. `test_double_tap_executes_two_taps`

**Commit:** `feat(device): add long_press and double_tap methods`

---

## Task 2: Add Simple Action Handlers

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/executor.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_executor.py`

**Add action handlers:**

```python
def _action_long_press(self, step: Step) -> str | None:
    """Execute long press action."""
    coords = self._resolve_coordinates(step)
    if coords is None:
        return f"Element '{step.target}' not found"

    duration = step.duration or 500  # Default 500ms
    self._device.long_press(coords[0], coords[1], duration)
    return None

def _action_scroll_to(self, step: Step) -> str | None:
    """Scroll until element is visible."""
    target = step.target
    if not target:
        return "No element specified for scroll_to"

    direction = step.direction or "down"
    max_scrolls = step.max_scrolls or 10

    for _ in range(max_scrolls):
        # Check if element exists
        coords = self._device.find_element(target)
        if coords:
            return None  # Found it

        # Swipe in direction
        self._do_swipe(direction)

    return f"Element '{target}' not found after {max_scrolls} scrolls"
```

**Step model additions needed (in models/test.py):**
- `duration: int | None = None` - For long_press
- `max_scrolls: int | None = None` - For scroll_to

**Tests:**
1. `test_long_press_action`
2. `test_long_press_with_custom_duration`
3. `test_scroll_to_finds_element`
4. `test_scroll_to_max_scrolls_exceeded`
5. `test_scroll_to_respects_direction`

**Commit:** `feat(executor): add scroll_to and long_press actions`

---

## Task 3: Extend Step Model for Conditionals

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/models/test.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_models.py`

**Add fields to Step dataclass:**

```python
@dataclass
class Step:
    action: str
    target: str | None = None
    # ... existing fields ...

    # Conditional fields
    condition_type: str | None = None  # "if_present", "if_absent", "if_screen"
    condition_target: str | None = None  # Element name or screen description
    then_steps: list["Step"] | None = None
    else_steps: list["Step"] | None = None
```

**Tests:**
1. `test_step_with_conditional_fields`
2. `test_step_nested_then_steps`
3. `test_step_with_else_branch`

**Commit:** `feat(models): extend Step model for conditionals`

---

## Task 4: Update Parser for Conditionals

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/parser.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_parser.py`

**Parse new YAML structures:**

```yaml
# if_present
- if_present: "Cookie Banner"
  then:
    - tap: "Accept"

# if_absent
- if_absent: "Login Button"
  then:
    - tap: "Logout"

# if_screen with else
- if_screen: "Two-factor auth"
  then:
    - type: "123456"
  else:
    - verify_screen: "Dashboard"
```

**Parser logic:**

```python
def _parse_step(self, step_data: dict) -> Step:
    # Check for conditional
    for cond_type in ("if_present", "if_absent", "if_screen"):
        if cond_type in step_data:
            return Step(
                action=cond_type,
                condition_type=cond_type,
                condition_target=step_data[cond_type],
                then_steps=[self._parse_step(s) for s in step_data.get("then", [])],
                else_steps=[self._parse_step(s) for s in step_data.get("else", [])] if "else" in step_data else None,
            )

    # ... existing parsing ...
```

**Tests:**
1. `test_parse_if_present`
2. `test_parse_if_absent`
3. `test_parse_if_screen`
4. `test_parse_conditional_with_else`
5. `test_parse_nested_conditionals`

**Commit:** `feat(parser): support conditional YAML syntax`

---

## Task 5: Implement Conditional Execution

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/executor.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_executor.py`

**Add conditional handlers:**

```python
def _action_if_present(self, step: Step) -> str | None:
    """Execute then/else based on element presence."""
    target = step.condition_target
    coords = self._device.find_element(target)

    if coords:
        # Element found, execute then
        return self._execute_nested_steps(step.then_steps)
    elif step.else_steps:
        # Element not found, execute else
        return self._execute_nested_steps(step.else_steps)

    return None  # No else branch, just skip

def _action_if_absent(self, step: Step) -> str | None:
    """Execute then/else based on element absence."""
    target = step.condition_target
    coords = self._device.find_element(target)

    if coords is None:
        # Element not found, execute then
        return self._execute_nested_steps(step.then_steps)
    elif step.else_steps:
        # Element found, execute else
        return self._execute_nested_steps(step.else_steps)

    return None

def _action_if_screen(self, step: Step) -> str | None:
    """Execute then/else based on AI screen verification."""
    description = step.condition_target
    screenshot = self._device.take_screenshot()

    result = self._ai.verify_screen(screenshot, description)

    if result.get("pass"):
        return self._execute_nested_steps(step.then_steps)
    elif step.else_steps:
        return self._execute_nested_steps(step.else_steps)

    return None

def _execute_nested_steps(self, steps: list[Step] | None) -> str | None:
    """Execute a list of nested steps."""
    if not steps:
        return None

    for step in steps:
        result = self.execute_step(step)
        if result.status == "failed":
            return result.error

    return None
```

**Tests:**
1. `test_if_present_executes_then_when_found`
2. `test_if_present_executes_else_when_not_found`
3. `test_if_present_skips_when_not_found_no_else`
4. `test_if_absent_executes_then_when_not_found`
5. `test_if_absent_executes_else_when_found`
6. `test_if_screen_executes_then_on_match`
7. `test_if_screen_executes_else_on_no_match`
8. `test_nested_conditionals`

**Commit:** `feat(executor): implement conditional execution`

---

## Task 6: Run All Tests and Verify

**Run full test suite:**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest -v
```

**Manual testing (if device available):**

Create test file `tests/conditionals-test/test.yaml`:

```yaml
config:
  app: com.example.app

steps:
  - launch_app
  - wait: 2s

  - if_present: "Cookie Banner"
    then:
      - tap: "Accept"

  - scroll_to: "Settings"
  - long_press: "Settings"

  - terminate_app
```

**Commit:** `feat: complete enhanced actions and conditionals`

---

## Summary

After completing this plan:
- `scroll_to` action scrolls until element found
- `long_press` action with configurable duration
- `if_present` / `if_absent` conditionals for element checks
- `if_screen` conditional for AI-powered screen matching
- Full test coverage for all new features
