"""Scrcpy service for fast screenshots and video recording."""

import io
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from adbutils import adb
from myscrcpy.core import ControlArgs, Session, VideoArgs
from myscrcpy.core.control import Action
from PIL import Image

logger = logging.getLogger("mut.scrcpy")


class ScrcpyService:
    """Unified scrcpy service for screenshots and recording.

    Uses MYScrcpy for scrcpy 3.x support. Maintains a circular frame buffer
    for instant screenshots (~50ms) and handles video recording via PyAV.
    Optionally enables control mode for touch injection.
    """

    FRAME_BUFFER_SIZE = 10

    def __init__(self, device_id: str, enable_control: bool = False):
        """Initialize service for a specific device.

        Args:
            device_id: ADB device identifier
            enable_control: Enable control mode for touch injection
        """
        self._device_id = device_id
        self._enable_control = enable_control
        self._session: Session | None = None
        self._frame_buffer: deque[Any] = deque(maxlen=self.FRAME_BUFFER_SIZE)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()  # For clean shutdown signaling
        self._frame_thread: threading.Thread | None = None
        self._width = 0
        self._height = 0

        # Recording state
        self._recording = False
        self._writer_open = False  # Track if writer is open for writing (thread-safe)
        self._video_writer: Any = None
        self._video_stream: Any = None
        self._recording_output_path: str | None = None
        self._recording_start_time: float | None = None
        self._frame_timestamps: list[float] = []  # Wall-clock timestamps for each frame

    @property
    def is_connected(self) -> bool:
        """Check if scrcpy is connected and receiving frames."""
        session = self._session
        return (
            session is not None
            and not self._stop_event.is_set()
            and session.va is not None
        )

    @property
    def is_recording(self) -> bool:
        """Check if recording is active."""
        with self._lock:
            return self._recording and self._video_writer is not None

    def connect(self) -> bool:
        """Connect to device via MYScrcpy.

        Returns:
            True if connected successfully
        """
        if self.is_connected:
            return True

        try:
            # Find device
            devices = adb.device_list()
            device = None
            for d in devices:
                if d.serial == self._device_id:
                    device = d
                    break

            if device is None:
                logger.error(f"Device {self._device_id} not found")
                return False

            logger.info(f"Connecting to {self._device_id}...")

            # Create session with video, optionally with control
            control_args = ControlArgs() if self._enable_control else None
            self._session = Session(
                device,
                video_args=VideoArgs(fps=60),
                control_args=control_args,
            )

            # Wait for video stream to fully initialize
            # MYScrcpy needs time to set up the native decoder
            time.sleep(2.0)

            if self._session.va is None:
                logger.error("Video stream failed to initialize")
                self._session = None
                return False

            # Wait for first frame to be available before starting thread
            # This prevents segfaults from accessing uninitialized native buffers
            first_frame = None
            for _ in range(20):  # Try for 2 seconds
                try:
                    first_frame = self._session.va.get_frame()
                    if first_frame is not None:
                        break
                except Exception:
                    pass
                time.sleep(0.1)

            if first_frame is None:
                logger.error("Could not get first frame from video stream")
                self._session = None
                return False

            # Store initial dimensions
            self._height, self._width = first_frame.shape[:2]
            logger.info(f"First frame received: {self._width}x{self._height}")

            # Start frame capture thread (not daemon - we need clean shutdown)
            self._stop_event.clear()
            self._frame_thread = threading.Thread(
                target=self._frame_loop,
                daemon=False,  # Must exit cleanly before session.stop()
            )
            self._frame_thread.start()

            # Give thread time to start
            time.sleep(0.2)

            logger.info(f"Connected to {self._device_id}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._session = None
            return False

    def disconnect(self) -> None:
        """Disconnect from device and clean up.

        IMPORTANT: We must stop the frame thread BEFORE calling session.stop()
        to avoid segfaults. The native scrcpy code can't be safely interrupted.
        """
        # Signal thread to stop
        self._stop_event.set()

        # Wait for frame thread to exit (it checks stop_event frequently)
        if self._frame_thread:
            # Give it time to finish current iteration and exit
            self._frame_thread.join(timeout=5)
            if self._frame_thread.is_alive():
                # Thread didn't exit cleanly - log warning but proceed
                # This is safer than segfaulting
                logger.warning("Frame thread did not exit cleanly, proceeding with disconnect")
            self._frame_thread = None

        # NOW it's safe to stop the session
        if self._session:
            try:
                self._session.stop()
            except Exception:
                pass
            self._session = None

        with self._lock:
            self._frame_buffer.clear()

        self._width = 0
        self._height = 0
        logger.info("Disconnected")

    def _frame_loop(self) -> None:
        """Continuous frame capture loop.

        IMPORTANT: This loop must check stop_event frequently and exit quickly
        when signaled. Never access session after stop_event is set.
        """
        # Small delay to ensure session is fully ready
        time.sleep(0.1)

        while not self._stop_event.is_set():
            # Check session validity AFTER checking stop_event
            session = self._session
            if session is None or session.va is None:
                break

            try:
                # Check stop_event again right before native call
                if self._stop_event.is_set():
                    break

                frame = session.va.get_frame()

                # Check again after native call returns
                if self._stop_event.is_set():
                    break

                if frame is not None:
                    timestamp = time.time()

                    with self._lock:
                        self._frame_buffer.append({
                            "frame": frame,
                            "timestamp": timestamp,
                        })

                        # Update dimensions from first frame
                        if self._height == 0:
                            self._height, self._width = frame.shape[:2]

                        # Check recording state under lock
                        recording = self._recording

                    # Write to video if recording
                    if recording and not self._stop_event.is_set():
                        self._write_frame(frame, timestamp)

                time.sleep(0.016)  # ~60 fps polling

            except Exception as e:
                if self._stop_event.is_set():
                    break  # Expected during shutdown
                logger.debug(f"Frame loop error: {e}")
                time.sleep(0.1)

        logger.debug("Frame loop exited cleanly")

    def screenshot(self) -> bytes:
        """Get latest frame as PNG from buffer.

        Returns:
            PNG image bytes

        Raises:
            RuntimeError: If not connected or no frames available
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to device")

        with self._lock:
            if not self._frame_buffer:
                raise RuntimeError("No frames available in buffer")
            # Copy the frame array while holding the lock to prevent
            # the original from being garbage collected
            frame = self._frame_buffer[-1]["frame"].copy()

        # Convert numpy array to PNG bytes
        img = Image.fromarray(frame)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def start_recording(self, output_path: str) -> dict[str, Any]:
        """Start writing frames to video file.

        Args:
            output_path: Path to output video file (.mp4)

        Returns:
            Dict with success status and recording_start_time
        """
        if self.is_recording:
            return {"success": False, "error": "Recording already in progress"}

        if not self.is_connected:
            return {"success": False, "error": "Not connected to device"}

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Read dimensions under lock to avoid race condition
        with self._lock:
            width = self._width
            height = self._height

        if width == 0 or height == 0:
            return {"success": False, "error": "No frame dimensions available yet"}

        try:
            import av

            container = av.open(output_path, "w")
            self._video_writer = container
            stream = container.add_stream("h264", rate=30)
            stream.width = width
            stream.height = height
            stream.pix_fmt = "yuv420p"
            self._video_stream = stream

            with self._lock:
                self._writer_open = True
                self._recording = True
            self._recording_output_path = output_path
            self._recording_start_time = time.time()
            self._frame_timestamps = []  # Clear timestamps for new recording

            logger.info(f"Recording started: {output_path}")

            return {
                "success": True,
                "output_path": output_path,
                "recording_start_time": self._recording_start_time,
            }

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return {"success": False, "error": str(e)}

    def stop_recording(self) -> dict[str, Any]:
        """Stop recording and finalize video.

        Returns:
            Dict with recording info
        """
        if not self.is_recording:
            return {"success": False, "error": "No recording in progress"}

        duration = time.time() - (self._recording_start_time or 0)
        output_path = self._recording_output_path

        try:
            # Signal frame thread to stop writing BEFORE we close the writer
            with self._lock:
                self._writer_open = False
                self._recording = False

            # Small delay to ensure frame thread sees the flag change
            time.sleep(0.05)

            # Flush remaining packets before closing
            if self._video_stream:
                for packet in self._video_stream.encode(None):
                    if self._video_writer:
                        self._video_writer.mux(packet)

            # Finalize video
            if self._video_writer:
                logger.info("Closing video writer...")
                self._video_writer.close()
                logger.info("Video writer closed")

            file_size = Path(output_path).stat().st_size if output_path else 0

            # Save frame timestamps for accurate frame extraction
            timestamps_path = None
            if output_path and self._frame_timestamps:
                import json
                timestamps_path = str(Path(output_path).with_suffix(".timestamps.json"))
                with open(timestamps_path, "w") as f:
                    json.dump(self._frame_timestamps, f)
                logger.info(f"Saved {len(self._frame_timestamps)} frame timestamps")

            logger.info(f"Recording stopped: {output_path} ({duration:.1f}s)")

            return {
                "success": True,
                "output_path": output_path,
                "timestamps_path": timestamps_path,
                "duration_seconds": round(duration, 2),
                "file_size_bytes": file_size,
                "frame_count": len(self._frame_timestamps),
            }

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            return {"success": False, "error": str(e)}

        finally:
            self._video_writer = None
            self._video_stream = None
            self._recording_output_path = None
            self._recording_start_time = None
            self._frame_timestamps = []

    def _write_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Write frame to video file with proper timestamp.

        Thread-safe: checks _writer_open flag under lock to prevent race
        condition where main thread closes writer while frame thread writes.

        Args:
            frame: RGB frame as numpy array
            timestamp: Wall-clock timestamp when frame was captured
        """
        # Check if writer is open under lock (prevents race with stop_recording)
        with self._lock:
            if not self._writer_open:
                return
            writer = self._video_writer
            stream = self._video_stream

        if not writer or not stream:
            return

        try:
            import av

            # Store wall-clock timestamp for this frame (relative to recording start)
            if self._recording_start_time:
                elapsed = timestamp - self._recording_start_time
                with self._lock:
                    self._frame_timestamps.append(elapsed)

            # Convert RGB to video frame and encode
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
            for packet in stream.encode(video_frame):
                writer.mux(packet)

        except Exception as e:
            logger.debug(f"Error writing frame: {e}")

    def get_buffer_info(self) -> dict[str, Any]:
        """Get info about current frame buffer state."""
        with self._lock:
            count = len(self._frame_buffer)
            oldest_ts = self._frame_buffer[0]["timestamp"] if count > 0 else None
            newest_ts = self._frame_buffer[-1]["timestamp"] if count > 0 else None
            width = self._width
            height = self._height

        return {
            "frame_count": count,
            "buffer_size": self.FRAME_BUFFER_SIZE,
            "width": width,
            "height": height,
            "oldest_frame_age_ms": int((time.time() - oldest_ts) * 1000) if oldest_ts else None,
            "newest_frame_age_ms": int((time.time() - newest_ts) * 1000) if newest_ts else None,
        }

    def get_screen_size(self) -> tuple[int, int]:
        """Get device screen dimensions.

        Returns:
            Tuple of (width, height) in pixels
        """
        with self._lock:
            return self._width, self._height

    def get_latest_frame(self) -> np.ndarray | None:
        """Get latest frame as numpy array (RGB).

        Returns:
            Frame as numpy array or None if no frames available
        """
        with self._lock:
            if not self._frame_buffer:
                return None
            return self._frame_buffer[-1]["frame"].copy()

    @property
    def is_control_ready(self) -> bool:
        """Check if control mode is ready for touch injection."""
        return (
            self._enable_control
            and self._session is not None
            and self._session.ca is not None
        )

    def inject_touch(
        self,
        action: int,
        x: int,
        y: int,
        touch_id: int = 0,
    ) -> bool:
        """Inject touch event to device.

        Args:
            action: Action.DOWN (0), Action.RELEASE (1), or Action.MOVE (2)
            x: Screen X coordinate in pixels
            y: Screen Y coordinate in pixels
            touch_id: Touch pointer ID for multi-touch (default 0)

        Returns:
            True if injection succeeded, False otherwise
        """
        if not self.is_control_ready:
            logger.warning("Control not ready, cannot inject touch")
            return False

        try:
            with self._lock:
                width = self._width
                height = self._height

            if width == 0 or height == 0:
                logger.warning("Screen dimensions not available")
                return False

            self._session.ca.f_touch(
                action=action,
                x=x,
                y=y,
                width=width,
                height=height,
                touch_id=touch_id,
            )
            return True

        except Exception as e:
            logger.error(f"Touch injection failed: {e}")
            return False

    def tap(self, x: int, y: int, duration_ms: int = 50) -> bool:
        """Inject a tap gesture at coordinates.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            duration_ms: Duration between down and up (default 50ms)

        Returns:
            True if tap succeeded
        """
        if not self.inject_touch(Action.DOWN.value, x, y):
            return False
        time.sleep(duration_ms / 1000)
        return self.inject_touch(Action.RELEASE.value, x, y)

    def long_press(self, x: int, y: int, duration_ms: int = 500) -> bool:
        """Inject a long press gesture at coordinates.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            duration_ms: Duration to hold (default 500ms)

        Returns:
            True if long press succeeded
        """
        if not self.inject_touch(Action.DOWN.value, x, y):
            return False
        time.sleep(duration_ms / 1000)
        return self.inject_touch(Action.RELEASE.value, x, y)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 300,
        steps: int = 20,
    ) -> bool:
        """Inject a swipe gesture.

        Args:
            start_x, start_y: Starting coordinates
            end_x, end_y: Ending coordinates
            duration_ms: Total swipe duration
            steps: Number of intermediate move events

        Returns:
            True if swipe succeeded
        """
        if not self.inject_touch(Action.DOWN.value, start_x, start_y):
            return False

        step_delay = duration_ms / steps / 1000
        for i in range(1, steps + 1):
            progress = i / steps
            x = int(start_x + (end_x - start_x) * progress)
            y = int(start_y + (end_y - start_y) * progress)
            self.inject_touch(Action.MOVE.value, x, y)
            time.sleep(step_delay)

        return self.inject_touch(Action.RELEASE.value, end_x, end_y)
