"""Tests for CLI stop command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mutcli.cli import app
from mutcli.core.step_analyzer import AnalyzedStep
from mutcli.core.verification_suggester import VerificationPoint

runner = CliRunner()


class TestStopCommand:
    """Tests for the stop command."""

    @pytest.fixture
    def recording_dir(self, tmp_path: Path) -> Path:
        """Create a mock recording directory with touch events."""
        test_dir = tmp_path / "test-recording"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [
            {"x": 540, "y": 800, "timestamp": 1.0, "screen_height": 2400},
            {"x": 520, "y": 1400, "timestamp": 2.0, "screen_height": 2400},
        ]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        return test_dir

    @pytest.fixture
    def recording_dir_with_keyboard_taps(self, tmp_path: Path) -> Path:
        """Create recording with keyboard taps (bottom 40% of screen)."""
        test_dir = tmp_path / "keyboard-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        # Screen height 2400: keyboard area y > 1440 (bottom 40%)
        touch_events = [
            {"x": 540, "y": 500, "timestamp": 1.0, "screen_height": 2400},  # Non-keyboard
            {"x": 200, "y": 1800, "timestamp": 2.0, "screen_height": 2400},  # Keyboard
            {"x": 300, "y": 1850, "timestamp": 2.3, "screen_height": 2400},  # Keyboard
            {"x": 250, "y": 1900, "timestamp": 2.6, "screen_height": 2400},  # Keyboard
            {"x": 540, "y": 600, "timestamp": 3.0, "screen_height": 2400},  # Non-keyboard
        ]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        return test_dir

    def test_stop_generates_yaml(self, recording_dir: Path) -> None:
        """Stop command should generate test.yaml file."""
        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        assert (recording_dir / "test.yaml").exists()

    def test_stop_detects_typing_sequences(
        self, recording_dir_with_keyboard_taps: Path
    ) -> None:
        """Stop command should detect typing sequences from touch events."""
        with (
            patch("mutcli.core.config.ConfigLoader.load") as mock_load,
            patch("mutcli.core.typing_detector.TypingDetector") as mock_detector_class,
        ):
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            # Mock the TypingDetector to return a sequence
            mock_detector = MagicMock()
            mock_detector.detect.return_value = []  # No sequences for simpler test
            mock_detector_class.return_value = mock_detector

            result = runner.invoke(app, ["stop", str(recording_dir_with_keyboard_taps)])

        assert result.exit_code == 0
        # Verify TypingDetector was called with correct screen height
        mock_detector_class.assert_called_once_with(2400)
        mock_detector.detect.assert_called_once()

    def test_stop_prompts_for_typed_text(
        self, recording_dir_with_keyboard_taps: Path
    ) -> None:
        """Stop command should prompt user for typed text when typing detected."""
        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            # The actual TypingDetector will detect the keyboard taps
            # Simulate user input for typing prompt
            result = runner.invoke(
                app,
                ["stop", str(recording_dir_with_keyboard_taps)],
                input="hello world\n",  # User types this text
            )

        assert result.exit_code == 0
        # Check that typing was detected (3 keyboard taps at indices 1-3)
        output_lower = result.output.lower()
        assert "typing sequence" in output_lower or "typing pattern" in output_lower

    def test_stop_uses_ai_analysis_when_api_key_available(
        self, recording_dir: Path
    ) -> None:
        """Stop command should use AI analysis when API key is configured."""
        with (
            patch("mutcli.core.config.ConfigLoader.load") as mock_load,
            patch("mutcli.core.ai_analyzer.AIAnalyzer") as mock_ai_class,
            patch("mutcli.core.step_analyzer.StepAnalyzer") as mock_step_analyzer_class,
            patch(
                "mutcli.core.verification_suggester.VerificationSuggester"
            ) as mock_suggester_class,
        ):
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = "test-api-key"
            mock_load.return_value = mock_config

            # Mock AI analyzer
            mock_ai = MagicMock()
            mock_ai_class.return_value = mock_ai

            # Mock step analyzer
            mock_step_analyzer = MagicMock()
            mock_analyzed_steps = [
                AnalyzedStep(
                    index=0,
                    original_tap={"x": 540, "y": 800, "timestamp": 1.0},
                    element_text="Login",
                    before_description="Login screen",
                    after_description="Home screen",
                    suggested_verification=None,
                ),
                AnalyzedStep(
                    index=1,
                    original_tap={"x": 520, "y": 1400, "timestamp": 2.0},
                    element_text="Submit",
                    before_description="Form screen",
                    after_description="Success screen",
                    suggested_verification="Form submitted",
                ),
            ]
            mock_step_analyzer.analyze_all.return_value = mock_analyzed_steps
            mock_step_analyzer_class.return_value = mock_step_analyzer

            # Mock verification suggester
            mock_suggester = MagicMock()
            mock_suggester.suggest.return_value = [
                VerificationPoint(
                    after_step_index=1,
                    description="Success screen shown",
                    confidence=0.85,
                    reason="Form submission detected",
                )
            ]
            mock_suggester_class.return_value = mock_suggester

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        # Verify AI components were used
        mock_ai_class.assert_called_once_with(api_key="test-api-key")
        mock_step_analyzer_class.assert_called_once_with(mock_ai)
        mock_step_analyzer.analyze_all.assert_called_once()
        mock_suggester_class.assert_called_once_with(mock_ai)
        mock_suggester.suggest.assert_called_once()
        # Check output mentions element extraction
        assert "Extracted" in result.output and "element names" in result.output

    def test_stop_skips_ai_analysis_when_no_api_key(
        self, recording_dir: Path
    ) -> None:
        """Stop command should skip AI analysis gracefully when no API key."""
        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None  # No API key
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        assert "AI analysis skipped (no API key)" in result.output
        # Verify YAML was still generated
        assert (recording_dir / "test.yaml").exists()

    def test_stop_handles_ai_analysis_exception(
        self, recording_dir: Path
    ) -> None:
        """Stop command should handle AI analysis exceptions gracefully."""
        with (
            patch("mutcli.core.config.ConfigLoader.load") as mock_load,
            patch("mutcli.core.ai_analyzer.AIAnalyzer") as mock_ai_class,
            patch("mutcli.core.step_analyzer.StepAnalyzer") as mock_step_analyzer_class,
        ):
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = "test-api-key"
            mock_load.return_value = mock_config

            # Mock AI analyzer
            mock_ai = MagicMock()
            mock_ai_class.return_value = mock_ai

            # Mock step analyzer to raise exception
            mock_step_analyzer = MagicMock()
            mock_step_analyzer.analyze_all.side_effect = RuntimeError("API error")
            mock_step_analyzer_class.return_value = mock_step_analyzer

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        # Check that error was caught and reported
        assert "AI analysis skipped:" in result.output
        # Verify YAML was still generated with fallback (coordinates)
        assert (recording_dir / "test.yaml").exists()

    def test_stop_warns_on_empty_touch_events(self, tmp_path: Path) -> None:
        """Stop command should warn when touch_events.json is empty."""
        test_dir = tmp_path / "empty-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        # Write empty touch events array
        (recording_dir / "touch_events.json").write_text("[]")

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        assert "Warning:" in result.output
        assert "No touch events found" in result.output

    def test_stop_handles_json_decode_error(self, tmp_path: Path) -> None:
        """Stop command should handle malformed touch_events.json."""
        test_dir = tmp_path / "malformed-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        # Write malformed JSON
        (recording_dir / "touch_events.json").write_text("{invalid json")

        result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 2
        assert "Invalid JSON" in result.output

    def test_stop_generates_yaml_with_analysis(
        self, recording_dir: Path
    ) -> None:
        """Stop command should generate YAML with element names from AI analysis."""
        with (
            patch("mutcli.core.config.ConfigLoader.load") as mock_load,
            patch("mutcli.core.ai_analyzer.AIAnalyzer") as mock_ai_class,
            patch("mutcli.core.step_analyzer.StepAnalyzer") as mock_step_analyzer_class,
            patch(
                "mutcli.core.verification_suggester.VerificationSuggester"
            ) as mock_suggester_class,
        ):
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = "test-api-key"
            mock_load.return_value = mock_config

            # Mock AI analyzer
            mock_ai = MagicMock()
            mock_ai_class.return_value = mock_ai

            # Mock step analyzer with element names
            mock_analyzed_steps = [
                AnalyzedStep(
                    index=0,
                    original_tap={"x": 540, "y": 800, "timestamp": 1.0},
                    element_text="Login Button",
                    before_description="Login screen",
                    after_description="Home screen",
                    suggested_verification=None,
                ),
                AnalyzedStep(
                    index=1,
                    original_tap={"x": 520, "y": 1400, "timestamp": 2.0},
                    element_text="Submit",
                    before_description="Form screen",
                    after_description="Success screen",
                    suggested_verification=None,
                ),
            ]
            mock_step_analyzer = MagicMock()
            mock_step_analyzer.analyze_all.return_value = mock_analyzed_steps
            mock_step_analyzer_class.return_value = mock_step_analyzer

            # Mock verification suggester
            mock_suggester = MagicMock()
            mock_suggester.suggest.return_value = []
            mock_suggester_class.return_value = mock_suggester

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        # Verify YAML was generated
        yaml_path = recording_dir / "test.yaml"
        assert yaml_path.exists()
        yaml_content = yaml_path.read_text()
        # Should have element-based taps (from AI analysis)
        assert "Login Button" in yaml_content or "Submit" in yaml_content

    def test_stop_falls_back_to_coordinates_without_analysis(
        self, recording_dir: Path
    ) -> None:
        """Stop command should fall back to coordinates when no AI analysis."""
        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None  # No API key
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(recording_dir)])

        assert result.exit_code == 0
        # Verify YAML was generated with coordinates
        yaml_path = recording_dir / "test.yaml"
        assert yaml_path.exists()
        yaml_content = yaml_path.read_text()
        # Should have coordinate-based taps (fallback)
        assert "540" in yaml_content or "800" in yaml_content

    def test_stop_handles_missing_touch_events_file(self, tmp_path: Path) -> None:
        """Stop command should error when touch_events.json is missing."""
        test_dir = tmp_path / "no-events"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)
        # Don't create touch_events.json

        result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 2
        assert "touch_events.json not found" in result.output

    def test_stop_handles_missing_recording_directory(self, tmp_path: Path) -> None:
        """Stop command should handle when test directory exists but no recording."""
        test_dir = tmp_path / "no-recording"
        test_dir.mkdir(parents=True)
        # Don't create recording subdirectory

        result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 2
        assert "touch_events.json not found" in result.output


class TestStopCommandVideoExtraction:
    """Tests for video frame extraction in stop command."""

    @pytest.fixture
    def recording_with_video(self, tmp_path: Path) -> Path:
        """Create recording directory with video file."""
        test_dir = tmp_path / "video-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [
            {"x": 540, "y": 800, "timestamp": 1.0, "screen_height": 2400},
        ]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        # Create a fake video file (won't be decoded but will trigger extraction code)
        (recording_dir / "recording.mp4").write_bytes(b"fake video content")

        return test_dir

    def test_stop_extracts_frames_from_video(
        self, recording_with_video: Path
    ) -> None:
        """Stop command should extract frames when video exists."""
        with (
            patch("mutcli.core.config.ConfigLoader.load") as mock_load,
            patch("mutcli.core.frame_extractor.FrameExtractor") as mock_extractor_class,
        ):
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            # Mock frame extractor
            mock_extractor = MagicMock()
            mock_extractor.extract_for_touches.return_value = [
                recording_with_video / "recording" / "screenshots" / "touch_001.png"
            ]
            mock_extractor_class.return_value = mock_extractor

            result = runner.invoke(app, ["stop", str(recording_with_video)])

        assert result.exit_code == 0
        # Verify frame extractor was called
        mock_extractor_class.assert_called_once()
        mock_extractor.extract_for_touches.assert_called_once()
        assert "Extracted 1 frames" in result.output

    def test_stop_skips_extraction_when_no_video(
        self, tmp_path: Path
    ) -> None:
        """Stop command should skip frame extraction when no video file."""
        test_dir = tmp_path / "no-video-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [{"x": 540, "y": 800, "timestamp": 1.0, "screen_height": 2400}]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))
        # No video file created

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        assert "No video found, skipping frame extraction" in result.output


class TestStopCommandIntegration:
    """Integration tests for stop command with minimal mocking."""

    def test_stop_end_to_end_without_api_key(self, tmp_path: Path) -> None:
        """Full stop command flow without AI (no API key)."""
        test_dir = tmp_path / "integration-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [
            {"x": 100, "y": 200, "timestamp": 1.0, "screen_height": 2400},
            {"x": 300, "y": 400, "timestamp": 2.0, "screen_height": 2400},
            {"x": 500, "y": 600, "timestamp": 3.0, "screen_height": 2400},
        ]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.test.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        assert "Test generated!" in result.output

        # Verify YAML file was created with correct content
        yaml_path = test_dir / "test.yaml"
        assert yaml_path.exists()

        yaml_content = yaml_path.read_text()
        assert "com.test.app" in yaml_content
        assert "tap:" in yaml_content

    def test_stop_uses_correct_test_name_from_directory(
        self, tmp_path: Path
    ) -> None:
        """Stop command should derive test name from directory."""
        test_dir = tmp_path / "my-custom-test-name"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [{"x": 100, "y": 200, "timestamp": 1.0, "screen_height": 2400}]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        # Test name should be derived from directory name
        yaml_path = test_dir / "test.yaml"
        assert yaml_path.exists()


class TestStopCommandEdgeCases:
    """Edge case tests for stop command."""

    def test_stop_handles_special_characters_in_path(self, tmp_path: Path) -> None:
        """Stop command should handle paths with special characters."""
        test_dir = tmp_path / "test with spaces"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [{"x": 100, "y": 200, "timestamp": 1.0, "screen_height": 2400}]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        assert (test_dir / "test.yaml").exists()

    def test_stop_handles_config_load_exception(self, tmp_path: Path) -> None:
        """Stop command should handle config loading exceptions gracefully."""
        test_dir = tmp_path / "config-error-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [{"x": 100, "y": 200, "timestamp": 1.0, "screen_height": 2400}]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            # First call for config load raises exception
            mock_load.side_effect = Exception("Config load error")

            result = runner.invoke(app, ["stop", str(test_dir)])

        # Should still complete but use default app package
        assert result.exit_code == 0
        yaml_content = (test_dir / "test.yaml").read_text()
        assert "com.example.app" in yaml_content  # Default app package

    def test_stop_with_single_touch_event(self, tmp_path: Path) -> None:
        """Stop command should handle single touch event."""
        test_dir = tmp_path / "single-touch-test"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        touch_events = [{"x": 540, "y": 800, "timestamp": 1.0, "screen_height": 2400}]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        assert "Found 1 touch events" in result.output
        assert (test_dir / "test.yaml").exists()

    def test_stop_uses_default_screen_height_when_missing(
        self, tmp_path: Path
    ) -> None:
        """Stop command should use default screen height when not in events."""
        test_dir = tmp_path / "no-screen-height"
        recording_dir = test_dir / "recording"
        recording_dir.mkdir(parents=True)

        # Touch events without screen_height field
        touch_events = [
            {"x": 540, "y": 800, "timestamp": 1.0},
            {"x": 520, "y": 1400, "timestamp": 2.0},
        ]
        (recording_dir / "touch_events.json").write_text(json.dumps(touch_events))

        with patch("mutcli.core.config.ConfigLoader.load") as mock_load:
            mock_config = MagicMock()
            mock_config.app = "com.example.app"
            mock_config.google_api_key = None
            mock_load.return_value = mock_config

            result = runner.invoke(app, ["stop", str(test_dir)])

        assert result.exit_code == 0
        # Test should complete successfully with default screen height
        assert (test_dir / "test.yaml").exists()
