"""Tests for StepAnalyzer."""

from unittest.mock import MagicMock, patch

from mutcli.core.step_analyzer import AnalyzedStep, StepAnalyzer


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
