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
from myscrcpy.core import Session, VideoArgs
from PIL import Image

logger = logging.getLogger("mut.scrcpy")


class ScrcpyService:
    """Unified scrcpy service for screenshots and recording.

    Uses MYScrcpy for scrcpy 3.x support. Maintains a circular frame buffer
    for instant screenshots (~50ms) and handles video recording via PyAV.
    """

    FRAME_BUFFER_SIZE = 10

    def __init__(self, device_id: str):
        """Initialize service for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._session: Session | None = None
        self._frame_buffer: deque[Any] = deque(maxlen=self.FRAME_BUFFER_SIZE)
        self._lock = threading.Lock()
        self._running = False
        self._frame_thread: threading.Thread | None = None
        self._width = 0
        self._height = 0

        # Recording state
        self._recording = False
        self._video_writer: Any = None
        self._video_stream: Any = None
        self._recording_output_path: str | None = None
        self._recording_start_time: float | None = None

    @property
    def is_connected(self) -> bool:
        """Check if scrcpy is connected and receiving frames."""
        session = self._session
        return (
            session is not None
            and self._running
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

            # Create session with video only
            self._session = Session(
                device,
                video_args=VideoArgs(fps=60),
                control_args=None,  # No control needed
            )

            # Wait for video stream to initialize
            time.sleep(1.0)

            if self._session.va is None:
                logger.error("Video stream failed to initialize")
                self._session = None
                return False

            # Start frame capture thread
            self._running = True
            self._frame_thread = threading.Thread(
                target=self._frame_loop,
                daemon=True,
            )
            self._frame_thread.start()

            # Wait for first frame
            time.sleep(0.5)

            logger.info(f"Connected to {self._device_id}")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._session = None
            return False

    def disconnect(self) -> None:
        """Disconnect from device and clean up."""
        self._running = False

        if self._frame_thread:
            self._frame_thread.join(timeout=2)
            self._frame_thread = None

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
        """Continuous frame capture loop."""
        while self._running and self._session and self._session.va:
            try:
                frame = self._session.va.get_frame()
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
                    if recording:
                        self._write_frame(frame)

                time.sleep(0.016)  # ~60 fps polling

            except Exception as e:
                logger.debug(f"Frame loop error: {e}")
                time.sleep(0.1)

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
                self._recording = True
            self._recording_output_path = output_path
            self._recording_start_time = time.time()

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
            with self._lock:
                self._recording = False

            # Flush remaining packets before closing
            if self._video_stream:
                for packet in self._video_stream.encode(None):
                    if self._video_writer:
                        self._video_writer.mux(packet)

            # Finalize video
            if self._video_writer:
                self._video_writer.close()

            file_size = Path(output_path).stat().st_size if output_path else 0

            logger.info(f"Recording stopped: {output_path} ({duration:.1f}s)")

            return {
                "success": True,
                "output_path": output_path,
                "duration_seconds": round(duration, 2),
                "file_size_bytes": file_size,
            }

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            return {"success": False, "error": str(e)}

        finally:
            self._video_writer = None
            self._video_stream = None
            self._recording_output_path = None
            self._recording_start_time = None

    def _write_frame(self, frame: np.ndarray) -> None:
        """Write frame to video file."""
        if not self._video_writer or not self._video_stream:
            return

        try:
            import av

            # Convert RGB to video frame
            video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")

            # Encode and write
            for packet in self._video_stream.encode(video_frame):
                self._video_writer.mux(packet)

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
