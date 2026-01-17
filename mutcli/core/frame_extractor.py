"""Video frame extraction using PyAV."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import av

if TYPE_CHECKING:
    from mutcli.core.step_collapsing import CollapsedStep

logger = logging.getLogger("mut.frame_extractor")


class FrameExtractor:
    """Extract frames from recorded video at specific timestamps.

    Uses PyAV for efficient video seeking and frame extraction.
    Uses midpoint approach for non-overlapping time ranges.
    Uses frame timestamps file for accurate wall-clock time mapping.

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
        """Get video duration in seconds.

        Returns:
            Duration in seconds, or 0.0 on error
        """
        try:
            with av.open(str(self._video_path)) as container:
                stream = container.streams.video[0]
                if stream.duration and stream.time_base:
                    return float(stream.duration * stream.time_base)
                # Fallback: calculate from container duration
                if container.duration:
                    return container.duration / av.time_base
                return 0.0
        except Exception as e:
            logger.error(f"Failed to get video duration: {e}")
            return 0.0

    def extract_frame(self, timestamp_sec: float) -> bytes | None:
        """Extract single frame at timestamp as PNG bytes.

        If frame timestamps are available, uses frame index for accurate
        wall-clock time extraction with efficient seeking.

        Args:
            timestamp_sec: Timestamp in seconds (wall-clock time)

        Returns:
            PNG image bytes, or None on error
        """
        # Find target frame index using timestamps if available
        target_frame_idx = self._find_frame_index(timestamp_sec)

        try:
            with av.open(str(self._video_path)) as container:
                stream = container.streams.video[0]
                time_base = float(stream.time_base) if stream.time_base else 1.0 / 30

                # Seek to keyframe before target (use estimated PTS from frame rate)
                # This is approximate but gets us close for efficient decoding
                estimated_pts = int((target_frame_idx / 30.0) / time_base)
                seek_pts = max(0, estimated_pts - int(1.0 / time_base))
                container.seek(seek_pts, stream=stream, backward=True)

                # Decode frames and find the target by index
                # Track frame indices by counting from seek position
                best_frame = None
                frames_decoded = 0

                for frame in container.decode(video=0):
                    # Get actual frame index from PTS
                    frame_idx = int(frame.pts * time_base * 30) if frame.pts else frames_decoded

                    # Keep best frame (closest to target without going too far)
                    if best_frame is None or frame_idx <= target_frame_idx:
                        best_frame = frame

                    # Stop if we've passed the target
                    if frame_idx >= target_frame_idx:
                        break

                    frames_decoded += 1

                    # Safety limit
                    if frames_decoded > 100:
                        break

                if best_frame is not None:
                    img = best_frame.to_image()
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    return buffer.getvalue()

                logger.warning(f"Frame {target_frame_idx} not found for timestamp {timestamp_sec}s")
                return None

        except FileNotFoundError:
            logger.error(f"Video file not found: {self._video_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract frame at {timestamp_sec}s: {e}")
            return None

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

    def extract_for_touches(
        self,
        touch_events: list[dict[str, Any]],
        output_dir: Path,
    ) -> list[Path]:
        """Extract frames for touch events using midpoint approach.

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

        extracted_paths: list[Path] = []

        if not touch_events:
            return extracted_paths

        # Get actual recording duration for boundary calculation
        video_duration = self._get_actual_duration()
        if video_duration <= 0:
            logger.warning("Could not get video duration, using fallback")
            video_duration = touch_events[-1].get("timestamp", 0.0) + 2.0

        # Calculate frame times using midpoint approach
        frame_times = self._calculate_frame_times(touch_events, video_duration)

        for ft in frame_times:
            step_num = ft["step_num"]
            gesture = ft["gesture"]
            step_str = f"{step_num:03d}"

            # BEFORE frame (common to all gestures)
            path = self._extract_and_save(
                ft["before_time"],
                output_dir / f"step_{step_str}_before.png",
                step_num, "before"
            )
            if path:
                extracted_paths.append(path)

            # Gesture-specific frames
            if gesture == "tap":
                path = self._extract_and_save(
                    ft["touch_time"],
                    output_dir / f"step_{step_str}_touch.png",
                    step_num, "touch"
                )
                if path:
                    extracted_paths.append(path)

            elif gesture == "swipe":
                path = self._extract_and_save(
                    ft["swipe_start_time"],
                    output_dir / f"step_{step_str}_swipe_start.png",
                    step_num, "swipe_start"
                )
                if path:
                    extracted_paths.append(path)

                path = self._extract_and_save(
                    ft["swipe_end_time"],
                    output_dir / f"step_{step_str}_swipe_end.png",
                    step_num, "swipe_end"
                )
                if path:
                    extracted_paths.append(path)

            elif gesture == "long_press":
                path = self._extract_and_save(
                    ft["press_start_time"],
                    output_dir / f"step_{step_str}_press_start.png",
                    step_num, "press_start"
                )
                if path:
                    extracted_paths.append(path)

                path = self._extract_and_save(
                    ft["press_held_time"],
                    output_dir / f"step_{step_str}_press_held.png",
                    step_num, "press_held"
                )
                if path:
                    extracted_paths.append(path)

            else:
                # Unknown gesture - extract single touch frame
                path = self._extract_and_save(
                    ft.get("touch_time", ft["before_time"]),
                    output_dir / f"step_{step_str}_touch.png",
                    step_num, "touch"
                )
                if path:
                    extracted_paths.append(path)

            # AFTER frame (common to all gestures)
            path = self._extract_and_save(
                ft["after_time"],
                output_dir / f"step_{step_str}_after.png",
                step_num, "after"
            )
            if path:
                extracted_paths.append(path)

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
        """Extract frames for collapsed steps.

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

        extracted_paths: list[Path] = []

        if not collapsed_steps or not touch_events:
            return extracted_paths

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

        for ft in frame_times:
            step_num = ft["step_num"]
            action = ft["action"]
            step_str = f"{step_num:03d}"

            # BEFORE frame (common to all actions)
            path = self._extract_and_save(
                ft["before_time"],
                output_dir / f"step_{step_str}_before.png",
                step_num, "before"
            )
            if path:
                extracted_paths.append(path)

            # Action-specific frames
            if action == "type":
                # "type" action: no touch frame, only before and after
                pass

            elif action == "tap":
                path = self._extract_and_save(
                    ft["touch_time"],
                    output_dir / f"step_{step_str}_touch.png",
                    step_num, "touch"
                )
                if path:
                    extracted_paths.append(path)

            elif action == "swipe":
                path = self._extract_and_save(
                    ft["swipe_start_time"],
                    output_dir / f"step_{step_str}_swipe_start.png",
                    step_num, "swipe_start"
                )
                if path:
                    extracted_paths.append(path)

                path = self._extract_and_save(
                    ft["swipe_end_time"],
                    output_dir / f"step_{step_str}_swipe_end.png",
                    step_num, "swipe_end"
                )
                if path:
                    extracted_paths.append(path)

            elif action == "long_press":
                path = self._extract_and_save(
                    ft["press_start_time"],
                    output_dir / f"step_{step_str}_press_start.png",
                    step_num, "press_start"
                )
                if path:
                    extracted_paths.append(path)

                path = self._extract_and_save(
                    ft["press_held_time"],
                    output_dir / f"step_{step_str}_press_held.png",
                    step_num, "press_held"
                )
                if path:
                    extracted_paths.append(path)

            else:
                # Unknown action - extract single touch frame
                path = self._extract_and_save(
                    ft.get("touch_time", ft["before_time"]),
                    output_dir / f"step_{step_str}_touch.png",
                    step_num, "touch"
                )
                if path:
                    extracted_paths.append(path)

            # AFTER frame (common to all actions)
            path = self._extract_and_save(
                ft["after_time"],
                output_dir / f"step_{step_str}_after.png",
                step_num, "after"
            )
            if path:
                extracted_paths.append(path)

        logger.info(
            f"Extracted {len(extracted_paths)} frames for "
            f"{len(collapsed_steps)} collapsed steps"
        )

        return extracted_paths
