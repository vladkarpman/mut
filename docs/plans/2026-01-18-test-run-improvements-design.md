# Test Run Improvements Design

## Overview

Improve the `mut run` command with better terminal output, parallel AI analysis, and enhanced AI prompts.

## Components

### 1. Terminal Output (Smart Default)

**Normal output:**
```
mut run tests/calculator-simple-14/test.yaml

┌─────────────────────────────────────────────┐
│  Test: calculator-simple-14                 │
│  App:  com.google.android.calculator        │
│  Steps: 16 (setup: 1, main: 15)             │
└─────────────────────────────────────────────┘

Using device: SM-S911B (RFCW318P7NV)
Connecting to device for video recording...

Running test...
████████████████░░░░░░░░ 12/16  tap 'multiply'

AI analysis...
████████████████████████ 16/16

✓ PASSED (4.2s)
Report: tests/calculator-simple-14/reports/...
```

**On failure - show failed step details:**
```
Running test...
████████████████░░░░░░░░ 12/16  tap 'equals'

✗ FAILED at step 12 (3.1s)
  Action: tap 'equals'
  Error: Element 'equals' not found

AI analysis...
████████████████████████ 12/12

Report: ...
```

**With `--verbose` - show all steps:**
```
[1/16] ✓ launch_app (0.8s)
[2/16] ✓ tap '1' at (15.5%, 83.2%) (0.2s)
...
```

### 2. Parallel AI Analysis

Add `analyze_all_steps_parallel()` to `StepVerifier`:
- Async method using `asyncio.as_completed()`
- Exponential backoff retry for rate limits (429)
- Progress callback for progress bar
- Same result format as sequential method

Pattern already exists in `StepAnalyzer.analyze_collapsed_steps_parallel()`.

### 3. Enhanced AI Prompt

**Current prompt issues:**
- No app/test context
- No coordinate hints
- Generic suggestions
- No failure pattern guidance

**Improved prompt structure:**

```
You are analyzing a mobile UI test step execution.

## Context
- App: {app_package}
- Test: {test_name}
- Step {step_number} of {total_steps}
- Previous steps: {brief_history}

## Step Details
- Action: {action}
- Target: "{target}"
- Coordinates: ({x}%, {y}%) on screen
- Reported Status: {reported_status}
- Error (if any): {error}

## Screenshots
Image 1: BEFORE the action
Image 2: AFTER the action

## Your Task

Analyze the visual change between screenshots to determine:

1. **Verification**: Did the action succeed visually?
   - For tap: Was the element tapped? Did expected UI response occur?
   - For type: Was text entered in the correct field?
   - For swipe: Did content scroll/move as expected?

2. **Outcome**: What actually happened on screen?
   - Be specific: "Login button was tapped, loading spinner appeared"
   - Note unexpected changes: "Keyboard appeared blocking the button"

3. **Suggestion** (if failed): What should be fixed?
   - Element not found → suggest correct element text or add wait_for
   - Wrong screen → suggest navigation step
   - Timing issue → suggest adding wait step

## Common Failure Patterns to Check
- Element exists but has different text (e.g., "Sign In" vs "Login")
- Element is off-screen (needs scroll_to)
- Element is covered by keyboard or dialog
- Screen hasn't finished loading (needs wait or wait_for)
- Wrong screen entirely (app navigated elsewhere)

## Response Format
JSON only, no markdown:
{
  "verified": true/false,
  "outcome": "1-2 sentence description of what happened",
  "suggestion": "actionable fix if failed, null if passed",
  "confidence": "high/medium/low"
}
```

## Files to Modify

1. **`mutcli/core/step_verifier.py`**
   - Add `analyze_all_steps_parallel()` async method
   - Add `_analyze_step_async()` with retry logic
   - Update `_build_analysis_prompt()` with enhanced prompt

2. **`mutcli/cli.py`** (run command)
   - Add test summary panel at start
   - Add progress bar for test execution with current step
   - Switch to parallel AI analysis with progress bar
   - Auto-show failed step details
   - Add `--verbose` flag for detailed output

## Implementation Order

1. Update `step_verifier.py` with parallel method and new prompt
2. Update `cli.py` run command with new output format
3. Test with existing calculator tests
