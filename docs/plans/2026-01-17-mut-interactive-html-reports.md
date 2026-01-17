# Interactive HTML Reports Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Generate interactive HTML reports for test execution results, matching the approval flow design language with video scrubbing, step navigation, and before/after frame comparison.

**Architecture:** ReportGenerator creates HTML from TestResult with embedded screenshots and video. Design matches approval.html (dark theme, step cards, frame comparison).

**Tech Stack:** Python (Jinja2 templating or string formatting), existing TestResult/StepResult dataclasses, base64-encoded screenshots.

---

## Design Requirements

**Match approval.html design:**
- Dark theme: `--bg-primary: #111827`, `--bg-secondary: #1f2937`, `--bg-tertiary: #374151`
- Status colors: `--pass-color: #10b981`, `--fail-color: #ef4444`, `--skip-color: #6b7280`
- Action colors: `--action-tap: #f59e0b`, `--action-verify: #8b5cf6`, `--action-type: #06b6d4`
- Step cards with number badges, action badges, status indicators
- Before → Action → After frame layout (same as approval flow)
- Video scrubber with step markers (if video exists)
- Rounded corners (8px), consistent padding (16px, 20px)

**Report Features:**
- Test summary header (name, status, duration, step count)
- Step-by-step breakdown with:
  - Step number badge (colored by status: green=pass, red=fail)
  - Action type badge (tap, verify, type, wait, swipe)
  - Before/After screenshots (if available)
  - Error message (for failed steps)
  - Duration per step
- Video player with step markers (click to jump)
- Collapsible step details
- JSON export button

---

## Task 1: Create Report HTML Template

**Files:**
- Create: `/Users/vladislavkarpman/Projects/mut/mutcli/templates/report.html`

**Template structure:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Report - {test_name}</title>
    <style>
        /* Same CSS variables as approval.html */
        :root {
            --pass-color: #10b981;
            --fail-color: #ef4444;
            --skip-color: #6b7280;
            --bg-primary: #111827;
            --bg-secondary: #1f2937;
            --bg-tertiary: #374151;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
            --border-color: #4b5563;
            --accent-color: #3b82f6;
            --action-tap: #f59e0b;
            --action-verify: #8b5cf6;
            --action-type: #06b6d4;
            --action-wait: #6b7280;
        }
        /* Component styles matching approval flow */
    </style>
</head>
<body>
    <header class="header">
        <div class="header-left">
            <span class="status-badge {status}">{STATUS}</span>
        </div>
        <div class="header-center">
            <h1>{test_name}</h1>
        </div>
        <div class="header-right">
            <span class="duration">{duration}s</span>
            <button class="btn btn-secondary" onclick="exportJSON()">Export JSON</button>
        </div>
    </header>

    <main class="main">
        <!-- Video panel (if video exists) -->
        <div class="video-panel">
            <video controls>...</video>
            <div class="step-markers">...</div>
        </div>

        <!-- Steps panel -->
        <div class="steps-panel">
            <!-- Step cards -->
        </div>
    </main>

    <script>
        const reportData = {json_data};
        // Video scrubbing, step navigation, JSON export
    </script>
</body>
</html>
```

**Commit:** `feat(report): create HTML report template matching approval design`

---

## Task 2: Update ReportGenerator for New Template

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/report.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/tests/test_report.py`

**Changes:**

1. Load template from `mutcli/templates/report.html`
2. Embed screenshots as base64 data URIs
3. Embed video path (relative) for playback
4. Generate step markers for video timeline

```python
def generate_html(self, result: TestResult) -> Path:
    """Generate interactive HTML report.

    Args:
        result: Test execution result

    Returns:
        Path to generated HTML file
    """
    # Load template
    template = self._load_template()

    # Prepare step data with embedded screenshots
    steps_data = []
    for step in result.steps:
        step_data = {
            "number": step.step_number,
            "action": step.action,
            "status": step.status,
            "duration": step.duration,
            "error": step.error,
            "before_screenshot": self._encode_screenshot(step.screenshot_before),
            "after_screenshot": self._encode_screenshot(step.screenshot_after),
        }
        steps_data.append(step_data)

    # Render template
    html = template.format(
        test_name=result.name,
        status=result.status,
        duration=f"{result.duration:.1f}",
        steps=steps_data,
        json_data=json.dumps(self._to_dict(result)),
    )

    # Write HTML file
    html_path = self._output_dir / "report.html"
    html_path.write_text(html)
    return html_path

def _encode_screenshot(self, data: bytes | None) -> str | None:
    """Encode screenshot as base64 data URI."""
    if data is None:
        return None
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"
```

**Tests:**
1. `test_generate_html_creates_file`
2. `test_html_contains_test_name`
3. `test_html_contains_status_badge`
4. `test_html_embeds_screenshots_as_base64`
5. `test_html_includes_step_cards`
6. `test_html_shows_error_for_failed_steps`

**Commit:** `feat(report): update ReportGenerator to use new HTML template`

---

## Task 3: Add Video Integration

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/report.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/templates/report.html`

**Features:**
1. Check if video exists in output directory
2. Include video player in report if video present
3. Generate step markers on video timeline
4. Click marker to jump to step timestamp

**Video timeline markers:**
```javascript
function createStepMarkers(steps, videoDuration) {
    const timeline = document.querySelector('.video-timeline');
    steps.forEach((step, i) => {
        const marker = document.createElement('div');
        marker.className = `step-marker ${step.status}`;
        marker.style.left = `${(step.timestamp / videoDuration) * 100}%`;
        marker.onclick = () => video.currentTime = step.timestamp;
        timeline.appendChild(marker);
    });
}
```

**Tests:**
1. `test_html_includes_video_player_when_video_exists`
2. `test_html_no_video_panel_when_video_missing`
3. `test_step_markers_generated_for_video`

**Commit:** `feat(report): add video player with step markers`

---

## Task 4: Add Step Navigation and Interactivity

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/templates/report.html`

**Features:**
1. Click step card to highlight and scroll video to timestamp
2. Collapsible step details (expand to see full error/screenshots)
3. Filter steps by status (All / Passed / Failed)
4. Keyboard navigation (arrow keys for steps)

**JavaScript additions:**
```javascript
// Step navigation
document.querySelectorAll('.step-card').forEach((card, i) => {
    card.onclick = () => {
        // Highlight card
        document.querySelectorAll('.step-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');

        // Scroll video to step timestamp
        if (video && steps[i].timestamp) {
            video.currentTime = steps[i].timestamp;
        }
    };
});

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') selectNextStep();
    if (e.key === 'ArrowUp') selectPrevStep();
});

// Filter by status
function filterSteps(status) {
    document.querySelectorAll('.step-card').forEach(card => {
        const stepStatus = card.dataset.status;
        card.style.display = (status === 'all' || stepStatus === status) ? 'block' : 'none';
    });
}
```

**Commit:** `feat(report): add step navigation and filtering`

---

## Task 5: Wire Up Report Generation in Executor

**Files:**
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/core/executor.py`
- Modify: `/Users/vladislavkarpman/Projects/mut/mutcli/cli.py`

**Changes:**

1. Capture screenshots before/after each step during execution
2. Record step timestamps for video synchronization
3. Pass video path to ReportGenerator

**Executor changes:**
```python
def execute_step(self, step: Step) -> StepResult:
    self._step_number += 1
    start = time.time()

    # Capture before screenshot
    screenshot_before = self._capture_screenshot()

    try:
        handler = getattr(self, f"_action_{step.action}", None)
        if handler is None:
            return StepResult(...)

        error = handler(step)

        # Capture after screenshot
        screenshot_after = self._capture_screenshot()

        return StepResult(
            step_number=self._step_number,
            action=step.action,
            status="failed" if error else "passed",
            duration=time.time() - start,
            error=error,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            details={"timestamp": time.time() - self._test_start},
        )
    except Exception as e:
        ...

def _capture_screenshot(self) -> bytes | None:
    """Capture screenshot if available."""
    try:
        return self._device.take_screenshot()
    except Exception:
        return None
```

**Tests:**
1. `test_executor_captures_before_screenshot`
2. `test_executor_captures_after_screenshot`
3. `test_step_result_includes_screenshots`
4. `test_step_result_includes_timestamp`

**Commit:** `feat(executor): capture screenshots for report generation`

---

## Task 6: Run All Tests and Manual Verification

**Run full test suite:**

```bash
cd /Users/vladislavkarpman/Projects/mut
source .venv/bin/activate
pytest -v
```

**Manual testing:**

1. Create a simple test file
2. Run test with `mut run tests/example/test.yaml`
3. Open generated report in browser
4. Verify:
   - Dark theme matches approval flow
   - Status badge shows correct color
   - Step cards display with correct badges
   - Before/After screenshots shown
   - Video player works (if video exists)
   - Step navigation works (click card → video jumps)
   - JSON export button works

**Commit:** `feat: complete interactive HTML reports implementation`

---

## Summary

After completing this plan:
- HTML reports match approval flow design (dark theme, step cards, badges)
- Reports include before/after screenshots for each step
- Video player with step markers for timeline navigation
- Interactive step filtering (All/Passed/Failed)
- JSON export functionality
- Keyboard navigation support
