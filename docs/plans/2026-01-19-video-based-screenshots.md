# Video-Based Screenshots Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract report screenshots from video files instead of embedding runtime screenshots as base64.

**Architecture:** Runtime screenshots stay in memory for AI features. After test ends, frames are extracted from video at stored timestamps, saved as PNG files, and referenced by HTML reports via relative paths. No video = no HTML report.

**Tech Stack:** Python, pytest, Pillow (already a dependency via frame_extractor)

---

## Task 1: Add Screenshot Path Fields to StepResult

**Files:**
- Modify: `mutcli/core/executor.py:24-55`
- Test: `tests/test_executor.py`

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
def test_step_result_has_screenshot_path_fields():
    """StepResult has path fields for report screenshots."""
    from pathlib import Path
    result = StepResult(
        step_number=1,
        action="tap",
        status="passed",
    )
    # Path fields should exist and default to None
    assert result.screenshot_before_path is None
    assert result.screenshot_after_path is None
    assert result.screenshot_action_path is None
    assert result.screenshot_action_end_path is None

    # Should accept Path values
    result.screenshot_before_path = Path("screenshots/001_tap_before.png")
    assert result.screenshot_before_path == Path("screenshots/001_tap_before.png")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py::test_step_result_has_screenshot_path_fields -v`
Expected: FAIL with "AttributeError: 'StepResult' object has no attribute 'screenshot_before_path'"

**Step 3: Write minimal implementation**

In `mutcli/core/executor.py`, add fields to `StepResult` dataclass after the existing screenshot bytes fields (around line 42):

```python
    # Screenshot file paths (for report - populated after video extraction)
    screenshot_before_path: Path | None = None
    screenshot_after_path: Path | None = None
    screenshot_action_path: Path | None = None
    screenshot_action_end_path: Path | None = None
```

Also add `Path` to the imports at top if not already present.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_executor.py::test_step_result_has_screenshot_path_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/executor.py tests/test_executor.py
git commit -m "feat(executor): add screenshot path fields to StepResult"
```

---

## Task 2: Create Screenshot Saver Utility

**Files:**
- Create: `mutcli/core/screenshot_saver.py`
- Test: `tests/test_screenshot_saver.py`

**Step 1: Write the failing test**

Create `tests/test_screenshot_saver.py`:

```python
"""Tests for screenshot saver utility."""
from pathlib import Path

import pytest


class TestScreenshotSaver:
    def test_generates_correct_filename(self):
        """Generates filename with step number, action, and frame type."""
        from mutcli.core.screenshot_saver import ScreenshotSaver

        saver = ScreenshotSaver(Path("/tmp/screenshots"))
        filename = saver.get_filename(step_number=1, action="tap", frame_type="before")
        assert filename == "001_tap_before.png"

    def test_generates_filename_for_swipe(self):
        """Handles multi-word actions correctly."""
        from mutcli.core.screenshot_saver import ScreenshotSaver

        saver = ScreenshotSaver(Path("/tmp/screenshots"))
        filename = saver.get_filename(step_number=5, action="long_press", frame_type="action_end")
        assert filename == "005_long_press_action_end.png"

    def test_saves_screenshot_to_file(self, tmp_path):
        """Saves bytes to PNG file and returns path."""
        from mutcli.core.screenshot_saver import ScreenshotSaver

        screenshots_dir = tmp_path / "screenshots"
        saver = ScreenshotSaver(screenshots_dir)

        # Minimal valid PNG
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
            b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
            b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        path = saver.save(png_bytes, step_number=1, action="tap", frame_type="before")

        assert path.exists()
        assert path.name == "001_tap_before.png"
        assert path.read_bytes() == png_bytes
        assert path.parent == screenshots_dir

    def test_creates_directory_if_not_exists(self, tmp_path):
        """Creates screenshots directory if it doesn't exist."""
        from mutcli.core.screenshot_saver import ScreenshotSaver

        screenshots_dir = tmp_path / "nested" / "screenshots"
        saver = ScreenshotSaver(screenshots_dir)

        png_bytes = b'\x89PNG...'  # Minimal bytes for test
        path = saver.save(png_bytes, step_number=1, action="tap", frame_type="before")

        assert screenshots_dir.exists()
        assert path.exists()

    def test_returns_none_for_none_bytes(self, tmp_path):
        """Returns None when given None bytes."""
        from mutcli.core.screenshot_saver import ScreenshotSaver

        saver = ScreenshotSaver(tmp_path / "screenshots")
        path = saver.save(None, step_number=1, action="tap", frame_type="before")

        assert path is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_screenshot_saver.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'mutcli.core.screenshot_saver'"

**Step 3: Write minimal implementation**

Create `mutcli/core/screenshot_saver.py`:

```python
"""Screenshot file saver for test reports."""

from pathlib import Path


class ScreenshotSaver:
    """Save screenshots to files with structured naming."""

    def __init__(self, output_dir: Path):
        """Initialize saver.

        Args:
            output_dir: Directory to save screenshots to
        """
        self._output_dir = Path(output_dir)

    def get_filename(self, step_number: int, action: str, frame_type: str) -> str:
        """Generate filename for screenshot.

        Args:
            step_number: Step number (1-indexed)
            action: Action type (tap, swipe, etc.)
            frame_type: Frame type (before, after, action, action_end)

        Returns:
            Filename like "001_tap_before.png"
        """
        return f"{step_number:03d}_{action}_{frame_type}.png"

    def save(
        self,
        data: bytes | None,
        step_number: int,
        action: str,
        frame_type: str,
    ) -> Path | None:
        """Save screenshot bytes to file.

        Args:
            data: PNG bytes or None
            step_number: Step number
            action: Action type
            frame_type: Frame type

        Returns:
            Path to saved file, or None if data is None
        """
        if data is None:
            return None

        self._output_dir.mkdir(parents=True, exist_ok=True)

        filename = self.get_filename(step_number, action, frame_type)
        path = self._output_dir / filename
        path.write_bytes(data)

        return path
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_screenshot_saver.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/screenshot_saver.py tests/test_screenshot_saver.py
git commit -m "feat(core): add ScreenshotSaver utility for file-based screenshots"
```

---

## Task 3: Modify Frame Extraction to Save Files

**Files:**
- Modify: `mutcli/core/executor.py:523-621` (`_extract_frames_from_video` method)
- Test: `tests/test_executor.py`

**Step 1: Write the failing test**

Add to `tests/test_executor.py`:

```python
def test_extract_frames_saves_to_files(tmp_path, mocker):
    """Frame extraction saves PNGs to screenshots folder."""
    from mutcli.core.executor import StepResult, TestExecutor
    from mutcli.core.config import MutConfig

    # Create minimal video file
    video_path = tmp_path / "recording" / "video.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"fake video")

    # Mock FrameExtractor to return fake PNG bytes
    mock_extractor = mocker.MagicMock()
    mock_extractor.extract_frame.return_value = b'\x89PNG...'
    mocker.patch(
        "mutcli.core.executor.FrameExtractor",
        return_value=mock_extractor,
    )

    # Create executor with output_dir
    executor = TestExecutor.__new__(TestExecutor)
    executor._output_dir = tmp_path
    executor._recording_video_path = video_path
    executor._config = MutConfig()

    # Create step result with timestamps
    results = [
        StepResult(
            step_number=1,
            action="tap",
            status="passed",
            _ts_before=0.5,
            _ts_after=1.0,
            _ts_action=0.7,
        )
    ]

    # Run extraction
    executor._extract_frames_from_video(results)

    # Verify files were saved
    screenshots_dir = tmp_path / "screenshots"
    assert screenshots_dir.exists()
    assert (screenshots_dir / "001_tap_before.png").exists()
    assert (screenshots_dir / "001_tap_action.png").exists()
    assert (screenshots_dir / "001_tap_after.png").exists()

    # Verify path fields were populated
    assert results[0].screenshot_before_path == screenshots_dir / "001_tap_before.png"
    assert results[0].screenshot_action_path == screenshots_dir / "001_tap_action.png"
    assert results[0].screenshot_after_path == screenshots_dir / "001_tap_after.png"
    assert results[0].screenshot_action_end_path is None  # No timestamp for this
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_executor.py::test_extract_frames_saves_to_files -v`
Expected: FAIL (path fields not populated, files not saved)

**Step 3: Write minimal implementation**

Modify `_extract_frames_from_video` in `mutcli/core/executor.py`. Add import at top:

```python
from mutcli.core.screenshot_saver import ScreenshotSaver
```

Replace the `_extract_frames_from_video` method:

```python
    def _extract_frames_from_video(self, results: list[StepResult]) -> None:
        """Extract precise frames from video and save as files.

        Uses FrameExtractor to extract frames at the timestamps stored during
        execution. Saves frames as PNG files to screenshots/ folder.

        Args:
            results: List of StepResult objects with _ts_* timestamps populated
        """
        if not self._recording_video_path or not self._recording_video_path.exists():
            logger.warning("No video file available for frame extraction")
            return

        # Create screenshot saver
        screenshots_dir = self._output_dir / "screenshots"
        saver = ScreenshotSaver(screenshots_dir)

        # Build extraction list with timing offsets
        # Format: (step, ts_field, adjusted_timestamp)
        extractions: list[tuple[StepResult, str, float]] = []
        for step in results:
            for ts_field in ["_ts_before", "_ts_after", "_ts_action", "_ts_action_end"]:
                ts = getattr(step, ts_field, None)
                if ts is not None:
                    # Apply timing offsets based on frame type
                    if ts_field == "_ts_after":
                        ts = ts + self.FRAME_OFFSET_AFTER
                    elif ts_field in ("_ts_action", "_ts_action_end"):
                        ts = ts + self.FRAME_OFFSET_ACTION
                    extractions.append((step, ts_field, ts))

        if not extractions:
            logger.debug("No timestamps to extract from video")
            return

        logger.info(
            "Extracting %d frames from video at %s (parallel)",
            len(extractions),
            self._recording_video_path,
        )

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            from mutcli.core.frame_extractor import FrameExtractor

            extractor = FrameExtractor(self._recording_video_path)

            # Parallel extraction using ThreadPoolExecutor
            max_workers = min(16, len(extractions))
            extracted_count = 0

            def extract_single(
                item: tuple[StepResult, str, float],
            ) -> tuple[StepResult, str, bytes | None]:
                """Extract a single frame and return with metadata."""
                step, ts_field, timestamp = item
                frame_bytes = extractor.extract_frame(timestamp)
                return step, ts_field, frame_bytes

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(extract_single, item): item for item in extractions
                }

                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        step, ts_field, frame_bytes = future.result()
                        if frame_bytes:
                            # Map timestamp field to frame type
                            frame_type = ts_field.replace("_ts_", "")

                            # Save to file
                            path = saver.save(
                                frame_bytes,
                                step_number=step.step_number,
                                action=step.action,
                                frame_type=frame_type,
                            )

                            # Populate path field
                            path_field = f"screenshot_{frame_type}_path"
                            setattr(step, path_field, path)

                            extracted_count += 1
                        else:
                            logger.warning(
                                "Failed to extract frame at %.3fs for step %d (%s)",
                                item[2],
                                item[0].step_number,
                                ts_field,
                            )
                    except Exception as e:
                        logger.warning(
                            "Exception extracting frame for step %d: %s",
                            item[0].step_number,
                            e,
                        )

            logger.info(
                "Extracted %d/%d frames from video",
                extracted_count,
                len(extractions),
            )

        except Exception as e:
            logger.exception("Failed to extract frames from video: %s", e)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_executor.py::test_extract_frames_saves_to_files -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/executor.py tests/test_executor.py
git commit -m "feat(executor): save extracted frames as files instead of bytes"
```

---

## Task 4: Update ReportGenerator to Use File Paths

**Files:**
- Modify: `mutcli/core/report.py`
- Test: `tests/test_report.py`

**Step 1: Write the failing test**

Add to `tests/test_report.py`:

```python
def test_html_references_screenshot_files(tmp_path):
    """HTML report references screenshot files instead of base64."""
    from pathlib import Path
    from mutcli.core.executor import StepResult, TestResult
    from mutcli.core.report import ReportGenerator

    # Create video and screenshots
    output_dir = tmp_path / "report"
    output_dir.mkdir()
    (output_dir / "recording").mkdir()
    (output_dir / "recording" / "video.mp4").write_bytes(b"fake video")

    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir()
    (screenshots_dir / "001_tap_before.png").write_bytes(b'\x89PNG...')
    (screenshots_dir / "001_tap_after.png").write_bytes(b'\x89PNG...')

    result = TestResult(
        name="file-screenshot-test",
        status="passed",
        duration=1.0,
        steps=[
            StepResult(
                step_number=1,
                action="tap",
                status="passed",
                duration=0.5,
                screenshot_before_path=screenshots_dir / "001_tap_before.png",
                screenshot_after_path=screenshots_dir / "001_tap_after.png",
            ),
        ],
    )

    generator = ReportGenerator(output_dir)
    html_path = generator.generate_html(result)

    content = html_path.read_text()
    # Should reference files, not base64
    assert 'src="screenshots/001_tap_before.png"' in content
    assert 'src="screenshots/001_tap_after.png"' in content
    assert "data:image/png;base64" not in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py::test_html_references_screenshot_files -v`
Expected: FAIL (still using base64)

**Step 3: Write minimal implementation**

Modify `mutcli/core/report.py`:

1. Update `_result_to_dict` to use paths:

```python
    def _result_to_dict(self, result: TestResult) -> dict[str, Any]:
        """Convert TestResult to dictionary."""
        passed = sum(1 for s in result.steps if s.status == "passed")
        failed = sum(1 for s in result.steps if s.status == "failed")
        skipped = sum(1 for s in result.steps if s.status == "skipped")

        return {
            "test": result.name,
            "status": result.status,
            "duration": f"{result.duration:.1f}s",
            "timestamp": datetime.now().isoformat(),
            "error": result.error,
            "steps": [
                {
                    "number": s.step_number,
                    "action": s.action,
                    "status": s.status,
                    "target": s.target,
                    "description": s.description,
                    "duration": f"{s.duration:.1f}s",
                    "error": s.error,
                    # Use file paths if available, fall back to base64 for backward compat
                    "screenshot_before": self._get_screenshot_src(s.screenshot_before_path, s.screenshot_before),
                    "screenshot_after": self._get_screenshot_src(s.screenshot_after_path, s.screenshot_after),
                    "screenshot_action": self._get_screenshot_src(s.screenshot_action_path, s.screenshot_action),
                    "screenshot_action_end": self._get_screenshot_src(s.screenshot_action_end_path, s.screenshot_action_end),
                    # AI analysis results
                    "ai_verified": s.ai_verified,
                    "ai_outcome": s.ai_outcome,
                    "ai_suggestion": s.ai_suggestion,
                    # Gesture coordinates for visualization
                    "coords": s.details.get("coords"),
                    "end_coords": s.details.get("end_coords"),
                    "direction": s.details.get("direction"),
                    # Trajectory data for swipe visualization
                    "trajectory": s.details.get("trajectory"),
                    "duration_ms": s.details.get("duration_ms"),
                }
                for s in result.steps
            ],
            "summary": {
                "total": len(result.steps),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
        }

    def _get_screenshot_src(self, path: Path | None, fallback_bytes: bytes | None) -> str | None:
        """Get screenshot source - prefer file path, fall back to base64.

        Args:
            path: Path to screenshot file (relative to output_dir)
            fallback_bytes: Screenshot bytes for base64 encoding

        Returns:
            Relative path string, base64 data URI, or None
        """
        if path is not None and path.exists():
            # Return path relative to output_dir
            try:
                return str(path.relative_to(self._output_dir))
            except ValueError:
                return str(path.name)
        if fallback_bytes is not None:
            return self._encode_screenshot(fallback_bytes)
        return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py::test_html_references_screenshot_files -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/report.py tests/test_report.py
git commit -m "feat(report): reference screenshot files instead of base64"
```

---

## Task 5: Skip HTML Report When No Video

**Files:**
- Modify: `mutcli/core/report.py`
- Test: `tests/test_report.py`

**Step 1: Write the failing test**

Add to `tests/test_report.py`:

```python
def test_generate_html_requires_video(tmp_path):
    """generate_html raises error when no video is available."""
    from mutcli.core.executor import StepResult, TestResult
    from mutcli.core.report import ReportGenerator, NoVideoError

    output_dir = tmp_path / "report"
    output_dir.mkdir()
    # No video file created

    result = TestResult(
        name="no-video-test",
        status="passed",
        duration=1.0,
        steps=[
            StepResult(step_number=1, action="tap", status="passed", duration=0.5),
        ],
    )

    generator = ReportGenerator(output_dir)

    with pytest.raises(NoVideoError) as exc_info:
        generator.generate_html(result)

    assert "video recording" in str(exc_info.value).lower()


def test_generate_json_works_without_video(tmp_path):
    """generate_json works even without video."""
    from mutcli.core.executor import StepResult, TestResult
    from mutcli.core.report import ReportGenerator

    output_dir = tmp_path / "report"
    output_dir.mkdir()
    # No video file

    result = TestResult(
        name="json-no-video-test",
        status="passed",
        duration=1.0,
        steps=[
            StepResult(step_number=1, action="tap", status="passed", duration=0.5),
        ],
    )

    generator = ReportGenerator(output_dir)
    json_path = generator.generate_json(result)

    assert json_path.exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_report.py::test_generate_html_requires_video -v`
Expected: FAIL (no NoVideoError exception)

**Step 3: Write minimal implementation**

Add to `mutcli/core/report.py`:

```python
class NoVideoError(Exception):
    """Raised when HTML report is requested but no video is available."""
    pass
```

Modify `generate_html` method to check for video:

```python
    def generate_html(self, result: TestResult) -> Path:
        """Generate interactive HTML report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.html

        Raises:
            NoVideoError: If no video recording is available
        """
        # Check for video recording
        run_video_path = self._output_dir / "recording" / "video.mp4"
        has_run_video = run_video_path.exists()
        has_source_video = self._source_video_path and self._source_video_path.exists()

        if not has_run_video and not has_source_video:
            raise NoVideoError(
                "HTML report requires video recording. "
                "Run test with --video flag or use JSON report instead."
            )

        # ... rest of method unchanged ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_report.py::test_generate_html_requires_video tests/test_report.py::test_generate_json_works_without_video -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/core/report.py tests/test_report.py
git commit -m "feat(report): require video for HTML report generation"
```

---

## Task 6: Update CLI to Handle NoVideoError

**Files:**
- Modify: `mutcli/cli.py:267-278`
- Test: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_run_without_video_skips_html_report(mocker, tmp_path):
    """Running without --video skips HTML report with message."""
    from typer.testing import CliRunner
    from mutcli.cli import app

    runner = CliRunner()

    # Create test file
    test_file = tmp_path / "test.yaml"
    test_file.write_text("""
config:
  app: com.example.app
tests:
  - name: Simple
    steps:
      - tap: "Button"
""")

    # Mock dependencies
    mocker.patch("mutcli.cli.DeviceController.list_devices", return_value=[{"id": "device1", "name": "Test"}])
    mocker.patch("mutcli.cli.ConfigLoader.load")
    mocker.patch("mutcli.cli.TestParser.parse")

    mock_executor = mocker.MagicMock()
    mock_result = mocker.MagicMock()
    mock_result.status = "passed"
    mock_result.steps = []
    mock_executor.execute_test.return_value = mock_result
    mocker.patch("mutcli.cli.TestExecutor", return_value=mock_executor)

    mock_scrcpy = mocker.MagicMock()
    mock_scrcpy.connect.return_value = True
    mocker.patch("mutcli.cli.ScrcpyService", return_value=mock_scrcpy)

    result = runner.invoke(app, ["run", str(test_file), "--no-video"])

    # Should succeed but mention skipping HTML
    assert "HTML report skipped" in result.output or "no video" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_run_without_video_skips_html_report -v`
Expected: FAIL (currently crashes or doesn't show message)

**Step 3: Write minimal implementation**

Modify `mutcli/cli.py` around line 267-278:

```python
    from mutcli.core.report import NoVideoError, ReportGenerator

    # ... existing code ...

    # Check for source video from recording session
    source_video = test_file.parent / "video.mp4"
    generator = ReportGenerator(
        report_dir,
        source_video_path=source_video if source_video.exists() else None,
    )
    generator.generate_json(result)

    # Generate HTML report (requires video)
    try:
        html_path = generator.generate_html(result)
        console.print()
        console.print(f"[dim]Report: {html_path}[/dim]")
    except NoVideoError:
        console.print()
        console.print("[dim]HTML report skipped (no video recording)[/dim]")
        console.print(f"[dim]JSON results: {report_dir / 'report.json'}[/dim]")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_run_without_video_skips_html_report -v`
Expected: PASS

**Step 5: Commit**

```bash
git add mutcli/cli.py tests/test_cli.py
git commit -m "feat(cli): gracefully skip HTML report when no video"
```

---

## Task 7: Update Existing Tests

**Files:**
- Modify: `tests/test_report.py`

**Step 1: Fix tests that expect base64**

Update `test_html_embeds_screenshots_as_base64` test - it should now only apply when using fallback bytes (no path):

```python
def test_html_uses_base64_fallback_when_no_path(tmp_path):
    """HTML report uses base64 for backward compatibility when no path available."""
    # ... similar to existing test but name clarifies it's fallback behavior
```

**Step 2: Fix tests that expect HTML without video**

Update tests like `test_html_shows_no_video_message_when_no_video` - they now need to either:
- Create a video file, OR
- Expect NoVideoError

**Step 3: Run full test suite**

Run: `pytest tests/test_report.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_report.py
git commit -m "test(report): update tests for video-required HTML reports"
```

---

## Task 8: Clean Up - Remove Unused Bytes from Report Serialization

**Files:**
- Modify: `mutcli/core/report.py`

**Step 1: Remove `_encode_screenshot` if no longer needed**

Check if any code path still uses base64 encoding. If not, remove the method.

**Step 2: Run full test suite**

Run: `pytest`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add mutcli/core/report.py
git commit -m "refactor(report): remove unused base64 encoding"
```

---

## Summary

After completing all tasks:

1. **StepResult** has path fields for report screenshots
2. **ScreenshotSaver** utility saves frames with structured naming
3. **TestExecutor** extracts frames to files after video recording
4. **ReportGenerator** references files in HTML, requires video
5. **CLI** gracefully handles no-video case
6. **Tests** updated to reflect new behavior

Output structure:
```
tests/my-test/runs/2026-01-17_14-30-25/
├── report.json              # Always generated
├── report.html              # Only with video
├── recording/
│   └── video.mp4
└── screenshots/
    ├── 001_tap_before.png
    ├── 001_tap_action.png
    ├── 001_tap_after.png
    └── ...
```
