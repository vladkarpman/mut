"""Video frame extraction using PyAV."""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import av

logger = logging.getLogger("mut.frame_extractor")


class FrameExtractor:
    """Extract frames from recorded video at specific timestamps.

    Uses PyAV for efficient video seeking and frame extraction.
    Designed to extract frames 100ms before touch events to capture
    the UI state at the moment of tap decision.

    Usage:
        extractor = FrameExtractor("/path/to/video.mp4")
        frame_data = extractor.extract_frame(1.5)  # PNG bytes at 1.5s

        # Or extract for all touch events
        paths = extractor.extract_for_touches(touch_events, output_dir)
    """

    BEFORE_OFFSET_MS = 100  # Extract frame 100ms before touch

    def __init__(self, video_path: str | Path):
        """Initialize with video file path.

        Args:
            video_path: Path to the video file
        """
        self._video_path = Path(video_path)

    def extract_frame(self, timestamp_sec: float) -> bytes | None:
        """Extract single frame at timestamp as PNG bytes.

        Args:
            timestamp_sec: Timestamp in seconds

        Returns:
            PNG image bytes, or None on error
        """
        try:
            with av.open(str(self._video_path)) as container:
                stream = container.streams.video[0]

                # Calculate pts for seek
                time_base = stream.time_base or 1
                target_pts = int(timestamp_sec / float(time_base))
                container.seek(target_pts, stream=stream)

                # Get first frame after seek
                for frame in container.decode(video=0):
                    img = frame.to_image()

                    # Convert to PNG bytes
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    return buffer.getvalue()

                # No frames decoded
                logger.warning(f"No frames found at timestamp {timestamp_sec}s")
                return None

        except FileNotFoundError:
            logger.error(f"Video file not found: {self._video_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract frame at {timestamp_sec}s: {e}")
            return None

    def extract_for_touches(
        self,
        touch_events: list[dict[str, Any]],
        output_dir: Path,
    ) -> list[Path]:
        """Extract frames 100ms before each touch event.

        Args:
            touch_events: List of dicts with 'timestamp' field (seconds)
            output_dir: Directory to save frames as touch_001.png, touch_002.png, etc.

        Returns:
            List of paths to extracted frame files (only successful extractions)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if not touch_events:
            return []

        extracted_paths: list[Path] = []
        offset_sec = self.BEFORE_OFFSET_MS / 1000.0

        for idx, event in enumerate(touch_events, start=1):
            timestamp = event.get("timestamp", 0.0)

            # Calculate extraction timestamp (100ms before touch)
            extract_at = max(0.0, timestamp - offset_sec)

            # Extract frame
            frame_data = self.extract_frame(extract_at)

            if frame_data is None:
                logger.warning(f"Skipping touch {idx}: extraction failed")
                continue

            # Save to file
            filename = f"touch_{idx:03d}.png"
            file_path = output_dir / filename

            with open(file_path, "wb") as f:
                f.write(frame_data)

            extracted_paths.append(file_path)
            logger.debug(f"Extracted frame for touch {idx} at {extract_at:.3f}s")

        logger.info(
            f"Extracted {len(extracted_paths)}/{len(touch_events)} frames to {output_dir}"
        )

        return extracted_paths
