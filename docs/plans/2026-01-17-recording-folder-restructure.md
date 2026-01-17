# Recording Folder Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Flatten folder structure, save AI analysis to `analysis.json`, fix typing by collapsing sequences before frame extraction.

**Architecture:** Processing pipeline becomes: touch_events → typing detection → collapse steps → frame extraction → AI analysis → save analysis.json → approval UI → YAML. The `analysis.json` file serves as the single source of truth for the approval UI.

**Tech Stack:** Python, dataclasses, JSON, pytest

**Design Doc:** `docs/plans/2026-01-17-recording-folder-restructure-design.md`

---

## Task 1: Create StepCollapsing Module

**Files:**
- Create: `mutcli/core/step_collapsing.py`
- Create: `tests/test_step_collapsing.py`

**Context:** This module takes raw touch events + typing sequences and produces collapsed steps where typing sequences become single "type" actions.

**Step 1: Write the failing test**

```python
"""Tests for step collapsing."""

import pytest
from mutcli.core.step_collapsing import collapse_steps, CollapsedStep
from mutcli.core.typing_detector import TypingSequence


class TestCollapseSteps:
    """Tests for collapse_steps function."""

    def test_no_typing_sequences_returns_all_taps(self):
        """When no typing detected, all taps become individual steps."""
        touch_events = [
            {"timestamp": 1.0, "x": 100, "y": 200, "gesture": "tap", "start_x": 100, "start_y": 200, "duration_ms": 50},
            {"timestamp": 2.0, "x": 300, "y": 400, "gesture": "tap", "start_x": 300, "start_y": 400, "duration_ms": 60},
        ]
        typing_sequences = []

        result = collapse_steps(touch_events, typing_sequences)

        assert len(result) == 2
        assert result[0].action == "tap"
        assert result[0].coordinates == {"x": 100, "y": 200}
        assert result[1].action == "tap"
        assert result[1].coordinates == {"x": 300, "y": 400}

    def test_typing_sequence_collapsed_into_single_step(self):
        """Typing sequence (indices 1-3) becomes single 'type' step."""
        touch_events = [
            {"timestamp": 1.0, "x": 100, "y": 200, "gesture": "tap", "start_x": 100, "start_y": 200, "duration_ms": 50},
            {"timestamp": 2.0, "x": 500, "y": 1800, "gesture": "tap", "start_x": 500, "start_y": 1800, "duration_ms": 30},
            {"timestamp": 2.2, "x": 600, "y": 1850, "gesture": "tap", "start_x": 600, "start_y": 1850, "duration_ms": 25},
            {"timestamp": 2.4, "x": 550, "y": 1820, "gesture": "tap", "start_x": 550, "start_y": 1820, "duration_ms": 35},
            {"timestamp": 3.5, "x": 800, "y": 500, "gesture": "tap", "start_x": 800, "start_y": 500, "duration_ms": 40},
        ]
        typing_sequences = [
            TypingSequence(start_index=1, end_index=3, tap_count=3, duration=0.4, text=None)
        ]

        result = collapse_steps(touch_events, typing_sequences)

        assert len(result) == 3  # tap + type + tap
        assert result[0].action == "tap"
        assert result[1].action == "type"
        assert result[1].tap_count == 3
        assert result[1].original_indices == (1, 3)
        assert result[2].action == "tap"

    def test_swipe_gesture_preserved(self):
        """Swipe gestures include start/end coordinates and direction."""
        touch_events = [
            {"timestamp": 1.0, "x": 540, "y": 600, "gesture": "swipe", "start_x": 540, "start_y": 1200, "duration_ms": 300, "path_distance": 600},
        ]

        result = collapse_steps(touch_events, [])

        assert len(result) == 1
        assert result[0].action == "swipe"
        assert result[0].start == {"x": 540, "y": 1200}
        assert result[0].end == {"x": 540, "y": 600}
        assert result[0].direction == "up"

    def test_long_press_includes_duration(self):
        """Long press includes duration_ms."""
        touch_events = [
            {"timestamp": 1.0, "x": 400, "y": 800, "gesture": "long_press", "start_x": 400, "start_y": 800, "duration_ms": 650},
        ]

        result = collapse_steps(touch_events, [])

        assert len(result) == 1
        assert result[0].action == "long_press"
        assert result[0].duration_ms == 650
        assert result[0].coordinates == {"x": 400, "y": 800}

    def test_indices_renumbered_after_collapse(self):
        """Step indices are sequential after collapsing."""
        touch_events = [
            {"timestamp": 1.0, "x": 100, "y": 200, "gesture": "tap", "start_x": 100, "start_y": 200, "duration_ms": 50},
            {"timestamp": 2.0, "x": 500, "y": 1800, "gesture": "tap", "start_x": 500, "start_y": 1800, "duration_ms": 30},
            {"timestamp": 2.2, "x": 600, "y": 1850, "gesture": "tap", "start_x": 600, "start_y": 1850, "duration_ms": 25},
            {"timestamp": 2.4, "x": 550, "y": 1820, "gesture": "tap", "start_x": 550, "start_y": 1820, "duration_ms": 35},
            {"timestamp": 3.5, "x": 800, "y": 500, "gesture": "tap", "start_x": 800, "start_y": 500, "duration_ms": 40},
        ]
        typing_sequences = [
            TypingSequence(start_index=1, end_index=3, tap_count=3, duration=0.4, text=None)
        ]

        result = collapse_steps(touch_events, typing_sequences)

        assert [s.index for s in result] == [1, 2, 3]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_step_collapsing.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'mutcli.core.step_collapsing'"

**Step 3: Write the implementation**

```python
"""Step collapsing - merge typing sequences into single steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mutcli.core.typing_detector import TypingSequence


@dataclass
class CollapsedStep:
    """A step after collapsing typing sequences.

    Attributes:
        index: Step number (1-based, sequential after collapse)
        action: tap, type, swipe, or long_press
        timestamp: When the action started
        original_indices: Tuple of (start, end) indices in original touch_events
    """

    index: int
    action: str
    timestamp: float
    original_indices: tuple[int, int]

    # For tap and long_press
    coordinates: dict[str, int] | None = None

    # For swipe
    start: dict[str, int] | None = None
    end: dict[str, int] | None = None
    direction: str | None = None

    # For long_press
    duration_ms: int | None = None

    # For type
    tap_count: int | None = None
    text: str | None = None


def _calculate_direction(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Calculate swipe direction from start/end coordinates."""
    dx = end_x - start_x
    dy = end_y - start_y

    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    else:
        return "down" if dy > 0 else "up"


def collapse_steps(
    touch_events: list[dict[str, Any]],
    typing_sequences: list[TypingSequence],
) -> list[CollapsedStep]:
    """Collapse typing sequences into single 'type' steps.

    Args:
        touch_events: Raw touch events from device
        typing_sequences: Detected typing sequences

    Returns:
        List of CollapsedStep with typing merged
    """
    if not touch_events:
        return []

    # Build set of indices that are part of typing sequences
    typing_ranges: dict[int, TypingSequence] = {}
    for seq in typing_sequences:
        for i in range(seq.start_index, seq.end_index + 1):
            typing_ranges[i] = seq

    result: list[CollapsedStep] = []
    step_index = 1
    i = 0

    while i < len(touch_events):
        event = touch_events[i]

        if i in typing_ranges:
            # This is part of a typing sequence
            seq = typing_ranges[i]
            if i == seq.start_index:
                # First event of sequence - create type step
                result.append(CollapsedStep(
                    index=step_index,
                    action="type",
                    timestamp=event["timestamp"],
                    original_indices=(seq.start_index, seq.end_index),
                    tap_count=seq.tap_count,
                    text=seq.text,
                ))
                step_index += 1
            # Skip to end of sequence
            i = seq.end_index + 1
            continue

        gesture = event.get("gesture", "tap")

        if gesture == "swipe":
            start_x = event.get("start_x", event["x"])
            start_y = event.get("start_y", event["y"])
            end_x = event["x"]
            end_y = event["y"]
            direction = _calculate_direction(start_x, start_y, end_x, end_y)

            result.append(CollapsedStep(
                index=step_index,
                action="swipe",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                start={"x": start_x, "y": start_y},
                end={"x": end_x, "y": end_y},
                direction=direction,
            ))
        elif gesture == "long_press":
            result.append(CollapsedStep(
                index=step_index,
                action="long_press",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                coordinates={"x": event["x"], "y": event["y"]},
                duration_ms=event.get("duration_ms", 500),
            ))
        else:
            # tap
            result.append(CollapsedStep(
                index=step_index,
                action="tap",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                coordinates={"x": event["x"], "y": event["y"]},
            ))

        step_index += 1
        i += 1

    return result
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_step_collapsing.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add mutcli/core/step_collapsing.py tests/test_step_collapsing.py
git commit -m "feat: add step collapsing module for typing sequences"
```

---

## Task 2: Update Recorder - Flatten Output Paths

**Files:**
- Modify: `mutcli/core/recorder.py`
- Modify: `tests/test_recorder.py` (if exists, update paths)

**Context:** Change output from `tests/<name>/recording/` to `tests/<name>/`. Files: `video.mp4` (was `recording.mp4`), `touch_events.json`, `screenshots/`.

**Step 1: Read current recorder implementation**

Run: `cat mutcli/core/recorder.py | head -100`

Understand the current path structure before modifying.

**Step 2: Update paths in recorder**

Key changes:
- `output_dir / "recording"` → `output_dir`
- `"recording.mp4"` → `"video.mp4"`
- Remove creation of `recording/` subdirectory

**Step 3: Run existing tests**

Run: `pytest tests/test_recorder.py -v` (if exists)
Fix any path-related failures.

**Step 4: Commit**

```bash
git add mutcli/core/recorder.py
git commit -m "refactor: flatten recorder output paths"
```

---

## Task 3: Update Frame Extractor - Handle Collapsed Steps

**Files:**
- Modify: `mutcli/core/frame_extractor.py`
- Modify: `tests/test_frame_extractor.py`

**Context:** Frame extractor needs to:
1. Accept CollapsedStep instead of raw touch events
2. For "type" actions: extract only before (first tap) and after (last tap)
3. Update output paths (remove `recording/` prefix)

**Step 1: Write test for typing frame extraction**

```python
def test_extract_frames_for_type_action(self):
    """Type action extracts before from first tap, after from last tap."""
    # CollapsedStep with original_indices=(1, 3) means taps at indices 1,2,3
    # Should extract: step_N_before.png from tap 1, step_N_after.png from tap 3
    ...
```

**Step 2: Update FrameExtractor.extract_for_step() signature**

Change to accept `CollapsedStep` and handle different action types.

**Step 3: Run tests**

Run: `pytest tests/test_frame_extractor.py -v`

**Step 4: Commit**

```bash
git add mutcli/core/frame_extractor.py tests/test_frame_extractor.py
git commit -m "feat: update frame extractor for collapsed steps"
```

---

## Task 4: Add Analysis JSON Save/Load

**Files:**
- Create: `mutcli/core/analysis_io.py`
- Create: `tests/test_analysis_io.py`

**Context:** Save processed analysis to `analysis.json` and load it for recovery.

**Step 1: Write failing tests**

```python
"""Tests for analysis.json save/load."""

import json
import pytest
from pathlib import Path
from mutcli.core.analysis_io import save_analysis, load_analysis, AnalysisData


class TestAnalysisIO:
    """Tests for analysis save/load functions."""

    def test_save_creates_valid_json(self, tmp_path):
        """save_analysis creates valid JSON file."""
        data = AnalysisData(
            app_package="com.example.app",
            screen_width=1080,
            screen_height=2400,
            steps=[],
        )

        save_analysis(data, tmp_path)

        analysis_path = tmp_path / "analysis.json"
        assert analysis_path.exists()
        loaded = json.loads(analysis_path.read_text())
        assert loaded["app_package"] == "com.example.app"
        assert loaded["version"] == 1

    def test_load_returns_analysis_data(self, tmp_path):
        """load_analysis returns AnalysisData from file."""
        analysis_path = tmp_path / "analysis.json"
        analysis_path.write_text(json.dumps({
            "version": 1,
            "app_package": "com.example.app",
            "screen": {"width": 1080, "height": 2400},
            "steps": [],
        }))

        result = load_analysis(tmp_path)

        assert result is not None
        assert result.app_package == "com.example.app"

    def test_load_returns_none_if_missing(self, tmp_path):
        """load_analysis returns None if file doesn't exist."""
        result = load_analysis(tmp_path)
        assert result is None
```

**Step 2: Implement analysis_io.py**

```python
"""Save and load analysis.json for recording processing."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AnalysisStep:
    """A step in the analysis."""
    index: int
    action: str
    timestamp: float
    # ... all fields from design doc


@dataclass
class AnalysisData:
    """Complete analysis data for a recording."""
    app_package: str
    screen_width: int
    screen_height: int
    steps: list[dict[str, Any]]
    created_at: str | None = None
    version: int = 1


def save_analysis(data: AnalysisData, test_dir: Path) -> Path:
    """Save analysis data to JSON file."""
    if data.created_at is None:
        data.created_at = datetime.now(timezone.utc).isoformat()

    output = {
        "version": data.version,
        "created_at": data.created_at,
        "app_package": data.app_package,
        "screen": {
            "width": data.screen_width,
            "height": data.screen_height,
        },
        "steps": data.steps,
    }

    path = test_dir / "analysis.json"
    path.write_text(json.dumps(output, indent=2))
    return path


def load_analysis(test_dir: Path) -> AnalysisData | None:
    """Load analysis data from JSON file if exists."""
    path = test_dir / "analysis.json"
    if not path.exists():
        return None

    data = json.loads(path.read_text())
    return AnalysisData(
        app_package=data["app_package"],
        screen_width=data["screen"]["width"],
        screen_height=data["screen"]["height"],
        steps=data["steps"],
        created_at=data.get("created_at"),
        version=data.get("version", 1),
    )
```

**Step 3: Run tests**

Run: `pytest tests/test_analysis_io.py -v`

**Step 4: Commit**

```bash
git add mutcli/core/analysis_io.py tests/test_analysis_io.py
git commit -m "feat: add analysis.json save/load functions"
```

---

## Task 5: Update Step Analyzer - Skip Typing

**Files:**
- Modify: `mutcli/core/step_analyzer.py`
- Modify: `tests/test_step_analyzer.py`

**Context:** Step analyzer should:
1. Accept CollapsedStep instead of raw touch events
2. Skip AI analysis for "type" actions (use generic descriptions)
3. Return AnalyzedStep compatible with new structure

**Step 1: Write test for typing skip**

```python
def test_type_action_skips_ai_analysis(self):
    """Type actions get generic descriptions without AI call."""
    # Create collapsed step with action="type"
    # Verify AI not called, generic descriptions returned
    ...
```

**Step 2: Update analyze_all_parallel to handle CollapsedStep**

**Step 3: Run tests**

Run: `pytest tests/test_step_analyzer.py -v`

**Step 4: Commit**

```bash
git add mutcli/core/step_analyzer.py tests/test_step_analyzer.py
git commit -m "feat: step analyzer handles collapsed steps, skips typing"
```

---

## Task 6: Update CLI - New Processing Pipeline

**Files:**
- Modify: `mutcli/cli.py`

**Context:** Reorder processing pipeline:
1. Load touch_events.json
2. Detect typing sequences
3. Collapse steps
4. Extract frames for collapsed steps
5. AI analysis (skipping type actions)
6. Save analysis.json
7. Start preview server
8. If analysis.json exists on re-run, skip to preview server

**Step 1: Read current _process_recording function**

Understand current flow before modifying.

**Step 2: Implement new pipeline order**

Key changes:
- Add collapse_steps call after typing detection
- Pass CollapsedStep to frame extractor and analyzer
- Save analysis.json after AI analysis
- Check for existing analysis.json at start

**Step 3: Manual test**

Run: `mut record test_cli_change --app com.google.android.calculator`
Verify: analysis.json created, approval UI works

**Step 4: Commit**

```bash
git add mutcli/cli.py
git commit -m "feat: implement new processing pipeline with analysis.json"
```

---

## Task 7: Update Preview Server - Support Type Action

**Files:**
- Modify: `mutcli/core/preview_server.py`

**Context:**
1. Update file serving paths (remove `recording/` prefix)
2. PreviewStep already supports different actions
3. Ensure "type" action data is passed through

**Step 1: Update _serve_recording_file paths**

Change `/recording/` handling to serve from test_dir directly.

**Step 2: Update PreviewStep dataclass if needed**

Add `tap_count` and `text` fields for type action.

**Step 3: Manual test**

Verify preview server serves files from new locations.

**Step 4: Commit**

```bash
git add mutcli/core/preview_server.py
git commit -m "refactor: update preview server paths for flat structure"
```

---

## Task 8: Update Approval HTML - Text Input for Typing

**Files:**
- Modify: `mutcli/templates/approval.html`

**Context:** Add text input field for "type" actions in approval UI.

**Step 1: Identify where step cards are rendered**

Find the HTML/JS that renders step cards.

**Step 2: Add conditional text input**

```html
<!-- For type actions -->
<div v-if="step.action === 'type'" class="type-input">
  <label>Text typed ({{ step.tapCount }} taps):</label>
  <input type="text" v-model="step.text" placeholder="Enter typed text">
</div>
```

**Step 3: Ensure text is included in approval POST**

Verify the approve handler sends step.text back to server.

**Step 4: Manual test**

Record typing, verify text input appears in approval UI.

**Step 5: Commit**

```bash
git add mutcli/templates/approval.html
git commit -m "feat: add text input for type actions in approval UI"
```

---

## Task 9: Update YAML Generator - Handle Type Action

**Files:**
- Modify: `mutcli/core/yaml_generator.py`
- Modify: `tests/test_yaml_generator.py`

**Context:** Generate `type: "text"` for type actions.

**Step 1: Write failing test**

```python
def test_generates_type_action(self):
    """Type action generates type: text step."""
    generator = YAMLGenerator(name="test", app_package="com.example")
    generator.add_type("hello world")

    yaml_content = generator.generate()

    assert "- type: \"hello world\"" in yaml_content
```

**Step 2: Implement add_type method**

```python
def add_type(self, text: str) -> None:
    """Add a type text step."""
    self._steps.append(f'- type: "{text}"')
```

**Step 3: Update CLI to use add_type for type actions**

**Step 4: Run tests**

Run: `pytest tests/test_yaml_generator.py -v`

**Step 5: Commit**

```bash
git add mutcli/core/yaml_generator.py tests/test_yaml_generator.py mutcli/cli.py
git commit -m "feat: YAML generator supports type action"
```

---

## Task 10: End-to-End Test

**Files:** None (manual testing)

**Context:** Verify complete flow works.

**Step 1: Clean test directory**

```bash
rm -rf tests/e2e_test
```

**Step 2: Record with typing**

```bash
mut record e2e_test --app com.google.android.calculator
# Tap some buttons, then type something
```

**Step 3: Verify analysis.json created**

```bash
cat tests/e2e_test/analysis.json | jq .
```

**Step 4: Verify approval UI shows typing**

Check that type action has text input field.

**Step 5: Generate YAML and verify**

```bash
cat tests/e2e_test/test.yaml
```

Should show `type: "text"` for typing steps.

**Step 6: Run all tests**

```bash
pytest
ruff check .
mypy mutcli/
```

**Step 7: Final commit**

```bash
git add -A
git commit -m "test: verify end-to-end recording flow"
```

---

## Summary

| Task | Description | New Files |
|------|-------------|-----------|
| 1 | Step collapsing module | `step_collapsing.py` |
| 2 | Flatten recorder paths | - |
| 3 | Frame extractor for collapsed steps | - |
| 4 | Analysis JSON save/load | `analysis_io.py` |
| 5 | Step analyzer skips typing | - |
| 6 | CLI new pipeline | - |
| 7 | Preview server paths | - |
| 8 | Approval HTML text input | - |
| 9 | YAML generator type action | - |
| 10 | End-to-end test | - |
