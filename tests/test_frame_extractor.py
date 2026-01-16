"""Tests for FrameExtractor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from mutcli.core.frame_extractor import FrameExtractor


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

    def test_before_offset_constant(self):
        """BEFORE_OFFSET_MS should be 100ms."""
        assert FrameExtractor.BEFORE_OFFSET_MS == 100


class TestExtractFrame:
    """Test extract_frame method."""

    def test_returns_png_bytes(self):
        """extract_frame should return PNG bytes for valid timestamp."""
        mock_frame = MagicMock()
        mock_image = MagicMock()
        mock_frame.to_image.return_value = mock_image

        # Mock PIL Image save to BytesIO
        def save_png(buffer, format):
            buffer.write(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes

        mock_image.save.side_effect = save_png

        mock_stream = MagicMock()
        mock_stream.time_base = 0.001  # 1ms time base

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.return_value = iter([mock_frame])

        with patch("av.open") as mock_av_open:
            mock_av_open.return_value.__enter__.return_value = mock_container

            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.5)

        assert result is not None
        assert result.startswith(b"\x89PNG")

    def test_returns_none_on_file_not_found(self):
        """extract_frame should return None if video file not found."""
        with patch("av.open") as mock_av_open:
            mock_av_open.side_effect = FileNotFoundError("Video not found")

            extractor = FrameExtractor("/nonexistent/video.mp4")
            result = extractor.extract_frame(1.0)

        assert result is None

    def test_returns_none_on_extraction_error(self):
        """extract_frame should return None on extraction error."""
        with patch("av.open") as mock_av_open:
            mock_av_open.side_effect = Exception("Extraction failed")

            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.0)

        assert result is None

    def test_returns_none_when_no_frames(self):
        """extract_frame should return None when no frames decoded."""
        mock_stream = MagicMock()
        mock_stream.time_base = 0.001

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.return_value = iter([])  # No frames

        with patch("av.open") as mock_av_open:
            mock_av_open.return_value.__enter__.return_value = mock_container

            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_frame(1.5)

        assert result is None

    def test_seeks_to_correct_timestamp(self):
        """extract_frame should seek to the correct timestamp."""
        mock_frame = MagicMock()
        mock_image = MagicMock()
        mock_frame.to_image.return_value = mock_image
        mock_image.save.side_effect = lambda buf, fmt: buf.write(b"\x89PNG")

        mock_stream = MagicMock()
        mock_stream.time_base = 0.001  # 1ms time base, so 1s = 1000 pts

        mock_container = MagicMock()
        mock_container.streams.video = [mock_stream]
        mock_container.decode.return_value = iter([mock_frame])

        with patch("av.open") as mock_av_open:
            mock_av_open.return_value.__enter__.return_value = mock_container

            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_frame(2.5)

        # 2.5 seconds / 0.001 time_base = 2500 pts
        mock_container.seek.assert_called_once_with(2500, stream=mock_stream)


class TestExtractForTouches:
    """Test extract_for_touches method."""

    def test_creates_output_directory(self, tmp_path):
        """extract_for_touches should create output directory if not exists."""
        output_dir = tmp_path / "screenshots"

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG"):
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_touches(
                [{"timestamp": 1.0}],
                output_dir,
            )

        assert output_dir.exists()

    def test_extracts_100ms_before_each_touch(self, tmp_path):
        """Should extract frames 100ms before each touch timestamp."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0},  # Should extract at 0.9s
            {"timestamp": 2.5},  # Should extract at 2.4s
        ]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG") as mock_extract:
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_touches(touch_events, output_dir)

            # Called with timestamps - 100ms
            calls = [call.args[0] for call in mock_extract.call_args_list]
            assert calls == [0.9, 2.4]

    def test_saves_files_with_correct_names(self, tmp_path):
        """Should save frames as touch_001.png, touch_002.png, etc."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0},
            {"timestamp": 2.0},
            {"timestamp": 3.0},
        ]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG"):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        assert len(paths) == 3
        assert paths[0] == output_dir / "touch_001.png"
        assert paths[1] == output_dir / "touch_002.png"
        assert paths[2] == output_dir / "touch_003.png"

        # Verify files exist
        for path in paths:
            assert path.exists()

    def test_handles_timestamp_less_than_offset(self, tmp_path):
        """Should use 0 when timestamp < 100ms offset."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 0.05},  # 50ms - should use 0
            {"timestamp": 0.08},  # 80ms - should use 0
        ]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG") as mock_extract:
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_touches(touch_events, output_dir)

            calls = [call.args[0] for call in mock_extract.call_args_list]
            assert calls == [0.0, 0.0]

    def test_returns_list_of_paths(self, tmp_path):
        """Should return list of Path objects for created files."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0},
            {"timestamp": 2.0},
        ]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG"):
            extractor = FrameExtractor("/path/to/video.mp4")
            result = extractor.extract_for_touches(touch_events, output_dir)

        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)

    def test_skips_failed_extractions(self, tmp_path):
        """Should skip and not create file when extraction returns None."""
        output_dir = tmp_path / "screenshots"
        touch_events = [
            {"timestamp": 1.0},
            {"timestamp": 2.0},
            {"timestamp": 3.0},
        ]

        # Second extraction fails
        def extract_side_effect(timestamp):
            if timestamp == 1.9:  # 2.0 - 0.1
                return None
            return b"\x89PNG"

        with patch.object(
            FrameExtractor, "extract_frame", side_effect=extract_side_effect
        ):
            extractor = FrameExtractor("/path/to/video.mp4")
            paths = extractor.extract_for_touches(touch_events, output_dir)

        # Should still number correctly and only return successful paths
        assert len(paths) == 2
        assert paths[0] == output_dir / "touch_001.png"
        assert paths[1] == output_dir / "touch_003.png"

        # Failed file should not exist
        assert not (output_dir / "touch_002.png").exists()

    def test_empty_touch_events(self, tmp_path):
        """Should return empty list for empty touch events."""
        output_dir = tmp_path / "screenshots"

        extractor = FrameExtractor("/path/to/video.mp4")
        result = extractor.extract_for_touches([], output_dir)

        assert result == []
        assert output_dir.exists()

    def test_handles_negative_timestamp_after_offset(self, tmp_path):
        """Should handle edge case of 0 timestamp."""
        output_dir = tmp_path / "screenshots"
        touch_events = [{"timestamp": 0.0}]

        with patch.object(FrameExtractor, "extract_frame", return_value=b"\x89PNG") as mock_extract:
            extractor = FrameExtractor("/path/to/video.mp4")
            extractor.extract_for_touches(touch_events, output_dir)

            calls = [call.args[0] for call in mock_extract.call_args_list]
            assert calls == [0.0]
