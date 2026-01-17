"""Tests for StepAnalyzer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core import exceptions as google_exceptions

from mutcli.core.step_analyzer import (
    RETRYABLE_EXCEPTIONS,
    AnalyzedStep,
    StepAnalyzer,
)
from mutcli.core.step_collapsing import CollapsedStep


class TestAnalyzedStep:
    """Test AnalyzedStep dataclass."""

    def test_creation_with_all_fields(self):
        """AnalyzedStep should store all fields correctly."""
        original_tap = {"x": 100, "y": 200, "timestamp": 1.5}
        step = AnalyzedStep(
            index=0,
            original_tap=original_tap,
            element_text="Submit",
            before_description="Login form displayed",
            after_description="Loading spinner appeared",
            suggested_verification="Login form submitted",
        )

        assert step.index == 0
        assert step.original_tap == original_tap
        assert step.element_text == "Submit"
        assert step.before_description == "Login form displayed"
        assert step.after_description == "Loading spinner appeared"
        assert step.suggested_verification == "Login form submitted"

    def test_creation_with_none_element_text(self):
        """AnalyzedStep should allow None element_text."""
        step = AnalyzedStep(
            index=1,
            original_tap={"x": 50, "y": 100, "timestamp": 0.0},
            element_text=None,
            before_description="Home screen",
            after_description="Menu opened",
            suggested_verification=None,
        )

        assert step.element_text is None
        assert step.suggested_verification is None


class TestStepAnalyzerInitialization:
    """Test StepAnalyzer initialization."""

    def test_stores_ai_analyzer(self):
        """Should store AIAnalyzer instance."""
        mock_ai = MagicMock()

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        assert analyzer._ai_analyzer is mock_ai


class TestAnalyzeStep:
    """Test analyze_step method."""

    def test_extracts_element_text_from_screenshot(self):
        """Should extract element text using AI."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        # Mock the analyze_image method to return JSON with element text
        mock_ai._client = MagicMock()

        # We'll mock the internal method that calls the AI
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        # Mock the element extraction response
        with patch.object(analyzer, '_extract_element', return_value={
            "element_text": "Login Button",
            "element_type": "button"
        }):
            # Mock the step analysis response
            mock_ai.analyze_step.return_value = {
                "before": "Login screen with form",
                "action": "Tap on login button",
                "after": "Loading spinner visible",
                "suggested_verification": "User logged in successfully",
            }

            result = analyzer.analyze_step(
                before_screenshot=b"fake_png_before",
                after_screenshot=b"fake_png_after",
                tap_coordinates=(100, 200),
            )

        assert result.element_text == "Login Button"
        assert result.before_description == "Login screen with form"
        assert result.after_description == "Loading spinner visible"
        assert result.suggested_verification == "User logged in successfully"
        # Placeholders are set by analyze_step, caller sets correct values
        assert result.index == 0
        assert result.original_tap == {}

    def test_returns_none_element_text_when_ai_unavailable(self):
        """Should return None element_text when AI is unavailable."""
        mock_ai = MagicMock()
        mock_ai.is_available = False
        mock_ai.analyze_step.return_value = {
            "before": "Unknown (AI unavailable)",
            "action": "Unknown",
            "after": "Unknown",
            "suggested_verification": None,
            "skipped": True,
        }

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        result = analyzer.analyze_step(
            before_screenshot=b"fake_png_before",
            after_screenshot=b"fake_png_after",
            tap_coordinates=(100, 200),
        )

        assert result.element_text is None
        assert "unavailable" in result.before_description.lower()

    def test_returns_none_element_text_when_extraction_fails(self):
        """Should return None element_text when AI extraction fails."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_step.return_value = {
            "before": "Screen state before",
            "action": "Tap action",
            "after": "Screen state after",
            "suggested_verification": None,
        }

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        # Mock extraction to return None (failed to identify)
        with patch.object(analyzer, '_extract_element', return_value={
            "element_text": None,
            "element_type": "other"
        }):
            result = analyzer.analyze_step(
                before_screenshot=b"fake_png_before",
                after_screenshot=b"fake_png_after",
                tap_coordinates=(100, 200),
            )

        assert result.element_text is None


class TestAnalyzeAll:
    """Test analyze_all method."""

    def test_processes_all_screenshots(self, tmp_path):
        """Should analyze all steps from recording."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_step.return_value = {
            "before": "Before state",
            "action": "Tap action",
            "after": "After state",
            "suggested_verification": "Verification",
        }

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        # Create test screenshots directory
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        # Create mock screenshot files (before and after for each step)
        for i in range(1, 4):
            (screenshots_dir / f"step_{i:03d}_before.png").write_bytes(b"png_before")
            (screenshots_dir / f"step_{i:03d}_after.png").write_bytes(b"png_after")

        touch_events = [
            {"x": 100, "y": 200, "timestamp": 0.0},
            {"x": 150, "y": 250, "timestamp": 1.0},
            {"x": 200, "y": 300, "timestamp": 2.0},
        ]

        # Mock element extraction
        with patch.object(analyzer, '_extract_element', return_value={
            "element_text": "Button",
            "element_type": "button"
        }):
            results = analyzer.analyze_all(
                touch_events=touch_events,
                screenshots_dir=screenshots_dir,
            )

        assert len(results) == 3
        assert all(isinstance(r, AnalyzedStep) for r in results)
        assert results[0].index == 0
        assert results[1].index == 1
        assert results[2].index == 2

    def test_handles_missing_screenshot_files(self, tmp_path):
        """Should handle missing screenshot files gracefully."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_step.return_value = {
            "before": "Before state",
            "action": "Tap action",
            "after": "After state",
            "suggested_verification": None,
        }

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        # Create screenshots directory with only some files
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        # Only create screenshots for step 1
        (screenshots_dir / "step_001_before.png").write_bytes(b"png_before")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png_after")
        # Step 2 screenshots missing

        touch_events = [
            {"x": 100, "y": 200, "timestamp": 0.0},
            {"x": 150, "y": 250, "timestamp": 1.0},  # No screenshot for this
        ]

        with patch.object(analyzer, '_extract_element', return_value={
            "element_text": None,
            "element_type": "other"
        }):
            results = analyzer.analyze_all(
                touch_events=touch_events,
                screenshots_dir=screenshots_dir,
            )

        # Should return results for all events, handling missing gracefully
        assert len(results) == 2
        # First step should have proper analysis
        assert results[0].index == 0
        # Second step should indicate missing screenshot
        assert results[1].index == 1
        desc = results[1].before_description
        assert "missing" in desc.lower() or desc == "Before state"

    def test_returns_empty_list_for_empty_events(self, tmp_path):
        """Should return empty list when no touch events."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        results = analyzer.analyze_all(
            touch_events=[],
            screenshots_dir=screenshots_dir,
        )

        assert results == []

    def test_preserves_original_tap_data(self, tmp_path):
        """Should preserve original tap data in AnalyzedStep."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_step.return_value = {
            "before": "Before",
            "action": "Action",
            "after": "After",
            "suggested_verification": None,
        }

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        original_tap = {"x": 123, "y": 456, "timestamp": 0.789, "extra_field": "value"}

        with patch.object(analyzer, '_extract_element', return_value={
            "element_text": None,
            "element_type": "other"
        }):
            results = analyzer.analyze_all(
                touch_events=[original_tap],
                screenshots_dir=screenshots_dir,
            )

        assert results[0].original_tap == original_tap
        assert results[0].original_tap["extra_field"] == "value"


class TestExtractElement:
    """Test _extract_element internal method."""

    def test_calls_ai_with_correct_prompt(self):
        """Should call AI with element extraction prompt."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        # Mock analyze_image to return JSON response
        mock_ai.analyze_image.return_value = '{"element_text": "Submit", "element_type": "button"}'

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        result = analyzer._extract_element(
            screenshot=b"fake_png",
            tap_coordinates=(100, 200),
        )

        assert result["element_text"] == "Submit"
        assert result["element_type"] == "button"
        # Verify analyze_image was called with correct arguments
        mock_ai.analyze_image.assert_called_once()
        call_args = mock_ai.analyze_image.call_args
        assert call_args[0][0] == b"fake_png"  # screenshot
        assert "(100, 200)" in call_args[0][1]  # prompt contains coordinates

    def test_returns_none_when_ai_unavailable(self):
        """Should return None element_text when AI unavailable."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        # analyze_image returns None when AI unavailable
        mock_ai.analyze_image.return_value = None

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        result = analyzer._extract_element(
            screenshot=b"fake_png",
            tap_coordinates=(100, 200),
        )

        assert result["element_text"] is None

    def test_handles_ai_error_gracefully(self):
        """Should handle AI errors gracefully (analyze_image returns None)."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        # analyze_image returns None on error
        mock_ai.analyze_image.return_value = None

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        result = analyzer._extract_element(
            screenshot=b"fake_png",
            tap_coordinates=(100, 200),
        )

        assert result["element_text"] is None

    def test_handles_malformed_json_response(self):
        """Should handle malformed JSON from AI."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        # analyze_image returns invalid JSON
        mock_ai.analyze_image.return_value = "not valid json"

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        result = analyzer._extract_element(
            screenshot=b"fake_png",
            tap_coordinates=(100, 200),
        )

        assert result["element_text"] is None


class TestRetryableExceptions:
    """Test RETRYABLE_EXCEPTIONS configuration."""

    def test_includes_google_rate_limit_exceptions(self):
        """Should include TooManyRequests and ResourceExhausted."""
        assert google_exceptions.TooManyRequests in RETRYABLE_EXCEPTIONS
        assert google_exceptions.ResourceExhausted in RETRYABLE_EXCEPTIONS

    def test_includes_google_server_errors(self):
        """Should include 5xx server errors."""
        assert google_exceptions.InternalServerError in RETRYABLE_EXCEPTIONS
        assert google_exceptions.BadGateway in RETRYABLE_EXCEPTIONS
        assert google_exceptions.ServiceUnavailable in RETRYABLE_EXCEPTIONS

    def test_includes_timeout_errors(self):
        """Should include timeout-related exceptions."""
        assert google_exceptions.DeadlineExceeded in RETRYABLE_EXCEPTIONS
        assert TimeoutError in RETRYABLE_EXCEPTIONS

    def test_includes_connection_errors(self):
        """Should include ConnectionError."""
        assert ConnectionError in RETRYABLE_EXCEPTIONS

    def test_does_not_include_client_errors(self):
        """Should NOT include 4xx client errors that shouldn't be retried."""
        # These are client errors that indicate a problem with the request
        # and should not be retried
        assert google_exceptions.InvalidArgument not in RETRYABLE_EXCEPTIONS
        assert google_exceptions.Unauthenticated not in RETRYABLE_EXCEPTIONS
        assert google_exceptions.PermissionDenied not in RETRYABLE_EXCEPTIONS
        assert google_exceptions.NotFound not in RETRYABLE_EXCEPTIONS


class TestAnalyzeAllParallel:
    """Test analyze_all_parallel async method."""

    @pytest.mark.asyncio
    async def test_processes_steps_in_parallel(self, tmp_path):
        """Should analyze all steps concurrently."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Button",
            "element_type": "button",
            "before_description": "Before state",
            "after_description": "After state",
            "suggested_verification": None,
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        # Create test screenshots directory
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        # Create mock screenshot files for 3 tap steps
        for i in range(1, 4):
            (screenshots_dir / f"step_{i:03d}_before.png").write_bytes(b"png_before")
            (screenshots_dir / f"step_{i:03d}_touch.png").write_bytes(b"png_touch")
            (screenshots_dir / f"step_{i:03d}_after.png").write_bytes(b"png_after")

        touch_events = [
            {"gesture": "tap", "x": 100, "y": 200},
            {"gesture": "tap", "x": 150, "y": 250},
            {"gesture": "tap", "x": 200, "y": 300},
        ]

        results = await analyzer.analyze_all_parallel(
            touch_events=touch_events,
            screenshots_dir=screenshots_dir,
        )

        assert len(results) == 3
        assert all(isinstance(r, AnalyzedStep) for r in results)
        # Results should be in original order
        assert results[0].index == 0
        assert results[1].index == 1
        assert results[2].index == 2

    @pytest.mark.asyncio
    async def test_calls_progress_callback(self, tmp_path):
        """Should call progress callback as each step completes."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Button",
            "element_type": "button",
            "before_description": "Before",
            "after_description": "After",
            "suggested_verification": None,
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        for i in range(1, 3):
            (screenshots_dir / f"step_{i:03d}_before.png").write_bytes(b"png")
            (screenshots_dir / f"step_{i:03d}_touch.png").write_bytes(b"png")
            (screenshots_dir / f"step_{i:03d}_after.png").write_bytes(b"png")

        touch_events = [
            {"gesture": "tap", "x": 100, "y": 200},
            {"gesture": "tap", "x": 150, "y": 250},
        ]

        progress_calls: list[tuple[int, int]] = []

        def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        await analyzer.analyze_all_parallel(
            touch_events=touch_events,
            screenshots_dir=screenshots_dir,
            on_progress=on_progress,
        )

        # Should have been called twice (once for each completed step)
        assert len(progress_calls) == 2
        # Total should always be 2
        assert all(total == 2 for _, total in progress_calls)
        # Completed should include 1 and 2
        completed_values = {c for c, _ in progress_calls}
        assert completed_values == {1, 2}

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_events(self, tmp_path):
        """Should return empty list when no touch events."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        results = await analyzer.analyze_all_parallel(
            touch_events=[],
            screenshots_dir=screenshots_dir,
        )

        assert results == []


class TestAnalyzeWithRetry:
    """Test _analyze_with_retry method."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self, tmp_path):
        """Should retry when TooManyRequests is raised."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise google_exceptions.TooManyRequests("Rate limited")
            return {
                "element_text": "Button",
                "element_type": "button",
                "before_description": "Before",
                "after_description": "After",
                "suggested_verification": None,
            }

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        assert call_count == 2  # First call failed, second succeeded
        assert index == 0
        assert result.element_text == "Button"

    @pytest.mark.asyncio
    async def test_retries_on_service_unavailable(self, tmp_path):
        """Should retry when ServiceUnavailable is raised."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise google_exceptions.ServiceUnavailable("503")
            return {
                "element_text": "OK",
                "element_type": "button",
                "before_description": "Before",
                "after_description": "After",
                "suggested_verification": None,
            }

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        assert call_count == 2
        assert result.element_text == "OK"

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, tmp_path):
        """Should NOT retry on client errors like InvalidArgument."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise google_exceptions.InvalidArgument("Invalid API key")

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        # Should only be called once - no retry on client errors
        assert call_count == 1
        assert index == 0
        assert result.element_text is None
        assert "Invalid API key" in result.before_description

    @pytest.mark.asyncio
    async def test_no_retry_on_permission_denied(self, tmp_path):
        """Should NOT retry on PermissionDenied errors."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise google_exceptions.PermissionDenied("Access denied")

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        assert call_count == 1  # No retry
        assert "Access denied" in result.before_description

    @pytest.mark.asyncio
    async def test_returns_placeholder_after_max_retries(self, tmp_path):
        """Should return placeholder after all retries exhausted."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise google_exceptions.ServiceUnavailable("Still down")

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        # Should be called 3 times (initial + 2 retries)
        assert call_count == 3
        assert index == 0
        assert result.element_text is None
        assert "Still down" in result.before_description

    @pytest.mark.asyncio
    async def test_retries_on_timeout_error(self, tmp_path):
        """Should retry on Python TimeoutError."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_tap(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Connection timed out")
            return {
                "element_text": "Done",
                "element_type": "button",
                "before_description": "Before",
                "after_description": "After",
                "suggested_verification": None,
            }

        mock_ai.analyze_tap = mock_analyze_tap

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        index, result = await analyzer._analyze_with_retry(
            index=0,
            event=event,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        assert call_count == 2
        assert result.element_text == "Done"


class TestGestureRouting:
    """Test gesture routing to correct handlers."""

    @pytest.mark.asyncio
    async def test_routes_tap_to_analyze_tap(self, tmp_path):
        """Should route tap gesture to analyze_tap handler."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Submit",
            "element_type": "button",
            "before_description": "Form displayed",
            "after_description": "Form submitted",
            "suggested_verification": None,
        })
        mock_ai.analyze_swipe = AsyncMock()
        mock_ai.analyze_long_press = AsyncMock()

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "tap", "x": 100, "y": 200}

        result = await analyzer._analyze_single_step(0, event, screenshots_dir)

        mock_ai.analyze_tap.assert_called_once()
        mock_ai.analyze_swipe.assert_not_called()
        mock_ai.analyze_long_press.assert_not_called()
        assert result.element_text == "Submit"

    @pytest.mark.asyncio
    async def test_routes_swipe_to_analyze_swipe(self, tmp_path):
        """Should route swipe gesture to analyze_swipe handler."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock()
        mock_ai.analyze_swipe = AsyncMock(return_value={
            "direction": "up",
            "content_changed": "Scrolled to next section",
            "before_description": "Top of list",
            "after_description": "Middle of list",
            "suggested_verification": None,
        })
        mock_ai.analyze_long_press = AsyncMock()

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_swipe_start.png").write_bytes(b"png")
        (screenshots_dir / "step_001_swipe_end.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "swipe", "x": 200, "y": 500, "end_x": 200, "end_y": 200}

        result = await analyzer._analyze_single_step(0, event, screenshots_dir)

        mock_ai.analyze_tap.assert_not_called()
        mock_ai.analyze_swipe.assert_called_once()
        mock_ai.analyze_long_press.assert_not_called()
        assert result.element_text == "swipe up"

    @pytest.mark.asyncio
    async def test_routes_long_press_to_analyze_long_press(self, tmp_path):
        """Should route long_press gesture to analyze_long_press handler."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock()
        mock_ai.analyze_swipe = AsyncMock()
        mock_ai.analyze_long_press = AsyncMock(return_value={
            "element_text": "Item 1",
            "element_type": "list_item",
            "result_type": "context_menu",
            "before_description": "List displayed",
            "after_description": "Context menu shown",
            "suggested_verification": "Context menu visible",
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_press_start.png").write_bytes(b"png")
        (screenshots_dir / "step_001_press_held.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "long_press", "x": 150, "y": 300, "duration_ms": 800}

        result = await analyzer._analyze_single_step(0, event, screenshots_dir)

        mock_ai.analyze_tap.assert_not_called()
        mock_ai.analyze_swipe.assert_not_called()
        mock_ai.analyze_long_press.assert_called_once()
        assert result.element_text == "Item 1"

    @pytest.mark.asyncio
    async def test_unknown_gesture_defaults_to_tap(self, tmp_path):
        """Should treat unknown gesture as tap."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Element",
            "element_type": "other",
            "before_description": "Before",
            "after_description": "After",
            "suggested_verification": None,
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        event = {"gesture": "unknown_gesture", "x": 100, "y": 200}

        result = await analyzer._analyze_single_step(0, event, screenshots_dir)

        mock_ai.analyze_tap.assert_called_once()
        assert result.element_text == "Element"


class TestPlaceholderResult:
    """Test _placeholder_result method."""

    def test_creates_placeholder_with_error_message(self):
        """Should create placeholder with error info."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        event = {"gesture": "tap", "x": 100, "y": 200}

        result = analyzer._placeholder_result(
            index=2,
            event=event,
            error_message="Connection failed",
        )

        assert result.index == 2
        assert result.original_tap == event
        assert result.element_text is None
        assert "Connection failed" in result.before_description
        assert "Connection failed" in result.after_description
        assert result.suggested_verification is None

    def test_preserves_original_event_data(self):
        """Should preserve all original event data."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        event = {
            "gesture": "swipe",
            "x": 100,
            "y": 200,
            "end_x": 100,
            "end_y": 500,
            "custom_field": "value",
        }

        result = analyzer._placeholder_result(
            index=0,
            event=event,
            error_message="Error",
        )

        assert result.original_tap == event
        assert result.original_tap["custom_field"] == "value"


class TestAnalyzeTypeStep:
    """Test _analyze_type_step method."""

    @pytest.mark.asyncio
    async def test_analyzes_type_action(self, tmp_path):
        """Should analyze type action using before/after frames."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_type = AsyncMock(return_value={
            "element_text": "Search field",
            "element_type": "search_box",
            "before_description": "Search screen with keyboard",
            "after_description": "Search field contains text",
            "suggested_verification": "search text visible",
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png_before")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png_after")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.5,
            original_indices=(0, 5),
            tap_count=6,
            text="hello",
        )

        result = await analyzer._analyze_type_step(0, step, screenshots_dir)

        mock_ai.analyze_type.assert_called_once()
        assert result.element_text == "Search field"
        assert result.before_description == "Search screen with keyboard"
        assert result.after_description == "Search field contains text"
        assert result.original_tap["action"] == "type"
        assert result.original_tap["tap_count"] == 6
        assert result.original_tap["text"] == "hello"

    @pytest.mark.asyncio
    async def test_raises_on_missing_before_frame(self, tmp_path):
        """Should raise FileNotFoundError when before frame is missing."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        # Only create after frame
        (screenshots_dir / "step_001_after.png").write_bytes(b"png_after")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.5,
            original_indices=(0, 5),
        )

        with pytest.raises(FileNotFoundError, match="before"):
            await analyzer._analyze_type_step(0, step, screenshots_dir)

    @pytest.mark.asyncio
    async def test_raises_on_missing_after_frame(self, tmp_path):
        """Should raise FileNotFoundError when after frame is missing."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        # Only create before frame
        (screenshots_dir / "step_001_before.png").write_bytes(b"png_before")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.5,
            original_indices=(0, 5),
        )

        with pytest.raises(FileNotFoundError, match="after"):
            await analyzer._analyze_type_step(0, step, screenshots_dir)


class TestAnalyzeCollapsedStepsParallel:
    """Test analyze_collapsed_steps_parallel method."""

    @pytest.mark.asyncio
    async def test_processes_mixed_actions_in_parallel(self, tmp_path):
        """Should analyze all collapsed step types concurrently."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Submit",
            "element_type": "button",
            "before_description": "Form",
            "after_description": "Loading",
            "suggested_verification": None,
        })
        mock_ai.analyze_type = AsyncMock(return_value={
            "element_text": "Email field",
            "element_type": "text_field",
            "before_description": "Login form",
            "after_description": "Email entered",
            "suggested_verification": None,
        })
        mock_ai.analyze_swipe = AsyncMock(return_value={
            "direction": "up",
            "content_changed": "New items",
            "before_description": "Top of list",
            "after_description": "More items",
            "suggested_verification": None,
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        # Step 1: tap
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        # Step 2: type
        (screenshots_dir / "step_002_before.png").write_bytes(b"png")
        (screenshots_dir / "step_002_after.png").write_bytes(b"png")

        # Step 3: swipe
        (screenshots_dir / "step_003_before.png").write_bytes(b"png")
        (screenshots_dir / "step_003_swipe_start.png").write_bytes(b"png")
        (screenshots_dir / "step_003_swipe_end.png").write_bytes(b"png")
        (screenshots_dir / "step_003_after.png").write_bytes(b"png")

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="tap",
                timestamp=1.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
            ),
            CollapsedStep(
                index=2,
                action="type",
                timestamp=2.0,
                original_indices=(1, 6),
                tap_count=6,
                text="test@email.com",
            ),
            CollapsedStep(
                index=3,
                action="swipe",
                timestamp=3.0,
                original_indices=(7, 7),
                start={"x": 200, "y": 500},
                end={"x": 200, "y": 200},
                direction="up",
            ),
        ]

        results = await analyzer.analyze_collapsed_steps_parallel(
            collapsed_steps=collapsed_steps,
            screenshots_dir=screenshots_dir,
        )

        assert len(results) == 3
        # Results should be in order
        assert results[0].index == 0
        assert results[0].element_text == "Submit"
        assert results[1].index == 1
        assert results[1].element_text == "Email field"
        assert results[2].index == 2
        assert results[2].element_text == "swipe up"

    @pytest.mark.asyncio
    async def test_calls_progress_callback(self, tmp_path):
        """Should call progress callback as each step completes."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_type = AsyncMock(return_value={
            "element_text": "Field",
            "element_type": "text_field",
            "before_description": "Before",
            "after_description": "After",
            "suggested_verification": None,
        })

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        for i in range(1, 3):
            (screenshots_dir / f"step_{i:03d}_before.png").write_bytes(b"png")
            (screenshots_dir / f"step_{i:03d}_after.png").write_bytes(b"png")

        collapsed_steps = [
            CollapsedStep(index=1, action="type", timestamp=1.0, original_indices=(0, 3)),
            CollapsedStep(index=2, action="type", timestamp=2.0, original_indices=(4, 7)),
        ]

        progress_calls: list[tuple[int, int]] = []

        def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        await analyzer.analyze_collapsed_steps_parallel(
            collapsed_steps=collapsed_steps,
            screenshots_dir=screenshots_dir,
            on_progress=on_progress,
        )

        assert len(progress_calls) == 2
        assert all(total == 2 for _, total in progress_calls)
        completed_values = {c for c, _ in progress_calls}
        assert completed_values == {1, 2}

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_steps(self, tmp_path):
        """Should return empty list when no collapsed steps."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        results = await analyzer.analyze_collapsed_steps_parallel(
            collapsed_steps=[],
            screenshots_dir=screenshots_dir,
        )

        assert results == []


class TestCollapsedStepRouting:
    """Test routing of collapsed steps to correct handlers."""

    @pytest.mark.asyncio
    async def test_routes_type_to_analyze_type(self, tmp_path):
        """Should route type action to analyze_type handler."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_type = AsyncMock(return_value={
            "element_text": "Search",
            "element_type": "search_box",
            "before_description": "Before",
            "after_description": "After",
            "suggested_verification": None,
        })
        mock_ai.analyze_tap = AsyncMock()

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.0,
            original_indices=(0, 5),
            tap_count=6,
        )

        result = await analyzer._analyze_single_collapsed_step(0, step, screenshots_dir)

        mock_ai.analyze_type.assert_called_once()
        mock_ai.analyze_tap.assert_not_called()
        assert result.element_text == "Search"

    @pytest.mark.asyncio
    async def test_routes_tap_to_analyze_tap(self, tmp_path):
        """Should route tap action to analyze_tap handler."""
        mock_ai = MagicMock()
        mock_ai.is_available = True
        mock_ai.analyze_tap = AsyncMock(return_value={
            "element_text": "Button",
            "element_type": "button",
            "before_description": "Before",
            "after_description": "After",
            "suggested_verification": None,
        })
        mock_ai.analyze_type = AsyncMock()

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_touch.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        step = CollapsedStep(
            index=1,
            action="tap",
            timestamp=1.0,
            original_indices=(0, 0),
            coordinates={"x": 100, "y": 200},
        )

        result = await analyzer._analyze_single_collapsed_step(0, step, screenshots_dir)

        mock_ai.analyze_tap.assert_called_once()
        mock_ai.analyze_type.assert_not_called()
        assert result.element_text == "Button"


class TestCollapsedStepToEvent:
    """Test _collapsed_step_to_event conversion method."""

    def test_converts_tap_step(self):
        """Should convert tap CollapsedStep to event dict."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        step = CollapsedStep(
            index=1,
            action="tap",
            timestamp=1.5,
            original_indices=(0, 0),
            coordinates={"x": 100, "y": 200},
        )

        event = analyzer._collapsed_step_to_event(step)

        assert event["gesture"] == "tap"
        assert event["action"] == "tap"
        assert event["timestamp"] == 1.5
        assert event["x"] == 100
        assert event["y"] == 200

    def test_converts_type_step(self):
        """Should convert type CollapsedStep to event dict."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        step = CollapsedStep(
            index=2,
            action="type",
            timestamp=2.0,
            original_indices=(1, 6),
            tap_count=6,
            text="hello",
        )

        event = analyzer._collapsed_step_to_event(step)

        # Type action should map to "tap" gesture for compatibility
        assert event["gesture"] == "tap"
        assert event["action"] == "type"
        assert event["timestamp"] == 2.0
        assert event["tap_count"] == 6
        assert event["text"] == "hello"

    def test_converts_swipe_step(self):
        """Should convert swipe CollapsedStep to event dict."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        step = CollapsedStep(
            index=3,
            action="swipe",
            timestamp=3.0,
            original_indices=(7, 7),
            start={"x": 200, "y": 500},
            end={"x": 200, "y": 200},
            direction="up",
        )

        event = analyzer._collapsed_step_to_event(step)

        assert event["gesture"] == "swipe"
        assert event["action"] == "swipe"
        assert event["timestamp"] == 3.0
        assert event["x"] == 200
        assert event["y"] == 500
        assert event["end_x"] == 200
        assert event["end_y"] == 200

    def test_converts_long_press_step(self):
        """Should convert long_press CollapsedStep to event dict."""
        mock_ai = MagicMock()
        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        step = CollapsedStep(
            index=4,
            action="long_press",
            timestamp=4.0,
            original_indices=(8, 8),
            coordinates={"x": 150, "y": 300},
            duration_ms=800,
        )

        event = analyzer._collapsed_step_to_event(step)

        assert event["gesture"] == "long_press"
        assert event["action"] == "long_press"
        assert event["timestamp"] == 4.0
        assert event["x"] == 150
        assert event["y"] == 300
        assert event["duration_ms"] == 800


class TestCollapsedStepRetry:
    """Test _analyze_collapsed_step_with_retry method."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, tmp_path):
        """Should retry collapsed step analysis on rate limit."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_type(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise google_exceptions.TooManyRequests("Rate limited")
            return {
                "element_text": "Field",
                "element_type": "text_field",
                "before_description": "Before",
                "after_description": "After",
                "suggested_verification": None,
            }

        mock_ai.analyze_type = mock_analyze_type

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.0,
            original_indices=(0, 5),
        )

        index, result = await analyzer._analyze_collapsed_step_with_retry(
            index=0,
            step=step,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        assert call_count == 2
        assert index == 0
        assert result.element_text == "Field"

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, tmp_path):
        """Should NOT retry on client errors."""
        mock_ai = MagicMock()
        mock_ai.is_available = True

        call_count = 0

        async def mock_analyze_type(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise google_exceptions.InvalidArgument("Bad request")

        mock_ai.analyze_type = mock_analyze_type

        analyzer = StepAnalyzer(ai_analyzer=mock_ai)

        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        (screenshots_dir / "step_001_before.png").write_bytes(b"png")
        (screenshots_dir / "step_001_after.png").write_bytes(b"png")

        step = CollapsedStep(
            index=1,
            action="type",
            timestamp=1.0,
            original_indices=(0, 5),
        )

        index, result = await analyzer._analyze_collapsed_step_with_retry(
            index=0,
            step=step,
            screenshots_dir=screenshots_dir,
            max_retries=2,
        )

        # Should only be called once - no retry
        assert call_count == 1
        assert index == 0
        assert result.element_text is None
        assert "Bad request" in result.before_description
