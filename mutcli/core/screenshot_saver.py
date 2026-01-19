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
