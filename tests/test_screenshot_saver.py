"""Tests for screenshot saver utility."""
from pathlib import Path


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
