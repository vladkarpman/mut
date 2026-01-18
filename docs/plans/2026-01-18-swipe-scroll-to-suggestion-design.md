# Swipe scroll_to Suggestion Design

## Problem

When recording a test, if a user swipes to find an element (e.g., scrolling to "Settings"), it's captured as a raw swipe:

```yaml
- swipe:
    direction: up
    distance: 30
```

This is fragile - different devices/screen sizes may need different distances. The smarter `scroll_to` action would be more robust:

```yaml
- scroll_to: "Settings"
```

Currently, the AI analyzes swipes but doesn't identify scroll intent or suggest converting to `scroll_to`.

## Solution

Add AI-powered detection during recording analysis:
1. AI analyzes before/after screenshots of swipe
2. If a new element appeared after the swipe, suggest it as a `scroll_to` target
3. Show suggestion in approval UI with option to convert

## Data Flow

```
Recording → TouchMonitor captures swipe
         → FrameExtractor gets before/after frames
         → AIAnalyzer.analyze_swipe() detects new element
         → Returns scroll_to_target: "Settings"
         → Approval UI shows: [Convert to scroll_to: "Settings"]
         → User accepts → YamlGenerator outputs scroll_to
```

## Implementation

### 1. ai_analyzer.py - Update SwipeAnalysisResult

```python
@dataclass
class SwipeAnalysisResult:
    direction: str
    content_changed: str
    action_description: str
    before_description: str
    after_description: str
    suggested_verification: str | None
    scroll_to_target: str | None  # NEW: element that appeared after swipe
```

### 2. ai_analyzer.py - Update analyze_swipe prompt

Add to the JSON response format:

```
"scroll_to_target": "element text" or null

scroll_to_target:
- If a specific UI element (button, menu item, text) appeared in AFTER that wasn't visible in BEFORE, return its text/label
- Return null if:
  - Swipe was for dismissing (closing drawer, dismissing dialog)
  - Swipe was for carousel/pagination (no specific target)
  - No new distinct element appeared
- Examples:
  - User scrolls list, "Settings" button appears → "Settings"
  - User swipes to dismiss drawer → null
  - User swipes carousel → null
```

### 3. step_analyzer.py - Pass through field

In `_analyze_swipe_step()`, add to AnalyzedStep:

```python
# Add new field to AnalyzedStep dataclass
@dataclass
class AnalyzedStep:
    # ... existing fields ...
    scroll_to_target: str | None = None  # For swipes: suggested scroll_to target
```

Update `_analyze_swipe_step()`:
```python
return AnalyzedStep(
    # ... existing fields ...
    scroll_to_target=result.get("scroll_to_target"),
)
```

### 4. yaml_generator.py - Handle conversion

Add method to generate scroll_to instead of swipe:

```python
def add_scroll_to(self, target: str, direction: str = "down") -> None:
    """Add scroll_to action."""
    step: dict[str, Any] = {"scroll_to": target}
    if direction != "down":  # down is default
        step["direction"] = direction
    self._steps.append(step)
```

### 5. approval.html - Show suggestion

In the step card for swipe actions, add:

```html
{% if step.scroll_to_target %}
<div class="scroll-to-suggestion">
  <span class="suggestion-icon">💡</span>
  <span>Consider: <code>scroll_to: "{{ step.scroll_to_target }}"</code></span>
  <button class="convert-btn" data-step-index="{{ loop.index0 }}"
          data-target="{{ step.scroll_to_target }}">
    Convert
  </button>
</div>
{% endif %}
```

Add JavaScript to handle conversion:
- On click, update the step data from `swipe` to `scroll_to`
- Update the UI to reflect the change
- Mark step as modified for YAML regeneration

### 6. analysis_io.py - Persist field

Ensure `scroll_to_target` is included when saving/loading analysis JSON.

## Files to Modify

| File | Change |
|------|--------|
| `mutcli/core/ai_analyzer.py` | Add `scroll_to_target` to SwipeAnalysisResult, update prompt |
| `mutcli/core/step_analyzer.py` | Add field to AnalyzedStep, pass through from SwipeAnalysisResult |
| `mutcli/core/yaml_generator.py` | Add `add_scroll_to()` method |
| `mutcli/core/analysis_io.py` | Include new field in serialization |
| `mutcli/templates/approval.html` | Show suggestion, add convert button |
| `tests/test_ai_analyzer.py` | Test new field in swipe analysis |
| `tests/test_step_analyzer.py` | Test field pass-through |

## UI Mockup

```
┌─────────────────────────────────────────────────┐
│ Step 3: Swipe                                   │
│ Direction: up | Distance: 30%                   │
│                                                 │
│ 💡 Consider: scroll_to: "Settings"              │
│    [Convert]                                    │
│                                                 │
│ Before: List shows items 1-5.                   │
│ After: List shows items 6-10, Settings visible. │
└─────────────────────────────────────────────────┘
```

## Edge Cases

1. **Multiple elements appeared** - AI picks the most prominent/interactive one
2. **Element partially visible before** - Only suggest if element became fully actionable
3. **Swipe for dismiss/animation** - AI returns null, no suggestion shown
4. **User declines conversion** - Keep original swipe, no changes

## Testing

1. Record a swipe that reveals a new element → verify suggestion appears
2. Record a swipe to dismiss → verify no suggestion
3. Click Convert → verify YAML changes to scroll_to
4. Verify scroll_to_target persists through save/load cycle
