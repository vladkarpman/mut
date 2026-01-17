# AI Analysis Optimization Design

**Date:** 2026-01-17
**Status:** Approved
**Goal:** Better quality, faster processing, cheaper API usage for "Analyzing with AI..." phase

## Problem

Current AI analysis during recording processing:
- 2N sequential API calls for N steps (slow, expensive)
- No progress visibility ("Analyzing with AI..." with no feedback)
- Same prompt for all gesture types (suboptimal quality)
- No retry handling (failures break the flow)

## Solution Overview

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| API calls | 2N | N | 50% fewer |
| Latency (10 steps) | ~20-40s | ~2-4s | 10x faster |
| Cost | 2N calls | N calls | 50% cheaper |
| Quality | 2 frames | 3-4 frames + gesture context | Better |

## Architecture

### Gesture Detection (TouchMonitor)

| Gesture | Criteria |
|---------|----------|
| tap | duration < 200ms AND path < 50px |
| swipe | path >= 100px |
| long_press | duration >= 500ms AND path < 100px |

### Frame Extraction (FrameExtractor)

| Gesture | Frames |
|---------|--------|
| tap | before, touch, after (3 frames) |
| swipe | before, swipe_start, swipe_end, after (4 frames) |
| long_press | before, press_start, press_held, after (4 frames) |

### API Call Strategy

- **1 call per step** (down from 2)
- **All steps in parallel** using `asyncio.as_completed()`
- **Gesture-specific prompts** for optimal quality

## Gesture-Specific Prompts

### Tap (3 frames)

```
Analyze this TAP interaction on a mobile app.

Screenshots:
1. BEFORE - stable state before tap
2. TOUCH - moment of tap (shows target element)
3. AFTER - result after UI settled

Tap coordinates: ({x}, {y})

Respond with JSON:
{
  "element_text": "button/field text or null",
  "element_type": "button|text_field|link|icon|checkbox|other",
  "before_description": "brief UI state before",
  "after_description": "brief UI state after",
  "suggested_verification": "verification phrase or null"
}
```

### Swipe (4 frames)

```
Analyze this SWIPE gesture on a mobile app.

Screenshots:
1. BEFORE - stable state before swipe
2. SWIPE_START - finger down position
3. SWIPE_END - finger up position
4. AFTER - result after UI settled

Start: ({start_x}, {start_y}) -> End: ({end_x}, {end_y})

Respond with JSON:
{
  "direction": "up|down|left|right",
  "content_changed": "what scrolled into/out of view",
  "before_description": "brief UI state before",
  "after_description": "brief UI state after",
  "suggested_verification": "verification phrase or null"
}
```

### Long Press (4 frames)

```
Analyze this LONG PRESS gesture on a mobile app.

Screenshots:
1. BEFORE - stable state before press
2. PRESS_START - finger down on element
3. PRESS_HELD - during hold (may show visual feedback)
4. AFTER - result (context menu, selection, etc.)

Press coordinates: ({x}, {y}), Duration: {duration_ms}ms

Respond with JSON:
{
  "element_text": "pressed element text or null",
  "element_type": "list_item|text|image|icon|other",
  "result_type": "context_menu|selection|drag_start|other",
  "before_description": "brief UI state before",
  "after_description": "brief UI state after",
  "suggested_verification": "verification phrase or null"
}
```

## Parallel Execution

```python
async def analyze_all_parallel(
    self,
    touch_events: list[dict],
    screenshots_dir: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[AnalyzedStep]:
    """Analyze all steps in parallel with progress callback."""
    tasks = []
    for i, event in enumerate(touch_events):
        task = self._analyze_with_retry(i, event, screenshots_dir)
        tasks.append(task)

    results = [None] * len(tasks)
    completed = 0

    for coro in asyncio.as_completed(tasks):
        index, result = await coro
        results[index] = result
        completed += 1
        if on_progress:
            on_progress(completed, len(tasks))

    return results
```

## Progress Display

```
Analyzing... ━━━━━━━━━━━━━━━━━━━━ 70%
```

Using Rich progress bar with percentage display.

## Retry Strategy

| Setting | Value | Rationale |
|---------|-------|-----------|
| Max retries | 2 | 3 total attempts |
| Initial delay | 500ms | Fast first retry |
| Backoff | 2x | 500ms -> 1s -> 2s |
| Retry on | Rate limit, timeout, 5xx | Not on 4xx |

```python
async def _analyze_with_retry(
    self,
    index: int,
    event: dict,
    screenshots_dir: Path,
    max_retries: int = 2,
) -> tuple[int, AnalyzedStep]:
    """Analyze single step with exponential backoff retry."""
    delay = 0.5
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            result = await self._analyze_single_step(index, event, screenshots_dir)
            return (index, result)
        except (RateLimitError, TimeoutError, ServerError) as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 2

    return (index, self._placeholder_result(index, event, str(last_error)))
```

## Files to Modify

1. **mutcli/core/ai_analyzer.py**
   - Add async `analyze_tap()`, `analyze_swipe()`, `analyze_long_press()` methods
   - Gesture-specific prompts with appropriate frame handling

2. **mutcli/core/step_analyzer.py**
   - Add `analyze_all_parallel()` with progress callback
   - Add `_analyze_with_retry()` for exponential backoff
   - Route to correct analyzer method based on gesture type

3. **mutcli/cli.py**
   - Replace sequential analysis with `asyncio.run(analyze_all_parallel())`
   - Integrate Rich progress bar (0% -> 100%)

## Error Handling

- Per-step failures don't block other steps
- Failed steps after all retries get placeholder result with `error: true`
- Final summary shows success/failure count
- Failed steps fall back to coordinate-only in YAML
