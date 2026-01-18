"""Tests for FrameExtractor."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from mutcli.core.frame_extractor import FrameExtractor
from mutcli.core.step_collapsing import CollapsedStep


class TestFrameExtractorInitialization:
    """Test FrameExtractor initialization."""

    def test_stores_video_path_as_path(self):
        """Should store video path as Path object."""
        extractor = FrameExtractor("/path/to/video.mp4")

        assert extractor._video_path == Path("/path/to/video.mp4")

    def test_accepts_path_object(self):
        """Should accept Path object as video path."""
        extractor = FrameExtractor(Path("/path/to/video.mp4"))

        assert extractor._video_path == Path("/path/to/video.mp4")

    def test_touch_offset_constant(self):
        """TOUCH_OFFSET should be 50ms (0.05s)."""
        assert FrameExtractor.TOUCH_OFFSET == 0.05

    def test_press_held_ratio_constant(self):
        """PRESS_HELD_RATIO should be 0.7 (70%)."""
        assert FrameExtractor.PRESS_HELD_RATIO == 0.7


class TestExtractFrame:
    """Test extract_frame method."""

    def test_returns_png_bytes(self, tmp_path):
        """extract_frame should return PNG bytes for valid timestamp."""
        png_data = b"\x89PNG\r\n\x1a\ntest_data"

        # Mock subprocess.run to succeed
        mock_result = MagicMock()
        mock_result.returncode = 0

        def run_side_effect(cmd, **kwargs):
            # Write PNG data to the temp file (last arg is output path)
            output_path = cmd[-1]
            Path(output_path).write_bytes(png_data)
            return mock_result

        with patch("mutcli.core.frame_extractor.subprocess.run", side_effect=run_side_effect):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.5)

        assert result is not None
        assert result.startswith(b"\x89PNG")

    def test_returns_none_on_file_not_found(self):
        """extract_frame should return None if ffmpeg fails with file not found."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"No such file or directory"

        with patch("mutcli.core.frame_extractor.subprocess.run", return_value=mock_result):
            extractor = FrameExtractor("/nonexistent/video.mp4")
            result = extractor.extract_frame(1.0)

        assert result is None

    def test_returns_none_on_extraction_error(self):
        """extract_frame should return None on extraction error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"Extraction failed"

        with patch("mutcli.core.frame_extractor.subprocess.run", return_value=mock_result):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.0)

        assert result is None

    def test_returns_none_on_timeout(self):
        """extract_frame should return None when ffmpeg times out."""
        with patch(
            "mutcli.core.frame_extractor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30),
        ):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.5)

        assert result is None

    def test_clamps_negative_timestamp(self, tmp_path):
        """extract_frame should clamp negative timestamps to 0."""
        png_data = b"\x89PNG\r\n\x1a\n"
        mock_result = MagicMock()
        mock_result.returncode = 0

        captured_cmd = []

        def run_side_effect(cmd, **kwargs):
            captured_cmd.clear()
            captured_cmd.extend(cmd)
            output_path = cmd[-1]
            Path(output_path).write_bytes(png_data)
            return mock_result

        with patch("mutcli.core.frame_extractor.subprocess.run", side_effect=run_side_effect):
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_frame(-1.0)

        # Should clamp to 0.000
        assert "-ss" in captured_cmd
        ss_idx = captured_cmd.index("-ss")
        assert captured_cmd[ss_idx + 1] == "0.000"


class TestCalculateFrameTimes:
    """Test _calculate_frame_times method for midpoint calculation."""

    def test_single_tap_frame_times(self):
        """Single tap should use video boundaries for midpoints."""
        extractor = FrameExtractor("/path/to/video.mp4")
        touch_events = [
            {"timestamp": 2.0, "gesture": "tap", "duration_ms": 100}
        ]
        video_duration = 5.0

        result = extractor._calculate_frame_times(touch_events, video_duration)

        assert len(result) == 1
        ft = result[0]
        assert ft["step_num"] == 1
        assert ft["gesture"] == "tap"
        # before: midpoint(0.0, 1.9) = 0.95 (touch_start = 2.0 - 0.1)
        assert ft["before_time"] == 0.95
        # touch: touch_start - 50ms = 1.9 - 0.05 = 1.85
        assert abs(ft["touch_time"] - 1.85) < 0.001  # Float precision tolerance
        # after: midpoint(2.0, 5.0) = 3.5
        assert ft["after_time"] == 3.5

    def test_two_taps_midpoint_calculation(self):
        """Two taps should use midpoint between them."""
        extractor = FrameExtractor("/path/to/video.mp4")
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 100},  # start=0.9
            {"timestamp": 3.0, "gesture": "tap", "duration_ms": 100},  # start=2.9
        ]
        video_duration = 5.0

        result = extractor._calculate_frame_times(touch_events, video_duration)

        assert len(result) == 2

        # First tap
        ft1 = result[0]
        # before: midpoint(0.0, 0.9) = 0.45
        assert ft1["before_time"] == 0.45
        # after: midpoint(1.0, 2.9) = 1.95
        assert ft1["after_time"] == 1.95

        # Second tap
        ft2 = result[1]
        # before: midpoint(1.0, 2.9) = 1.95
        assert ft2["before_time"] == 1.95
        # after: midpoint(3.0, 5.0) = 4.0
        assert ft2["after_time"] == 4.0

    def test_swipe_frame_times(self):
        """Swipe should have swipe_start and swipe_end times."""
        extractor = FrameExtractor("/path/to/video.mp4")
        touch_events = [
            {"timestamp": 2.0, "gesture": "swipe", "duration_ms": 500}  # start=1.5
        ]
        video_duration = 5.0

        result = extractor._calculate_frame_times(touch_events, video_duration)

        ft = result[0]
        assert ft["gesture"] == "swipe"
        assert "swipe_start_time" in ft
        assert "swipe_end_time" in ft
        assert ft["swipe_start_time"] == 1.5  # touch_start
        assert ft["swipe_end_time"] == 1.95  # touch_end - 50ms

    def test_long_press_frame_times(self):
        """Long press should have press_start and press_held times."""
        extractor = FrameExtractor("/path/to/video.mp4")
        touch_events = [
            {"timestamp": 2.0, "gesture": "long_press", "duration_ms": 1000}  # start=1.0
        ]
        video_duration = 5.0

        result = extractor._calculate_frame_times(touch_events, video_duration)

        ft = result[0]
        assert ft["gesture"] == "long_press"
        assert "press_start_time" in ft
        assert "press_held_time" in ft
        assert ft["press_start_time"] == 1.0  # touch_start
        # press_held: start + duration * 0.7 = 1.0 + 1.0 * 0.7 = 1.7
        assert ft["press_held_time"] == 1.7

    def test_defaults_for_missing_fields(self):
        """Should use defaults for missing gesture and duration_ms."""
        extractor = FrameExtractor("/path/to/video.mp4")
        touch_events = [{"timestamp": 2.0}]  # No gesture or duration_ms
        video_duration = 5.0

        result = extractor._calculate_frame_times(touch_events, video_duration)

        ft = result[0]
        assert ft["gesture"] == "tap"
        # duration defaults to 50ms, so start = 2.0 - 0.05 = 1.95
        assert ft["touch_time"] == 1.9  # 1.95 - 0.05 = 1.9


class TestExtractForTouches:
    """Test extract_for_touches method."""

    def test_creates_output_directory(self, tmp_path):
        """extract_for_touches should create output directory if not exists."""
        output_dir = tmp_path / "screenshots"

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG"), \
             patch.object(FrameExtractor, "get_duration", return_value=10.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_touches(
                [{"timestamp": 1.0, "gesture": "tap", "duration_ms": 50}],
                output_dir,
            )

        assert output_dir.exists()

    def test_tap_extracts_three_frames(self, tmp_path):
        """Tap should extract before, touch, after (3 frames)."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 2.0, "gesture": "tap", "duration_ms": 100}
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            # Return all requested paths (simulating successful extraction)
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        assert len(paths) == 3
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_touch.png" in path_names
        assert "step_001_after.png" in path_names

    def test_swipe_extracts_four_frames(self, tmp_path):
        """Swipe should extract before, swipe_start, swipe_end, after (4 frames)."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 2.0, "gesture": "swipe", "duration_ms": 500}
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        assert len(paths) == 4
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_swipe_start.png" in path_names
        assert "step_001_swipe_end.png" in path_names
        assert "step_001_after.png" in path_names

    def test_long_press_extracts_four_frames(self, tmp_path):
        """Long press should extract before, press_start, press_held, after (4 frames)."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 2.0, "gesture": "long_press", "duration_ms": 1000}
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        assert len(paths) == 4
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_press_start.png" in path_names
        assert "step_001_press_held.png" in path_names
        assert "step_001_after.png" in path_names

    def test_multiple_gestures_numbering(self, tmp_path):
        """Multiple gestures should be numbered correctly."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 2.0, "gesture": "swipe", "duration_ms": 300},
            {"timestamp": 3.0, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        # 3 tap + 4 swipe + 3 tap = 10
        assert len(paths) == 10

        # Check step numbering
        step_001_files = [p for p in paths if "step_001" in p.name]
        step_002_files = [p for p in paths if "step_002" in p.name]
        step_003_files = [p for p in paths if "step_003" in p.name]

        assert len(step_001_files) == 3  # tap
        assert len(step_002_files) == 4  # swipe
        assert len(step_003_files) == 3  # tap

    def test_returns_list_of_paths(self, tmp_path):
        """Should return list of Path objects for created files."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
        ]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG"), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_for_touches(touch_events, output_dir)

        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)

    def test_skips_failed_extractions(self, tmp_path):
        """Should skip frames when extraction fails."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            # Skip the touch frame (index 1)
            return [path for i, (_, path) in enumerate(extractions) if i != 1]

        with patch.object(
            FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract
        ), patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        # Should have before and after, but not touch
        assert len(paths) == 2
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_after.png" in path_names

    def test_empty_touch_events(self, tmp_path):
        """Should return empty list for empty touch events."""
        output_dir = tmp_path / "screenshots"

        extractor = FrameExtractor("/path/to/video.mp4")
        result = extractor.extract_for_touches([], output_dir)

        assert result == []
        assert output_dir.exists()

    def test_files_contain_png_data(self, tmp_path):
        """Extracted files should contain PNG data."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
        ]

        png_data = b"\x89PNG\r\n\x1a\ntest_data"

        with patch.object(FrameExtractor, "extract_frame", return_value=png_data), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        for path in paths:
            assert path.exists()
            assert path.read_bytes() == png_data


class TestGetDuration:
    """Test get_duration method using ffprobe."""

    def test_returns_duration_from_ffprobe(self):
        """Should return duration from ffprobe output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5.0\n"

        with patch("mutcli.core.frame_extractor.subprocess.run", return_value=mock_result):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.get_duration()

        assert result == 5.0

    def test_returns_zero_on_error(self):
        """Should return 0.0 on ffprobe error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("mutcli.core.frame_extractor.subprocess.run", return_value=mock_result):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.get_duration()

        assert result == 0.0

    def test_returns_zero_on_timeout(self):
        """Should return 0.0 if ffprobe times out."""
        with patch(
            "mutcli.core.frame_extractor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
        ):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.get_duration()

        assert result == 0.0

    def test_returns_zero_on_parse_error(self):
        """Should return 0.0 if duration cannot be parsed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not_a_number\n"

        with patch("mutcli.core.frame_extractor.subprocess.run", return_value=mock_result):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.get_duration()

        assert result == 0.0


class TestCalculateCollapsedFrameTimes:
    """Test _calculate_collapsed_frame_times method."""

    def test_single_type_step_frame_times(self):
        """Type step should only have before and after times."""
        extractor = FrameExtractor("/path/to/video.mp4")

        # Type step spanning 3 taps (indices 0, 1, 2)
        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="type",
                timestamp=1.0,
                original_indices=(0, 2),
                tap_count=3,
                text="abc",
            )
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.2, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.4, "gesture": "tap", "duration_ms": 50},
        ]
        video_duration = 5.0

        result = extractor._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        assert len(result) == 1
        ft = result[0]
        assert ft["step_num"] == 1
        assert ft["action"] == "type"
        # before: midpoint(0.0, 0.95) = 0.475 (first_start = 1.0 - 0.05)
        assert abs(ft["before_time"] - 0.475) < 0.001
        # after: midpoint(1.4, 5.0) = 3.2 (last_end = 1.4)
        assert ft["after_time"] == 3.2
        # Type should NOT have touch_time
        assert "touch_time" not in ft

    def test_tap_step_has_touch_time(self):
        """Tap step should have touch_time."""
        extractor = FrameExtractor("/path/to/video.mp4")

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="tap",
                timestamp=2.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "tap", "duration_ms": 100},
        ]
        video_duration = 5.0

        result = extractor._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        ft = result[0]
        assert ft["action"] == "tap"
        assert "touch_time" in ft
        # touch_time: first_start - 0.05 = 1.9 - 0.05 = 1.85
        assert abs(ft["touch_time"] - 1.85) < 0.001

    def test_type_followed_by_tap(self):
        """Type step followed by tap should calculate midpoints correctly."""
        extractor = FrameExtractor("/path/to/video.mp4")

        # Type (indices 0-2), then tap (index 3)
        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="type",
                timestamp=1.0,
                original_indices=(0, 2),
                tap_count=3,
                text="abc",
            ),
            CollapsedStep(
                index=2,
                action="tap",
                timestamp=3.0,
                original_indices=(3, 3),
                coordinates={"x": 100, "y": 200},
            ),
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.2, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.4, "gesture": "tap", "duration_ms": 50},  # end of type
            {"timestamp": 3.0, "gesture": "tap", "duration_ms": 100},  # tap
        ]
        video_duration = 5.0

        result = extractor._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        assert len(result) == 2

        # First step (type)
        ft1 = result[0]
        assert ft1["action"] == "type"
        # after: midpoint(1.4, 2.9) = 2.15 (tap start = 3.0 - 0.1)
        assert abs(ft1["after_time"] - 2.15) < 0.001

        # Second step (tap)
        ft2 = result[1]
        assert ft2["action"] == "tap"
        # before: midpoint(1.4, 2.9) = 2.15
        assert abs(ft2["before_time"] - 2.15) < 0.001

    def test_swipe_step_has_swipe_times(self):
        """Swipe step should have swipe_start_time and swipe_end_time."""
        extractor = FrameExtractor("/path/to/video.mp4")

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="swipe",
                timestamp=2.0,
                original_indices=(0, 0),
                start={"x": 100, "y": 200},
                end={"x": 100, "y": 500},
                direction="down",
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "swipe", "duration_ms": 500},
        ]
        video_duration = 5.0

        result = extractor._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        ft = result[0]
        assert ft["action"] == "swipe"
        assert "swipe_start_time" in ft
        assert "swipe_end_time" in ft
        # swipe_start = first_start = 2.0 - 0.5 = 1.5
        assert ft["swipe_start_time"] == 1.5
        # swipe_end = last_end - 0.05 = 2.0 - 0.05 = 1.95
        assert ft["swipe_end_time"] == 1.95

    def test_long_press_step_has_press_times(self):
        """Long press step should have press_start_time and press_held_time."""
        extractor = FrameExtractor("/path/to/video.mp4")

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="long_press",
                timestamp=2.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
                duration_ms=1000,
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "long_press", "duration_ms": 1000},
        ]
        video_duration = 5.0

        result = extractor._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        ft = result[0]
        assert ft["action"] == "long_press"
        assert "press_start_time" in ft
        assert "press_held_time" in ft
        # press_start = first_start = 2.0 - 1.0 = 1.0
        assert ft["press_start_time"] == 1.0
        # press_held: start + duration * 0.7 = 1.0 + 1.0 * 0.7 = 1.7
        assert ft["press_held_time"] == 1.7


class TestExtractForCollapsedSteps:
    """Test extract_for_collapsed_steps method."""

    def test_type_extracts_two_frames(self, tmp_path):
        """Type action should extract before and after (2 frames), no touch."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="type",
                timestamp=1.0,
                original_indices=(0, 2),
                tap_count=3,
                text="abc",
            )
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.2, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.4, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        assert len(paths) == 2
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_after.png" in path_names

    def test_tap_extracts_three_frames(self, tmp_path):
        """Tap action should extract before, touch, after (3 frames)."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="tap",
                timestamp=2.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "tap", "duration_ms": 100},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        assert len(paths) == 3
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_touch.png" in path_names
        assert "step_001_after.png" in path_names

    def test_swipe_extracts_four_frames(self, tmp_path):
        """Swipe action should extract before, swipe_start, swipe_end, after."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="swipe",
                timestamp=2.0,
                original_indices=(0, 0),
                start={"x": 100, "y": 200},
                end={"x": 100, "y": 500},
                direction="down",
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "swipe", "duration_ms": 500},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        assert len(paths) == 4
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_swipe_start.png" in path_names
        assert "step_001_swipe_end.png" in path_names
        assert "step_001_after.png" in path_names

    def test_long_press_extracts_four_frames(self, tmp_path):
        """Long press should extract before, press_start, press_held, after."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="long_press",
                timestamp=2.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
                duration_ms=1000,
            )
        ]
        touch_events = [
            {"timestamp": 2.0, "gesture": "long_press", "duration_ms": 1000},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        assert len(paths) == 4
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_press_start.png" in path_names
        assert "step_001_press_held.png" in path_names
        assert "step_001_after.png" in path_names

    def test_type_then_tap_correct_frame_count(self, tmp_path):
        """Type followed by tap should have 2 + 3 = 5 frames."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="type",
                timestamp=1.0,
                original_indices=(0, 2),
                tap_count=3,
                text="abc",
            ),
            CollapsedStep(
                index=2,
                action="tap",
                timestamp=3.0,
                original_indices=(3, 3),
                coordinates={"x": 100, "y": 200},
            ),
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.2, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.4, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 3.0, "gesture": "tap", "duration_ms": 100},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        # type: 2 frames (before, after) + tap: 3 frames (before, touch, after)
        assert len(paths) == 5

        step_001_files = [p for p in paths if "step_001" in p.name]
        step_002_files = [p for p in paths if "step_002" in p.name]

        assert len(step_001_files) == 2  # type
        assert len(step_002_files) == 3  # tap

    def test_empty_collapsed_steps_returns_empty(self, tmp_path):
        """Should return empty list for empty collapsed steps."""
        output_dir = tmp_path / "screenshots"

        extractor = FrameExtractor("/path/to/video.mp4")
        result = extractor.extract_for_collapsed_steps([], [], output_dir)

        assert result == []

    def test_empty_touch_events_returns_empty(self, tmp_path):
        """Should return empty list when touch_events is empty."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="tap",
                timestamp=1.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
            )
        ]

        extractor = FrameExtractor("/path/to/video.mp4")
        result = extractor.extract_for_collapsed_steps(
            collapsed_steps, [], output_dir
        )

        assert result == []

    def test_creates_output_directory(self, tmp_path):
        """Should create output directory if not exists."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="type",
                timestamp=1.0,
                original_indices=(0, 0),
                tap_count=1,
                text="a",
            )
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        assert output_dir.exists()

    def test_skips_failed_extractions(self, tmp_path):
        """Should skip frames when extraction fails."""
        output_dir = tmp_path / "screenshots"

        collapsed_steps = [
            CollapsedStep(
                index=1,
                action="tap",
                timestamp=1.0,
                original_indices=(0, 0),
                coordinates={"x": 100, "y": 200},
            )
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            # Skip the touch frame (index 1)
            return [path for i, (_, path) in enumerate(extractions) if i != 1]

        with patch.object(
            FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract
        ), patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        # Should have before and after, but not touch
        assert len(paths) == 2
        path_names = [p.name for p in paths]
        assert "step_001_before.png" in path_names
        assert "step_001_after.png" in path_names

    def test_uses_step_index_for_numbering(self, tmp_path):
        """Should use step.index for file naming, not sequential counter."""
        output_dir = tmp_path / "screenshots"

        # Steps with non-sequential indices (could happen with filtering)
        collapsed_steps = [
            CollapsedStep(
                index=3,  # Non-sequential index
                action="type",
                timestamp=1.0,
                original_indices=(0, 1),
                tap_count=2,
                text="ab",
            )
        ]
        touch_events = [
            {"timestamp": 1.0, "gesture": "tap", "duration_ms": 50},
            {"timestamp": 1.2, "gesture": "tap", "duration_ms": 50},
        ]

        def mock_parallel_extract(extractions, max_workers=None):
            return [path for _, path in extractions]

        with patch.object(FrameExtractor, "_extract_frames_parallel", side_effect=mock_parallel_extract), \
             patch.object(FrameExtractor, "get_duration", return_value=5.0):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_collapsed_steps(
                collapsed_steps, touch_events, output_dir
            )

        # Should use step index 3 in filenames
        path_names = [p.name for p in paths]
        assert "step_003_before.png" in path_names
        assert "step_003_after.png" in path_names
