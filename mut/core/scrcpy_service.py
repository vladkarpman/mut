"""Scrcpy service for fast screenshots and video recording."""

import io
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

# TODO: Import these when implementing
# from myscrcpy.core import Session, VideoArgs
# from adbutils import adb
# from PIL import Image
# import numpy as np
# import av


class ScrcpyService:
    """Unified scrcpy service for screenshots and recording.

    Uses MYScrcpy for scrcpy 3.x support. Maintains a circular frame buffer
    for instant screenshots (~50ms) and handles video recording via PyAV.
    """

    def __init__(self, device_id: str):
        """Initialize service for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id
        self._session = None
        self._frame_buffer: deque = deque(maxlen=10)
        self._lock = threading.Lock()
        self._running = False
        self._frame_thread: threading.Thread | None = None

        # Recording state
        self._recording = False
        self._video_writer = None
        self._recording_output_path: str | None = None
        self._recording_start_time: float | None = None

    @property
    def is_connected(self) -> bool:
        """Check if scrcpy is connected."""
        return self._session is not None and self._running

    @property
    def is_recording(self) -> bool:
        """Check if recording is active."""
        return self._recording

    async def connect(self) -> bool:
        """Connect to device via MYScrcpy.

        Returns:
            True if connected successfully
        """
        # TODO: Implement MYScrcpy connection
        # try:
        #     from adbutils import adb
        #     from myscrcpy.core import Session, VideoArgs
        #
        #     devices = adb.device_list()
        #     device = None
        #     for d in devices:
        #         if d.serial == self._device_id:
        #             device = d
        #             break
        #
        #     if not device:
        #         return False
        #
        #     self._session = Session(
        #         device,
        #         video_args=VideoArgs(fps=60),
        #         control_args=None,
        #     )
        #
        #     self._running = True
        #     self._frame_thread = threading.Thread(
        #         target=self._frame_loop, daemon=True
        #     )
        #     self._frame_thread.start()
        #
        #     return True
        #
        # except Exception as e:
        #     return False

        raise NotImplementedError("ScrcpyService.connect() not yet implemented")

    def screenshot(self) -> bytes:
        """Get latest frame as PNG from buffer.

        Returns:
            PNG image bytes

        Raises:
            RuntimeError: If not connected or no frames available
        """
        if not self.is_connected:
            raise RuntimeError("scrcpy not connected")

        with self._lock:
            if not self._frame_buffer:
                raise RuntimeError("No frames available in buffer")

            frame = self._frame_buffer[-1]

        # TODO: Convert numpy array to PNG
        # from PIL import Image
        # img = Image.fromarray(frame)
        # buffer = io.BytesIO()
        # img.save(buffer, format="PNG")
        # return buffer.getvalue()

        raise NotImplementedError("ScrcpyService.screenshot() not yet implemented")

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

        # TODO: Initialize PyAV video writer
        # import av
        # self._video_writer = av.open(output_path, 'w')
        # self._stream = self._video_writer.add_stream('h264', rate=30)

        self._recording = True
        self._recording_output_path = output_path
        self._recording_start_time = time.time()

        return {
            "success": True,
            "output_path": output_path,
            "recording_start_time": self._recording_start_time,
        }

    def stop_recording(self) -> dict[str, Any]:
        """Stop recording and finalize video.

        Returns:
            Dict with recording info
        """
        if not self.is_recording:
            return {"success": False, "error": "No recording in progress"}

        duration = time.time() - (self._recording_start_time or 0)

        # TODO: Finalize video
        # if self._video_writer:
        #     self._video_writer.close()

        output_path = self._recording_output_path

        # Reset recording state
        self._recording = False
        self._video_writer = None
        self._recording_output_path = None
        self._recording_start_time = None

        return {
            "success": True,
            "output_path": output_path,
            "duration_seconds": round(duration, 2),
        }

    def disconnect(self) -> None:
        """Disconnect from device and clean up."""
        self._running = False

        if self._frame_thread:
            self._frame_thread.join(timeout=1)
            self._frame_thread = None

        if self._session:
            try:
                self._session.stop()
            except Exception:
                pass
            self._session = None

        self._frame_buffer.clear()

    def _frame_loop(self) -> None:
        """Continuous frame capture loop."""
        while self._running and self._session:
            try:
                # TODO: Get frame from MYScrcpy
                # frame = self._session.va.get_frame()
                # if frame is not None:
                #     with self._lock:
                #         self._frame_buffer.append(frame)
                #     if self._recording:
                #         self._write_frame(frame)

                time.sleep(0.016)  # ~60 fps

            except Exception:
                time.sleep(0.1)

    def _write_frame(self, frame) -> None:
        """Write frame to video file."""
        # TODO: Implement frame writing with PyAV
        # import av
        # video_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        # packet = self._stream.encode(video_frame)
        # self._video_writer.mux(packet)
        pass
