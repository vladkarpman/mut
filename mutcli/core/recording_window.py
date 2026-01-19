"""Recording window for injection-based touch capture.

Displays live screen mirror and captures mouse events for touch injection.
"""

import logging
import threading
import tkinter as tk
from typing import TYPE_CHECKING, Callable

from PIL import Image, ImageTk

if TYPE_CHECKING:
    from mutcli.core.scrcpy_service import ScrcpyService
    from mutcli.core.touch_injector import TouchInjector

logger = logging.getLogger("mut.recording_window")


class RecordingWindow:
    """Tkinter window for recording touch interactions.

    Displays the live device screen and converts mouse events to touch
    events via TouchInjector.

    Usage:
        window = RecordingWindow(scrcpy, injector, on_close=callback)
        window.run()  # Blocks until window is closed
    """

    # Frame update rate (ms)
    FRAME_UPDATE_MS = 33  # ~30fps

    def __init__(
        self,
        scrcpy: "ScrcpyService",
        injector: "TouchInjector",
        title: str = "MUT Recording",
        on_close: Callable[[], None] | None = None,
        scale: float = 0.5,
    ):
        """Initialize recording window.

        Args:
            scrcpy: ScrcpyService instance for screen frames
            injector: TouchInjector instance for handling touches
            title: Window title
            on_close: Callback when window is closed
            scale: Scale factor for window size (0.5 = half size)
        """
        self._scrcpy = scrcpy
        self._injector = injector
        self._on_close = on_close
        self._scale = scale
        self._running = False

        # Screen dimensions (will be set from first frame)
        self._screen_width = 0
        self._screen_height = 0

        # Create window
        self._root = tk.Tk()
        self._root.title(title)
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        # Status bar
        self._status_var = tk.StringVar(value="Connecting...")
        self._status_bar = tk.Label(
            self._root,
            textvariable=self._status_var,
            anchor="w",
            bg="#2d2d2d",
            fg="#ffffff",
            padx=10,
            pady=5,
        )
        self._status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Canvas for screen display
        self._canvas = tk.Canvas(
            self._root,
            bg="#1a1a1a",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events
        self._canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self._canvas.bind("<B1-Motion>", self._on_mouse_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Bind keyboard shortcuts
        self._root.bind("<Escape>", lambda e: self._handle_close())
        self._root.bind("<q>", lambda e: self._handle_close())

        # Image reference (must keep reference to prevent garbage collection)
        self._photo_image: ImageTk.PhotoImage | None = None
        self._canvas_image_id: int | None = None

    def _canvas_to_screen(self, cx: int, cy: int) -> tuple[int, int]:
        """Convert canvas coordinates to device screen coordinates.

        Args:
            cx: Canvas X coordinate
            cy: Canvas Y coordinate

        Returns:
            Tuple of (screen_x, screen_y)
        """
        if self._screen_width == 0 or self._screen_height == 0:
            return cx, cy

        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()

        if canvas_width == 0 or canvas_height == 0:
            return cx, cy

        # Calculate scaling factors
        scale_x = self._screen_width / canvas_width
        scale_y = self._screen_height / canvas_height

        screen_x = int(cx * scale_x)
        screen_y = int(cy * scale_y)

        # Clamp to screen bounds
        screen_x = max(0, min(screen_x, self._screen_width - 1))
        screen_y = max(0, min(screen_y, self._screen_height - 1))

        return screen_x, screen_y

    def _on_mouse_down(self, event: tk.Event) -> None:
        """Handle mouse button press."""
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_down(x, y)
        self._update_status(f"Touch DOWN at ({x}, {y})")

    def _on_mouse_move(self, event: tk.Event) -> None:
        """Handle mouse movement while pressed."""
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_move(x, y)

    def _on_mouse_up(self, event: tk.Event) -> None:
        """Handle mouse button release."""
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_up(x, y)
        self._update_status(f"Events: {self._injector.event_count} | Press ESC or Q to stop")

    def _update_status(self, text: str) -> None:
        """Update status bar text."""
        self._status_var.set(text)

    def _update_frame(self) -> None:
        """Update canvas with latest frame from scrcpy."""
        if not self._running:
            return

        try:
            frame = self._scrcpy.get_latest_frame()

            if frame is not None:
                # Update screen dimensions from frame
                if self._screen_height == 0:
                    self._screen_height, self._screen_width = frame.shape[:2]

                    # Set initial window size
                    win_width = int(self._screen_width * self._scale)
                    win_height = int(self._screen_height * self._scale)
                    self._root.geometry(f"{win_width}x{win_height + 30}")  # +30 for status bar

                    self._update_status(
                        f"Recording... ({self._screen_width}x{self._screen_height}) | "
                        f"Press ESC or Q to stop"
                    )
                    logger.info(f"Screen size: {self._screen_width}x{self._screen_height}")

                # Convert numpy array to PhotoImage
                img = Image.fromarray(frame)

                # Resize to canvas size
                canvas_width = self._canvas.winfo_width()
                canvas_height = self._canvas.winfo_height()

                if canvas_width > 1 and canvas_height > 1:
                    img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

                self._photo_image = ImageTk.PhotoImage(img)

                # Update canvas
                if self._canvas_image_id is None:
                    self._canvas_image_id = self._canvas.create_image(
                        0, 0, anchor=tk.NW, image=self._photo_image
                    )
                else:
                    self._canvas.itemconfig(self._canvas_image_id, image=self._photo_image)

        except Exception as e:
            logger.debug(f"Frame update error: {e}")

        # Schedule next update
        if self._running:
            self._root.after(self.FRAME_UPDATE_MS, self._update_frame)

    def _handle_close(self) -> None:
        """Handle window close."""
        logger.info("Recording window closed")
        self._running = False

        if self._on_close:
            self._on_close()

        self._root.quit()

    def run(self) -> None:
        """Run the window main loop (blocks until closed)."""
        self._running = True

        # Start frame update loop
        self._root.after(100, self._update_frame)

        logger.info("Recording window started")
        self._root.mainloop()

    def run_async(self) -> threading.Thread:
        """Run the window in a separate thread.

        Returns:
            Thread running the window
        """
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def close(self) -> None:
        """Close the window programmatically."""
        if self._running:
            self._running = False
            try:
                self._root.quit()
                self._root.destroy()
            except tk.TclError:
                pass  # Window already destroyed
