"""Touch injection and logging for recording sessions.

Converts mouse events to touch events, injects them via scrcpy,
and logs them for perfect coordinate accuracy.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from myscrcpy.core.control import Action

if TYPE_CHECKING:
    from mutcli.core.scrcpy_service import ScrcpyService

logger = logging.getLogger("mut.touch_injector")


@dataclass
class TrajectoryPoint:
    """A single point in a touch trajectory."""

    timestamp: float  # Seconds since recording started
    x: int  # Screen X coordinate
    y: int  # Screen Y coordinate


@dataclass
class InjectedTouchEvent:
    """A touch event that was injected and logged.

    Attributes:
        timestamp: Seconds since recording started (touch END time)
        x: End X coordinate in pixels
        y: End Y coordinate in pixels
        gesture: Type of gesture ("tap", "swipe", "long_press")
        duration_ms: Touch duration in milliseconds
        start_x: Start X coordinate
        start_y: Start Y coordinate
        trajectory: Full path of touch points (for swipes)
        path_distance: Total distance traveled along path in pixels
    """

    timestamp: float
    x: int
    y: int
    gesture: str
    duration_ms: int
    start_x: int
    start_y: int
    trajectory: list[TrajectoryPoint] = field(default_factory=list)
    path_distance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "x": self.x,
            "y": self.y,
            "gesture": self.gesture,
            "duration_ms": self.duration_ms,
            "start_x": self.start_x,
            "start_y": self.start_y,
            "path_distance": round(self.path_distance, 1),
        }
        # Include trajectory for swipes
        if self.gesture == "swipe" and self.trajectory:
            result["trajectory"] = [
                {"t": round(p.timestamp, 3), "x": p.x, "y": p.y}
                for p in self.trajectory
            ]
        return result


class TouchInjector:
    """Handles mouse-to-touch conversion, injection, and logging.

    Converts mouse events from the recording window into touch events,
    injects them to the device via scrcpy, and logs them with perfect
    coordinate accuracy.

    Gesture classification:
    - tap: duration < 200ms AND distance < 50px
    - long_press: duration >= 500ms AND distance < 100px
    - swipe: distance >= 100px

    Usage:
        injector = TouchInjector(scrcpy_service, start_time)
        # On mouse down:
        injector.on_mouse_down(x, y)
        # On mouse move (while pressed):
        injector.on_mouse_move(x, y)
        # On mouse up:
        injector.on_mouse_up(x, y)
        # Get logged events:
        events = injector.get_events()
    """

    # Gesture classification thresholds
    TAP_MAX_DURATION_MS = 200
    TAP_MAX_DISTANCE_PX = 50
    LONG_PRESS_MIN_DURATION_MS = 500
    SWIPE_MIN_DISTANCE_PX = 100

    def __init__(self, scrcpy: "ScrcpyService", start_time: float):
        """Initialize touch injector.

        Args:
            scrcpy: ScrcpyService instance with control enabled
            start_time: Recording start timestamp (time.time())
        """
        self._scrcpy = scrcpy
        self._start_time = start_time
        self._events: list[InjectedTouchEvent] = []

        # Current touch state
        self._touch_down = False
        self._touch_start_time: float | None = None
        self._touch_start_pos: tuple[int, int] | None = None
        self._trajectory: list[TrajectoryPoint] = []

    def on_mouse_down(self, x: int, y: int) -> None:
        """Handle mouse button press.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
        """
        if self._touch_down:
            # Already tracking a touch, ignore
            return

        self._touch_down = True
        self._touch_start_time = time.time()
        self._touch_start_pos = (x, y)

        # Start trajectory
        rel_time = time.time() - self._start_time
        self._trajectory = [TrajectoryPoint(rel_time, x, y)]

        # Inject touch down
        self._scrcpy.inject_touch(Action.DOWN.value, x, y)
        logger.debug(f"Touch DOWN at ({x}, {y})")

    def on_mouse_move(self, x: int, y: int) -> None:
        """Handle mouse movement while pressed.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
        """
        if not self._touch_down:
            return

        # Add to trajectory
        rel_time = time.time() - self._start_time
        self._trajectory.append(TrajectoryPoint(rel_time, x, y))

        # Inject touch move
        self._scrcpy.inject_touch(Action.MOVE.value, x, y)

    def on_mouse_up(self, x: int, y: int) -> None:
        """Handle mouse button release.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
        """
        if not self._touch_down:
            return

        # Inject touch up
        self._scrcpy.inject_touch(Action.RELEASE.value, x, y)
        logger.debug(f"Touch UP at ({x}, {y})")

        # Calculate gesture properties
        now = time.time()
        duration_ms = int((now - self._touch_start_time) * 1000) if self._touch_start_time else 0
        start_x, start_y = self._touch_start_pos or (x, y)
        path_distance = self._calculate_path_distance()
        gesture = self._classify_gesture(duration_ms, path_distance)

        # Create event
        event = InjectedTouchEvent(
            timestamp=now - self._start_time,
            x=x,
            y=y,
            gesture=gesture,
            duration_ms=duration_ms,
            start_x=start_x,
            start_y=start_y,
            trajectory=list(self._trajectory) if gesture == "swipe" else [],
            path_distance=path_distance,
        )
        self._events.append(event)

        logger.info(
            f"{gesture.upper()}: ({start_x},{start_y})->({x},{y}) "
            f"{duration_ms}ms path={path_distance:.0f}px"
        )

        # Reset state
        self._touch_down = False
        self._touch_start_time = None
        self._touch_start_pos = None
        self._trajectory = []

    def _calculate_path_distance(self) -> float:
        """Calculate total distance traveled along the trajectory path.

        Returns:
            Total path distance in pixels
        """
        if len(self._trajectory) < 2:
            return 0.0

        total_distance = 0.0
        for i in range(1, len(self._trajectory)):
            dx = self._trajectory[i].x - self._trajectory[i - 1].x
            dy = self._trajectory[i].y - self._trajectory[i - 1].y
            total_distance += math.sqrt(dx * dx + dy * dy)

        return total_distance

    def _classify_gesture(self, duration_ms: int, path_distance: float) -> str:
        """Classify touch gesture based on duration and path distance.

        Args:
            duration_ms: Touch duration in milliseconds
            path_distance: Total distance traveled along path in pixels

        Returns:
            Gesture type: "tap", "swipe", or "long_press"
        """
        if path_distance >= self.SWIPE_MIN_DISTANCE_PX:
            return "swipe"
        elif duration_ms >= self.LONG_PRESS_MIN_DURATION_MS:
            return "long_press"
        elif duration_ms < self.TAP_MAX_DURATION_MS and path_distance < self.TAP_MAX_DISTANCE_PX:
            return "tap"
        else:
            # Ambiguous case - default to tap
            return "tap"

    def get_events(self) -> list[InjectedTouchEvent]:
        """Get all logged events.

        Returns:
            Copy of the event list
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear all logged events."""
        self._events.clear()

    @property
    def event_count(self) -> int:
        """Get number of logged events."""
        return len(self._events)
