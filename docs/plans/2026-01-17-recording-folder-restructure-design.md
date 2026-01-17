# Recording Folder Restructure Design

**Date:** 2026-01-17
**Status:** Draft
**Goal:** Flatten folder structure, save AI analysis results, fix typing handling

## Problem

1. **Nested folder structure** - Redundant `recording/` subfolder adds unnecessary depth
2. **AI analysis lost on failure** - If preview server fails (port in use), all AI work is lost
3. **Typing broken** - Individual keyboard taps shown in UI instead of collapsed "type" action; text asked after approval UI

## Solution Overview

| Issue | Before | After |
|-------|--------|-------|
| Folder structure | `tests/name/recording/...` | `tests/name/...` (flat) |
| AI results | Lost on failure | Saved to `analysis.json` |
| Typing in UI | Individual taps | Single "type" step with text input |

## New Folder Structure

```
tests/calculator_demo/
├── test.yaml              # Final generated test
├── video.mp4              # Screen recording
├── touch_events.json      # Raw touch data from device
├── analysis.json          # Processed data for approval UI (NEW)
└── screenshots/           # Extracted frames
    └── step_XXX_{before,touch,after}.png
```

## analysis.json Structure

This file contains everything needed to render the approval UI and generate YAML.

```json
{
  "version": 1,
  "created_at": "2026-01-17T21:57:12Z",
  "app_package": "com.google.android.calculator",
  "screen": {
    "width": 1080,
    "height": 2400
  },
  "steps": [
    {
      "index": 1,
      "action": "tap",
      "timestamp": 2.04,
      "coordinates": { "x": 364, "y": 1666 },
      "element_text": "2",
      "before_description": "Calculator app is open with empty display",
      "after_description": "The digit 2 appears in display",
      "frames": {
        "before": "screenshots/step_001_before.png",
        "touch": "screenshots/step_001_touch.png",
        "after": "screenshots/step_001_after.png"
      },
      "verification": null,
      "enabled": true
    },
    {
      "index": 2,
      "action": "type",
      "timestamp": 3.50,
      "text": null,
      "tap_count": 5,
      "element_text": "keyboard",
      "before_description": "Text field is focused",
      "after_description": "Text entered in field",
      "frames": {
        "before": "screenshots/step_002_before.png",
        "after": "screenshots/step_006_after.png"
      },
      "verification": null,
      "enabled": true
    },
    {
      "index": 7,
      "action": "swipe",
      "timestamp": 8.20,
      "start": { "x": 540, "y": 1800 },
      "end": { "x": 540, "y": 600 },
      "direction": "up",
      "before_description": "List showing first items",
      "after_description": "List scrolled to show more items",
      "frames": {
        "before": "screenshots/step_007_before.png",
        "swipe_start": "screenshots/step_007_swipe_start.png",
        "swipe_end": "screenshots/step_007_swipe_end.png",
        "after": "screenshots/step_007_after.png"
      },
      "verification": null,
      "enabled": true
    },
    {
      "index": 8,
      "action": "long_press",
      "timestamp": 10.50,
      "coordinates": { "x": 400, "y": 800 },
      "duration_ms": 650,
      "element_text": "List item",
      "before_description": "Item in normal state",
      "after_description": "Context menu appeared",
      "frames": {
        "before": "screenshots/step_008_before.png",
        "press_start": "screenshots/step_008_press_start.png",
        "press_held": "screenshots/step_008_press_held.png",
        "after": "screenshots/step_008_after.png"
      },
      "verification": "context menu is visible",
      "enabled": true
    }
  ]
}
```

### Step Fields by Action Type

| Field | tap | type | swipe | long_press |
|-------|-----|------|-------|------------|
| index | Y | Y | Y | Y |
| action | Y | Y | Y | Y |
| timestamp | Y | Y | Y | Y |
| coordinates | Y | - | - | Y |
| start/end | - | - | Y | - |
| direction | - | - | Y | - |
| duration_ms | - | - | - | Y |
| text | - | Y | - | - |
| tap_count | - | Y | - | - |
| element_text | Y | Y | - | Y |
| before_description | Y | Y | Y | Y |
| after_description | Y | Y | Y | Y |
| frames | Y | Y | Y | Y |
| verification | Y | Y | Y | Y |
| enabled | Y | Y | Y | Y |

## Processing Pipeline

```
┌─────────────────┐
│ touch_events.json│  Raw device data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Typing Detection │  Identify keyboard sequences
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step Collapsing  │  Merge typing taps → single "type" step
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Frame Extraction │  Extract screenshots per collapsed step
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ AI Analysis      │  Analyze collapsed steps (skip keyboard taps)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save analysis.json│  ← NEW: Persist here
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Approval UI      │  Load from analysis.json
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Generate YAML    │  From approved steps
└─────────────────┘
```

## Typing Handling

### Before (Current)

1. Record touch events (individual taps)
2. Extract frames for each tap
3. AI analyzes each tap individually
4. Show individual taps in approval UI
5. After approval, ask "what text was typed?"
6. Generate YAML

**Problems:**
- AI wastes calls on keyboard taps
- UI shows confusing individual taps
- Text asked too late (after approval)

### After (New)

1. Record touch events (individual taps)
2. **Detect typing sequences** (fast taps in keyboard area)
3. **Collapse into single "type" steps** (with placeholder text)
4. Extract frames only for first/last of sequence
5. AI analyzes collapsed steps (skips keyboard taps)
6. Show "type" action in approval UI with text input
7. User enters text in approval UI
8. Generate YAML

**Benefits:**
- Fewer AI calls (typing = 1 call, not N)
- Clear UI (shows "type" action)
- Text entered during approval (not after)

## Files to Modify

### 1. mutcli/core/recorder.py
- Change output paths from `recording/` to root
- `recording.mp4` → `video.mp4`

### 2. mutcli/cli.py (_process_recording)
- Reorder: typing detection → collapse → frame extraction → AI
- Save `analysis.json` after AI completes
- Load from `analysis.json` if exists (recovery)
- Update all paths (remove `recording/` prefix)

### 3. mutcli/core/step_collapsing.py (NEW)
- Take touch_events + typing_sequences
- Return collapsed steps (typing merged)
- Renumber indices

### 4. mutcli/core/frame_extractor.py
- Update paths (remove `recording/` prefix)
- Handle typing: extract only before (first tap) and after (last tap)

### 5. mutcli/core/step_analyzer.py
- Skip AI analysis for "type" action (no visual change per keystroke)
- Use generic descriptions for typing

### 6. mutcli/core/preview_server.py
- Update file serving paths
- PreviewStep: support "type" action with text field

### 7. mutcli/templates/approval.html
- Add text input for "type" actions
- Show tap_count for typing steps

### 8. mutcli/core/yaml_generator.py
- Handle "type" action from approval result

## Migration

Existing test folders with `recording/` subfolder will still work - the code checks both locations for backward compatibility.

## Error Handling

- If `analysis.json` exists and is valid, skip re-analysis
- If `analysis.json` is corrupt/incomplete, re-run analysis
- Preview server failure no longer loses work (analysis.json persisted)
