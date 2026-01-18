"""Video frame extraction using ffmpeg."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mutcli.core.step_collapsing import CollapsedStep

logger = logging.getLogger("mut.frame_extractor")


class FrameExtractor:
    """Extract frames from recorded video at specific timestamps.

    Uses ffmpeg for reliable video seeking and frame extraction.
    Uses midpoint approach for non-overlapping time ranges.
    Uses frame timestamps file for accurate wall-clock time mapping.
    Supports parallel extraction for performance.

    Frame extraction by gesture type:
    - tap: before, touch, after (3 frames)
    - swipe: before, swipe_start, swipe_end, after (4 frames)
    - long_press: before, press_start, press_held, after (4 frames)

    Usage:
        extractor = FrameExtractor("/path/to/video.mp4")
        frame_data = extractor.extract_frame(1.5)  # PNG bytes at 1.5s

        # Or extract for all touch events
        paths = extractor.extract_for_touches(touch_events, output_dir)
    """

    # Timing offsets
    TOUCH_OFFSET = 0.05  # 50ms before touch for "touch" frame
    PRESS_HELD_RATIO = 0.7  # Show press at 70% of duration for long_press

    def __init__(self, video_path: str | Path):
        """Initialize with video file path.

        Args:
            video_path: Path to the video file
        """
        self._video_path = Path(video_path)
        self._frame_timestamps: list[float] | None = None
        self._load_timestamps()

    def _load_timestamps(self) -> None:
        """Load frame timestamps from companion JSON file if it exists."""
        import json
        timestamps_path = self._video_path.with_suffix(".timestamps.json")
        if timestamps_path.exists():
            try:
                with open(timestamps_path) as f:
                    self._frame_timestamps = json.load(f)
                logger.info(f"Loaded {len(self._frame_timestamps)} frame timestamps")
            except Exception as e:
                logger.warning(f"Failed to load timestamps: {e}")
                self._frame_timestamps = None

    def _find_frame_index(self, target_time: float) -> int:
        """Find frame index closest to target wall-clock time.

        Uses binary search on frame timestamps.

        Args:
            target_time: Target time in seconds

        Returns:
            Frame index (0-based)
        """
        if not self._frame_timestamps:
            # Fallback: assume 30fps
            return int(target_time * 30)

        import bisect
        idx = bisect.bisect_left(self._frame_timestamps, target_time)

        # Return closest frame (check both idx-1 and idx)
        if idx == 0:
            return 0
        if idx >= len(self._frame_timestamps):
            return len(self._frame_timestamps) - 1

        # Choose the closer one
        if (target_time - self._frame_timestamps[idx - 1] <
                self._frame_timestamps[idx] - target_time):
            return idx - 1
        return idx

    def _get_actual_duration(self) -> float:
        """Get actual recording duration from timestamps, with fallback to video.

        When timestamps file exists, returns the last frame's wall-clock time.
        This is more accurate than video duration which is based on frame count.

        Returns:
            Duration in seconds
        """
        if self._frame_timestamps:
            return self._frame_timestamps[-1]
        return self.get_duration()

    def get_duration(self) -> float:
        """Get video duration in seconds using ffprobe.

        Returns:
            Duration in seconds, or 0.0 on error
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(self._video_path),
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except subprocess.TimeoutExpired:
            logger.error("ffprobe timed out getting video duration")
        except ValueError as e:
            logger.error(f"Failed to parse video duration: {e}")
        except Exception as e:
            logger.error(f"Failed to get video duration: {e}")

        return 0.0

    def extract_frame(self, timestamp_sec: float) -> bytes | None:
        """Extract single frame at timestamp as PNG bytes using ffmpeg.

        Args:
            timestamp_sec: Timestamp in seconds (video-relative time)

        Returns:
            PNG image bytes, or None on error
        """
        # Clamp timestamp to valid range
        timestamp_sec = max(0.0, timestamp_sec)

        # Create temp file for output
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        try:
            cmd = [
                "ffmpeg",
                "-ss", f"{timestamp_sec:.3f}",  # Seek BEFORE input (fast)
                "-i", str(self._video_path),
                "-frames:v", "1",
                "-q:v", "2",  # High quality
                "-y",  # Overwrite
                "-loglevel", "error",
                tmp_path,
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=30)

            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else "Unknown error"
                logger.warning(f"ffmpeg failed for {timestamp_sec}s: {stderr}")
                return None

            # Read PNG data
            with open(tmp_path, "rb") as f:
                data = f.read()

            return data if data else None

        except FileNotFoundError:
            logger.error(f"Video file not found: {self._video_path}")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timed out at {timestamp_sec}s")
            return None
        except Exception as e:
            logger.error(f"Failed to extract frame at {timestamp_sec}s: {e}")
            return None
        finally:
            # Clean up temp file
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _calculate_frame_times(
        self,
        touch_events: list[dict[str, Any]],
        video_duration: float,
    ) -> list[dict[str, Any]]:
        """Calculate frame extraction times using midpoint approach.

        Uses midpoints between consecutive gestures to ensure no overlap.
        Frame times vary by gesture type:

        - tap: before, touch, after (3 frames)
        - swipe/scroll: before, swipe_start, swipe_end, after (4 frames)
        - long_press: before, press_start, press_held, after (4 frames)

        Args:
            touch_events: List of touch event dicts with 'timestamp', 'gesture', 'duration_ms'
            video_duration: Video duration in seconds

        Returns:
            List of dicts with step_num, gesture, and frame times
        """
        frame_times = []
        n = len(touch_events)

        for i, event in enumerate(touch_events):
            touch_end_time = event.get("timestamp", 0.0)
            gesture = event.get("gesture", "tap")
            duration_ms = event.get("duration_ms", 50)
            duration_sec = duration_ms / 1000.0

            # Touch start time = end time - duration
            touch_start_time = touch_end_time - duration_sec

            # Before: midpoint between previous gesture end and this gesture start
            if i == 0:
                prev_end_time = 0.0  # Video start
            else:
                prev_end_time = touch_events[i - 1].get("timestamp", 0.0)
            before_time = (prev_end_time + touch_start_time) / 2

            # After: midpoint between this gesture end and next gesture start
            if i == n - 1:
                next_start_time = video_duration  # Video end
            else:
                next_event = touch_events[i + 1]
                next_end = next_event.get("timestamp", 0.0)
                next_duration = next_event.get("duration_ms", 50) / 1000.0
                next_start_time = next_end - next_duration
            after_time = (touch_end_time + next_start_time) / 2

            # Build frame times based on gesture type
            ft: dict[str, Any] = {
                "step_num": i + 1,
                "gesture": gesture,
                "before_time": before_time,
                "after_time": after_time,
            }

            if gesture == "tap":
                # tap: show target button just before touch
                ft["touch_time"] = max(0.0, touch_start_time - self.TOUCH_OFFSET)

            elif gesture == "swipe":
                # swipe: show start position and end position
                ft["swipe_start_time"] = touch_start_time
                ft["swipe_end_time"] = max(touch_start_time, touch_end_time - 0.05)

            elif gesture == "long_press":
                # long_press: show press start and held state
                ft["press_start_time"] = touch_start_time
                # Show press at 70% of duration (finger still held)
                held_time = touch_start_time + (duration_sec * self.PRESS_HELD_RATIO)
                ft["press_held_time"] = held_time

            else:
                # Unknown gesture - treat as tap
                ft["touch_time"] = max(0.0, touch_start_time - self.TOUCH_OFFSET)

            frame_times.append(ft)

        return frame_times

    def _extract_and_save(
        self,
        timestamp: float,
        output_path: Path,
        step_num: int,
        frame_name: str,
    ) -> Path | None:
        """Extract a frame and save it to disk.

        Args:
            timestamp: Video timestamp in seconds
            output_path: Path to save the frame
            step_num: Step number for logging
            frame_name: Frame name for logging

        Returns:
            Path if successful, None otherwise
        """
        data = self.extract_frame(timestamp)
        if data:
            with open(output_path, "wb") as f:
                f.write(data)
            logger.debug(f"Step {step_num}: {frame_name} @ {timestamp:.2f}s")
            return output_path
        else:
            logger.warning(f"Failed to extract {frame_name} frame for step {step_num}")
            return None

    def _extract_frames_parallel(
        self,
        extractions: list[tuple[float, Path]],
        max_workers: int | None = None,
    ) -> list[Path]:
        """Extract multiple frames in parallel using ffmpeg.

        Args:
            extractions: List of (timestamp, output_path) tuples
            max_workers: Max parallel processes (defaults to CPU count * 4, max 24)

        Returns:
            List of successfully extracted paths
        """
        if max_workers is None:
            max_workers = min(24, (os.cpu_count() or 4) * 4)

        def extract_single(timestamp: float, output_path: Path) -> Path | None:
            """Extract a single frame directly to output path."""
            timestamp = max(0.0, timestamp)
            cmd = [
                "ffmpeg",
                "-ss", f"{timestamp:.3f}",
                "-i", str(self._video_path),
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                "-loglevel", "error",
                str(output_path),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0 and output_path.exists():
                    return output_path
            except Exception as e:
                logger.debug(f"Failed to extract {output_path.name}: {e}")
            return None

        extracted: list[Path] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(extract_single, ts, path): path
                for ts, path in extractions
            }

            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result()
                    if result:
                        extracted.append(result)
                except Exception as e:
                    logger.warning(f"Failed to extract {path}: {e}")

        return extracted

    def extract_for_touches(
        self,
        touch_events: list[dict[str, Any]],
        output_dir: Path,
    ) -> list[Path]:
        """Extract frames for touch events using parallel ffmpeg.

        Uses midpoints between consecutive gestures to ensure non-overlapping
        time ranges. Frame count varies by gesture type:
        - tap: before, touch, after (3 frames)
        - swipe: before, swipe_start, swipe_end, after (4 frames)
        - long_press: before, press_start, press_held, after (4 frames)

        Args:
            touch_events: List of dicts with 'timestamp', 'gesture', 'duration_ms'
            output_dir: Directory to save frames

        Returns:
            List of paths to extracted frame files (only successful extractions)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if not touch_events:
            return []

        # Get actual recording duration for boundary calculation
        video_duration = self._get_actual_duration()
        if video_duration <= 0:
            logger.warning("Could not get video duration, using fallback")
            video_duration = touch_events[-1].get("timestamp", 0.0) + 2.0

        # Calculate frame times using midpoint approach
        frame_times = self._calculate_frame_times(touch_events, video_duration)

        # Build extraction tasks: (timestamp, output_path)
        extractions: list[tuple[float, Path]] = []

        for ft in frame_times:
            step_num = ft["step_num"]
            gesture = ft["gesture"]
            step_str = f"{step_num:03d}"

            # BEFORE frame (common to all gestures)
            extractions.append((
                ft["before_time"],
                output_dir / f"step_{step_str}_before.png"
            ))

            # Gesture-specific frames
            if gesture == "tap":
                extractions.append((
                    ft["touch_time"],
                    output_dir / f"step_{step_str}_touch.png"
                ))
            elif gesture == "swipe":
                extractions.append((
                    ft["swipe_start_time"],
                    output_dir / f"step_{step_str}_swipe_start.png"
                ))
                extractions.append((
                    ft["swipe_end_time"],
                    output_dir / f"step_{step_str}_swipe_end.png"
                ))
            elif gesture == "long_press":
                extractions.append((
                    ft["press_start_time"],
                    output_dir / f"step_{step_str}_press_start.png"
                ))
                extractions.append((
                    ft["press_held_time"],
                    output_dir / f"step_{step_str}_press_held.png"
                ))
            else:
                # Unknown gesture - extract single touch frame
                extractions.append((
                    ft.get("touch_time", ft["before_time"]),
                    output_dir / f"step_{step_str}_touch.png"
                ))

            # AFTER frame (common to all gestures)
            extractions.append((
                ft["after_time"],
                output_dir / f"step_{step_str}_after.png"
            ))

        # Extract all frames in parallel
        logger.info(f"Extracting {len(extractions)} frames in parallel...")
        extracted_paths = self._extract_frames_parallel(extractions)

        logger.info(
            f"Extracted {len(extracted_paths)} frames for {len(touch_events)} gestures"
        )

        return extracted_paths

    def _calculate_collapsed_frame_times(
        self,
        collapsed_steps: list[CollapsedStep],
        touch_events: list[dict[str, Any]],
        video_duration: float,
    ) -> list[dict[str, Any]]:
        """Calculate frame extraction times for collapsed steps.

        Uses original_indices to find timestamps in raw touch_events.
        For "type" action, extracts only before/after frames.

        Args:
            collapsed_steps: List of CollapsedStep objects
            touch_events: Original raw touch events
            video_duration: Video duration in seconds

        Returns:
            List of dicts with step_num, action, and frame times
        """
        frame_times = []
        n = len(collapsed_steps)

        for i, step in enumerate(collapsed_steps):
            start_idx, end_idx = step.original_indices

            # Get timestamps from raw touch_events
            first_event = touch_events[start_idx]
            last_event = touch_events[end_idx]

            first_end_time = first_event.get("timestamp", 0.0)
            first_duration_ms = first_event.get("duration_ms", 50)
            first_start_time = first_end_time - (first_duration_ms / 1000.0)

            last_end_time = last_event.get("timestamp", 0.0)

            # Before: midpoint between previous step end and this step start
            if i == 0:
                prev_end_time = 0.0  # Video start
            else:
                prev_step = collapsed_steps[i - 1]
                prev_event = touch_events[prev_step.original_indices[1]]
                prev_end_time = prev_event.get("timestamp", 0.0)
            before_time = (prev_end_time + first_start_time) / 2

            # After: midpoint between this step end and next step start
            if i == n - 1:
                next_start_time = video_duration  # Video end
            else:
                next_step = collapsed_steps[i + 1]
                next_event = touch_events[next_step.original_indices[0]]
                next_end = next_event.get("timestamp", 0.0)
                next_duration = next_event.get("duration_ms", 50) / 1000.0
                next_start_time = next_end - next_duration
            after_time = (last_end_time + next_start_time) / 2

            ft: dict[str, Any] = {
                "step_num": step.index,
                "action": step.action,
                "before_time": before_time,
                "after_time": after_time,
            }

            if step.action == "type":
                # "type" action: only before and after, no touch frame
                pass  # No additional frame times needed

            elif step.action == "tap":
                # tap: show target button just before touch
                ft["touch_time"] = max(0.0, first_start_time - self.TOUCH_OFFSET)

            elif step.action == "swipe":
                # swipe: show start position and end position
                ft["swipe_start_time"] = first_start_time
                ft["swipe_end_time"] = max(
                    first_start_time, last_end_time - 0.05
                )

            elif step.action == "long_press":
                # long_press: show press start and held state
                # Use duration_ms from the event for accurate duration
                duration_sec = first_duration_ms / 1000.0
                ft["press_start_time"] = first_start_time
                held_time = first_start_time + (duration_sec * self.PRESS_HELD_RATIO)
                ft["press_held_time"] = held_time

            else:
                # Unknown action - treat as tap
                ft["touch_time"] = max(0.0, first_start_time - self.TOUCH_OFFSET)

            frame_times.append(ft)

        return frame_times

    def extract_for_collapsed_steps(
        self,
        collapsed_steps: list[CollapsedStep],
        touch_events: list[dict[str, Any]],
        output_dir: Path,
    ) -> list[Path]:
        """Extract frames for collapsed steps using parallel ffmpeg.

        Uses collapsed step data with original_indices to find timestamps
        in raw touch_events. For "type" action, extracts only before/after
        frames (keyboard taps are not useful to show).

        Frame count varies by action type:
        - type: before, after (2 frames)
        - tap: before, touch, after (3 frames)
        - swipe: before, swipe_start, swipe_end, after (4 frames)
        - long_press: before, press_start, press_held, after (4 frames)

        Args:
            collapsed_steps: List of CollapsedStep objects
            touch_events: Original raw touch events for timestamp lookup
            output_dir: Directory to save frames

        Returns:
            List of paths to extracted frame files (only successful extractions)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if not collapsed_steps or not touch_events:
            return []

        # Get actual recording duration for boundary calculation
        video_duration = self._get_actual_duration()
        if video_duration <= 0:
            logger.warning("Could not get video duration, using fallback")
            last_event = touch_events[-1]
            video_duration = last_event.get("timestamp", 0.0) + 2.0

        # Calculate frame times for collapsed steps
        frame_times = self._calculate_collapsed_frame_times(
            collapsed_steps, touch_events, video_duration
        )

        # Build extraction tasks: (timestamp, output_path)
        extractions: list[tuple[float, Path]] = []

        for ft in frame_times:
            step_num = ft["step_num"]
            action = ft["action"]
            step_str = f"{step_num:03d}"

            # BEFORE frame (common to all actions)
            extractions.append((
                ft["before_time"],
                output_dir / f"step_{step_str}_before.png"
            ))

            # Action-specific frames
            if action == "type":
                # "type" action: no touch frame, only before and after
                pass
            elif action == "tap":
                extractions.append((
                    ft["touch_time"],
                    output_dir / f"step_{step_str}_touch.png"
                ))
            elif action == "swipe":
                extractions.append((
                    ft["swipe_start_time"],
                    output_dir / f"step_{step_str}_swipe_start.png"
                ))
                extractions.append((
                    ft["swipe_end_time"],
                    output_dir / f"step_{step_str}_swipe_end.png"
                ))
            elif action == "long_press":
                extractions.append((
                    ft["press_start_time"],
                    output_dir / f"step_{step_str}_press_start.png"
                ))
                extractions.append((
                    ft["press_held_time"],
                    output_dir / f"step_{step_str}_press_held.png"
                ))
            else:
                # Unknown action - extract single touch frame
                extractions.append((
                    ft.get("touch_time", ft["before_time"]),
                    output_dir / f"step_{step_str}_touch.png"
                ))

            # AFTER frame (common to all actions)
            extractions.append((
                ft["after_time"],
                output_dir / f"step_{step_str}_after.png"
            ))

        # Extract all frames in parallel
        logger.info(f"Extracting {len(extractions)} frames in parallel...")
        extracted_paths = self._extract_frames_parallel(extractions)

        logger.info(
            f"Extracted {len(extracted_paths)} frames for "
            f"{len(collapsed_steps)} collapsed steps"
        )

        return extracted_paths
