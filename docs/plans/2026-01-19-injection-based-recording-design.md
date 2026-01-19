# Injection-Based Touch Recording

**Date:** 2026-01-19
**Status:** Implementation

## Problem

Current touch capture via `adb getevent -lt` has reliability and coordinate accuracy issues:
- Device-specific touch panel coordinate ranges
- Complex scaling from raw touch panel to screen pixels
- Events can be missed or mis-parsed across different Android devices/versions

## Solution

Replace capture-based recording with injection-based recording:
- User interacts with a GUI window showing the mirrored screen
- Mouse events are converted to touch commands
- MUT injects touches via scrcpy control AND logs them
- Perfect accuracy: we define the coordinates we send

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RecordingWindow (tkinter)                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Live Screen Mirror                          ││
│  │           (updated from ScrcpyService frame buffer)      ││
│  │                                                          ││
│  │         User clicks/drags here → mouse events            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   TouchInjector        │
              │                        │
              │  1. Convert mouse→touch│
              │  2. Log touch event    │ ──→ touch_events.json
              │  3. Inject via scrcpy  │ ──→ Device receives touch
              └────────────────────────┘
```

## Components

### 1. ScrcpyService Changes

Enable control mode by passing `ControlArgs()` instead of `None`:

```python
from myscrcpy.core import Session, VideoArgs, ControlArgs

self._session = Session(
    device,
    video_args=VideoArgs(fps=60),
    control_args=ControlArgs(),  # Enable control
)
```

Add touch injection method:

```python
from myscrcpy.core.control import Action

def inject_touch(self, action: int, x: int, y: int, touch_id: int = 0) -> None:
    """Inject touch event to device.

    Args:
        action: Action.DOWN (0), Action.RELEASE (1), or Action.MOVE (2)
        x, y: Screen coordinates in pixels
        touch_id: Touch pointer ID for multi-touch
    """
    if self._session and self._session.ca:
        self._session.ca.f_touch(
            action=action,
            x=x,
            y=y,
            width=self._width,
            height=self._height,
            touch_id=touch_id,
        )
```

### 2. TouchInjector (new module)

Handles mouse-to-touch conversion and logging:

```python
@dataclass
class InjectedTouchEvent:
    timestamp: float      # Relative to recording start
    x: int                # Screen X coordinate
    y: int                # Screen Y coordinate
    gesture: str          # "tap", "swipe", "long_press"
    duration_ms: int      # Touch duration
    start_x: int          # Start X (for swipes)
    start_y: int          # Start Y (for swipes)
    trajectory: list      # Path points (for swipes)

class TouchInjector:
    def __init__(self, scrcpy: ScrcpyService, start_time: float):
        self._scrcpy = scrcpy
        self._start_time = start_time
        self._events: list[InjectedTouchEvent] = []

        # Current touch state
        self._touch_down = False
        self._touch_start_time: float | None = None
        self._touch_start_pos: tuple[int, int] | None = None
        self._trajectory: list[tuple[float, int, int]] = []

    def on_mouse_down(self, x: int, y: int) -> None:
        """Handle mouse button press."""
        self._touch_down = True
        self._touch_start_time = time.time()
        self._touch_start_pos = (x, y)
        self._trajectory = [(time.time() - self._start_time, x, y)]

        # Inject touch down
        self._scrcpy.inject_touch(Action.DOWN, x, y)

    def on_mouse_move(self, x: int, y: int) -> None:
        """Handle mouse movement while pressed."""
        if not self._touch_down:
            return

        self._trajectory.append((time.time() - self._start_time, x, y))

        # Inject touch move
        self._scrcpy.inject_touch(Action.MOVE, x, y)

    def on_mouse_up(self, x: int, y: int) -> None:
        """Handle mouse button release."""
        if not self._touch_down:
            return

        # Inject touch up
        self._scrcpy.inject_touch(Action.RELEASE, x, y)

        # Classify and record gesture
        duration_ms = int((time.time() - self._touch_start_time) * 1000)
        start_x, start_y = self._touch_start_pos
        path_distance = self._calculate_path_distance()
        gesture = self._classify_gesture(duration_ms, path_distance)

        event = InjectedTouchEvent(
            timestamp=time.time() - self._start_time,
            x=x, y=y,
            gesture=gesture,
            duration_ms=duration_ms,
            start_x=start_x, start_y=start_y,
            trajectory=self._trajectory if gesture == "swipe" else [],
        )
        self._events.append(event)

        # Reset state
        self._touch_down = False
        self._touch_start_time = None
        self._touch_start_pos = None
        self._trajectory = []

    def get_events(self) -> list[InjectedTouchEvent]:
        return list(self._events)
```

### 3. RecordingWindow (new module)

Tkinter window for visual interaction:

```python
class RecordingWindow:
    def __init__(
        self,
        scrcpy: ScrcpyService,
        injector: TouchInjector,
        title: str = "MUT Recording",
    ):
        self._scrcpy = scrcpy
        self._injector = injector

        self._root = tk.Tk()
        self._root.title(title)

        # Canvas for screen display
        self._canvas = tk.Canvas(self._root)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events
        self._canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self._canvas.bind("<B1-Motion>", self._on_mouse_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Start frame update loop
        self._update_frame()

    def _on_mouse_down(self, event):
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_down(x, y)

    def _on_mouse_move(self, event):
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_move(x, y)

    def _on_mouse_up(self, event):
        x, y = self._canvas_to_screen(event.x, event.y)
        self._injector.on_mouse_up(x, y)

    def _canvas_to_screen(self, cx: int, cy: int) -> tuple[int, int]:
        """Convert canvas coordinates to device screen coordinates."""
        # Account for scaling between canvas and actual screen
        scale_x = self._screen_width / self._canvas.winfo_width()
        scale_y = self._screen_height / self._canvas.winfo_height()
        return int(cx * scale_x), int(cy * scale_y)

    def _update_frame(self):
        """Update canvas with latest frame from scrcpy."""
        try:
            frame = self._scrcpy.get_latest_frame()
            # Convert to PhotoImage and display
            # ...
        except:
            pass
        self._root.after(33, self._update_frame)  # ~30fps

    def run(self):
        self._root.mainloop()

    def close(self):
        self._root.quit()
```

### 4. Recorder Integration

Update `Recorder` to use injection-based flow:

```python
class Recorder:
    def start(self) -> dict:
        # Connect with control enabled
        self._scrcpy = ScrcpyService(self._device_id, enable_control=True)
        self._scrcpy.connect()

        # Start video recording
        self._scrcpy.start_recording(video_path)

        # Create touch injector
        self._injector = TouchInjector(self._scrcpy, time.time())

        # Open recording window (blocks until closed)
        self._window = RecordingWindow(self._scrcpy, self._injector)
        # Window runs in separate thread or we handle it differently

    def stop(self) -> dict:
        # Get logged events (perfect accuracy!)
        events = self._injector.get_events()

        # Save to touch_events.json
        # ...
```

## File Changes

| File | Change |
|------|--------|
| `mutcli/core/scrcpy_service.py` | Add `inject_touch()`, enable control mode |
| `mutcli/core/touch_injector.py` | New - mouse→touch conversion and logging |
| `mutcli/core/recording_window.py` | New - tkinter GUI for recording |
| `mutcli/core/recorder.py` | Use injection flow instead of getevent |
| `mutcli/core/touch_monitor.py` | Keep for backward compat, mark deprecated |

## Benefits

| Before (getevent) | After (injection) |
|-------------------|-------------------|
| Device-specific coordinate scaling | Exact coordinates - we define them |
| Can miss events | 100% reliable - we log what we send |
| Complex parsing | Simple mouse→touch mapping |
| Timing sync issues | Perfect sync - inject time = log time |

## Implementation Steps

1. Add `inject_touch()` to ScrcpyService
2. Create TouchInjector class
3. Create RecordingWindow class
4. Update Recorder to use new flow
5. Test with real device
6. Deprecate TouchMonitor (keep for now)
