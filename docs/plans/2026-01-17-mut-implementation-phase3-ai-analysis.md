# AI-Powered Step Analysis Implementation Plan (Phase 3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement AI-powered analysis of recorded interactions to generate cleaner, smarter YAML tests with element names, typing detection, and verification suggestions.

**Architecture:** TypingDetector identifies keyboard input patterns. StepAnalyzer uses AIAnalyzer (Gemini) to extract element text and suggest verifications. Results feed into enhanced YAMLGenerator.

**Tech Stack:** AIAnalyzer (Gemini 2.5 Flash), PIL (image analysis), existing TouchMonitor/FrameExtractor

---

## Overview

Phase 3 transforms raw touch coordinates into semantic actions:

**Before (Phase 2):**
```yaml
steps:
  - tap: [540, 800]
  - tap: [520, 1400]
  - tap: [530, 1450]
  - tap: [540, 1400]
  - tap: [100, 1600]
  - tap: [540, 900]
```

**After (Phase 3):**
```yaml
steps:
  - tap: "Email"
  - type: "user@test.com"
  - tap: "Password"
  - type: "secret123"
  - tap: "Sign In"
  - verify_screen: "Dashboard with welcome message"
```

---

## Task 1: Implement TypingDetector

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/typing_detector.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_typing_detector.py`

**Purpose:** Detect keyboard typing sequences from touch events based on:
- Location: Bottom 40% of screen (keyboard area)
- Timing: < 1 second between taps
- Consecutive: 3+ taps in sequence

### TypingDetector specification

```python
@dataclass
class TypingSequence:
    start_index: int      # Index of first tap in sequence
    end_index: int        # Index of last tap in sequence
    tap_count: int        # Number of taps
    duration: float       # Total duration in seconds
    text: str | None = None  # User-provided text (filled later)

class TypingDetector:
    KEYBOARD_THRESHOLD = 0.4  # Bottom 40% of screen
    MAX_TAP_INTERVAL = 1.0    # Max seconds between keyboard taps
    MIN_SEQUENCE_LENGTH = 3   # Minimum taps to consider typing

    def __init__(self, screen_height: int):
        """Initialize with screen height for keyboard detection."""

    def detect(self, touch_events: list[dict]) -> list[TypingSequence]:
        """Detect typing sequences in touch events.

        Args:
            touch_events: List of dicts with 'x', 'y', 'timestamp'

        Returns:
            List of detected TypingSequence objects
        """

    def is_keyboard_tap(self, y: int) -> bool:
        """Check if Y coordinate is in keyboard area."""
```

### Detection algorithm

```python
def detect(self, touch_events):
    sequences = []
    current_sequence_start = None
    last_timestamp = None

    for i, event in enumerate(touch_events):
        is_keyboard = self.is_keyboard_tap(event["y"])

        if is_keyboard:
            if current_sequence_start is None:
                current_sequence_start = i
            elif event["timestamp"] - last_timestamp > self.MAX_TAP_INTERVAL:
                # Gap too large, end previous sequence
                if i - current_sequence_start >= self.MIN_SEQUENCE_LENGTH:
                    sequences.append(TypingSequence(
                        start_index=current_sequence_start,
                        end_index=i - 1,
                        tap_count=i - current_sequence_start,
                        duration=last_timestamp - touch_events[current_sequence_start]["timestamp"],
                    ))
                current_sequence_start = i
            last_timestamp = event["timestamp"]
        else:
            # Non-keyboard tap, end sequence if exists
            if current_sequence_start is not None:
                if i - current_sequence_start >= self.MIN_SEQUENCE_LENGTH:
                    sequences.append(...)
                current_sequence_start = None

    return sequences
```

### Tests to write

1. Detects typing in bottom 40% of screen
2. Requires 3+ consecutive taps
3. Splits sequences on > 1s gap
4. Ignores non-keyboard taps
5. Returns empty list for no typing
6. Handles edge cases (empty events, single tap)

### Commit message

```
feat(analysis): implement TypingDetector for keyboard input detection
```

---

## Task 2: Implement StepAnalyzer

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/step_analyzer.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_step_analyzer.py`

**Purpose:** Use AIAnalyzer to extract element text and suggest verifications from screenshots.

### StepAnalyzer specification

```python
@dataclass
class AnalyzedStep:
    index: int
    original_tap: dict           # Original touch event
    element_text: str | None     # AI-extracted element text
    before_description: str      # What screen showed before tap
    after_description: str       # What changed after tap
    suggested_verification: str | None  # Optional verification

class StepAnalyzer:
    def __init__(self, ai_analyzer: AIAnalyzer):
        """Initialize with AIAnalyzer instance."""

    def analyze_step(
        self,
        before_screenshot: bytes,
        after_screenshot: bytes,
        tap_coordinates: tuple[int, int],
    ) -> AnalyzedStep:
        """Analyze a single step using AI.

        Args:
            before_screenshot: PNG bytes before tap
            after_screenshot: PNG bytes after tap
            tap_coordinates: (x, y) of tap

        Returns:
            AnalyzedStep with extracted information
        """

    def analyze_all(
        self,
        touch_events: list[dict],
        screenshots_dir: Path,
    ) -> list[AnalyzedStep]:
        """Analyze all steps from recording.

        Args:
            touch_events: List of touch event dicts
            screenshots_dir: Directory with touch_001.png, etc.

        Returns:
            List of AnalyzedStep objects
        """
```

### AI prompt for element extraction

```python
ELEMENT_EXTRACTION_PROMPT = '''Analyze this mobile app screenshot.

A tap occurred at coordinates ({x}, {y}).

1. What UI element was tapped? Look for buttons, text fields, links near those coordinates.
2. What is the text label of that element?

Respond with JSON only:
{{"element_text": "button/field text or null if unclear", "element_type": "button|text_field|link|icon|other"}}'''
```

### Tests to write (mock AIAnalyzer)

1. Extracts element text from screenshot
2. Returns None element_text when AI unavailable
3. analyze_all processes all screenshots
4. Handles missing screenshot files gracefully

### Commit message

```
feat(analysis): implement StepAnalyzer for AI-powered element extraction
```

---

## Task 3: Implement VerificationSuggester

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/core/verification_suggester.py`
- Create: `/Users/vladislavkarpman/Projects/mut/tests/test_verification_suggester.py`

**Purpose:** Suggest verification points based on UI changes.

### VerificationSuggester specification

```python
@dataclass
class VerificationPoint:
    after_step_index: int        # Insert verification after this step
    description: str             # Suggested verify_screen description
    confidence: float            # 0.0-1.0 confidence score
    reason: str                  # Why this verification was suggested

class VerificationSuggester:
    def __init__(self, ai_analyzer: AIAnalyzer):
        """Initialize with AIAnalyzer."""

    def suggest(
        self,
        analyzed_steps: list[AnalyzedStep],
    ) -> list[VerificationPoint]:
        """Suggest verification points based on analyzed steps.

        Suggests verifications when:
        - Significant UI change detected (navigation, form submission)
        - Long pause before next action (user was verifying visually)
        - Flow completion (login, checkout, etc.)

        Returns:
            List of VerificationPoint suggestions
        """
```

### Verification criteria

1. **Navigation change**: Screen title/header changed
2. **Form submission**: After tapping "Submit", "Login", "Sign In", etc.
3. **Long pause**: > 2 seconds before next tap
4. **Flow keywords**: "success", "complete", "welcome", "dashboard"

### Tests to write

1. Suggests verification after form submission
2. Suggests verification on navigation change
3. Suggests verification after long pause
4. Returns empty list when no verifications needed
5. Limits suggestions (max 3-5 per recording)

### Commit message

```
feat(analysis): implement VerificationSuggester for smart verification points
```

---

## Task 4: Create EnhancedYAMLGenerator

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/yaml_generator.py`

**Purpose:** Extend YAMLGenerator to accept analyzed steps and typing sequences.

### New methods

```python
class YAMLGenerator:
    # ... existing methods ...

    def add_analyzed_step(self, step: AnalyzedStep) -> None:
        """Add step using AI-extracted element text.

        Uses element_text if available, falls back to coordinates.
        """
        if step.element_text:
            self.add_tap(0, 0, element=step.element_text)
        else:
            self.add_tap(step.original_tap["x"], step.original_tap["y"])

    def add_typing_sequence(self, sequence: TypingSequence) -> None:
        """Add type command for detected typing sequence."""
        if sequence.text:
            self.add_type(sequence.text)
        # If no text provided, skip (user didn't fill it in)

    def generate_from_analysis(
        self,
        analyzed_steps: list[AnalyzedStep],
        typing_sequences: list[TypingSequence],
        verifications: list[VerificationPoint],
    ) -> str:
        """Generate YAML from full analysis results.

        Merges steps, typing, and verifications in correct order.
        """
```

### Tests to write

1. Uses element_text when available
2. Falls back to coordinates when no element_text
3. Inserts type commands at correct positions
4. Inserts verify_screen at suggested points
5. Handles overlapping typing sequences and verifications

### Commit message

```
feat(yaml): extend YAMLGenerator with analysis integration
```

---

## Task 5: Integrate into stop Command

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/cli.py`

**Purpose:** Wire up AI analysis in the stop command.

### Updated stop command flow

```python
@app.command()
def stop(test_dir: Path | None = None) -> None:
    """Process recording and generate YAML test."""

    # ... existing directory finding ...

    # Load touch events
    with open(touch_file) as f:
        touch_events = json.load(f)

    # Get screen dimensions
    screen_height = touch_events[0].get("screen_height", 2400)

    # 1. Detect typing sequences
    console.print("  [dim]Detecting typing patterns...[/dim]")
    typing_detector = TypingDetector(screen_height)
    typing_sequences = typing_detector.detect(touch_events)

    if typing_sequences:
        console.print(f"    Found {len(typing_sequences)} typing sequence(s)")
        # Ask user for typed text
        for seq in typing_sequences:
            text = typer.prompt(
                f"    What text was typed at step {seq.start_index + 1}?",
                default="",
            )
            seq.text = text if text else None

    # 2. Extract frames (if video exists)
    if video_path.exists():
        console.print("  [dim]Extracting frames...[/dim]")
        extractor = FrameExtractor(video_path)
        extractor.extract_for_touches(touch_events, screenshots_dir)

    # 3. Analyze steps with AI (if API key available)
    analyzed_steps = []
    verifications = []

    try:
        config = ConfigLoader.load(require_api_key=False)
        if config.google_api_key:
            console.print("  [dim]Analyzing with AI...[/dim]")
            ai = AIAnalyzer(api_key=config.google_api_key)
            step_analyzer = StepAnalyzer(ai)
            analyzed_steps = step_analyzer.analyze_all(touch_events, screenshots_dir)

            suggester = VerificationSuggester(ai)
            verifications = suggester.suggest(analyzed_steps)

            console.print(f"    Extracted {sum(1 for s in analyzed_steps if s.element_text)} element names")
            console.print(f"    Suggested {len(verifications)} verifications")
    except Exception as e:
        console.print(f"  [yellow]AI analysis skipped: {e}[/yellow]")

    # 4. Generate YAML
    generator = YAMLGenerator(name=test_name, app_package=app_package)
    generator.add_launch_app()

    if analyzed_steps:
        generator.generate_from_analysis(analyzed_steps, typing_sequences, verifications)
    else:
        # Fallback to coordinates
        for event in touch_events:
            generator.add_tap(event["x"], event["y"])

    generator.add_terminate_app()
    generator.save(yaml_path)

    # ... show results ...
```

### User prompts for typing

When typing sequences are detected, prompt user:
```
Processing recording...
  Found 12 touch events
  Detecting typing patterns...
    Found 2 typing sequence(s)
    What text was typed at step 3? user@example.com
    What text was typed at step 7? secret123
  Extracting frames...
  Analyzing with AI...
    Extracted 8 element names
    Suggested 2 verifications

Test generated!
  Output: tests/login-test/test.yaml
```

### Commit message

```
feat(cli): integrate AI analysis into stop command
```

---

## Task 6: Run All Tests and Verify

**Step 1: Run all tests**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest -v
```

Expected: All tests pass

**Step 2: Manual testing with device**

```bash
# Start recording
mut record ai-test

# Interact: tap some buttons, type in a text field, navigate

# Stop and process
mut stop

# Check generated YAML
cat tests/ai-test/test.yaml
```

**Step 3: Commit and push**

```bash
git add -A
git commit -m "feat: complete Phase 3 AI-powered step analysis"
git push origin main
```

---

## Summary

After completing Phase 3:
- Typing sequences detected and converted to `type` commands
- AI extracts element text from screenshots
- Smart verifications suggested at key points
- Generated YAML uses semantic element names instead of coordinates
- Graceful fallback when AI unavailable

**Generated YAML quality improvement:**
- Raw coordinates → Element text labels
- Keyboard tap sequences → `type` commands
- Manual verification → AI-suggested `verify_screen`
