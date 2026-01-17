"""Step collapsing for typing sequences.

This module collapses typing sequences (fast keyboard taps) into single
'type' steps before frame extraction and AI analysis. This improves the
approval UI by showing typing as a single action rather than individual taps.
"""

from dataclasses import dataclass
from typing import Any

from mutcli.core.typing_detector import TypingSequence


@dataclass
class CollapsedStep:
    """A collapsed step representing a user action.

    After collapsing, typing sequences become single 'type' steps while
    individual gestures (tap, swipe, long_press) remain separate steps.

    Attributes:
        index: Step number (1-based, sequential after collapse)
        action: Action type - "tap", "type", "swipe", or "long_press"
        timestamp: When action started (seconds from recording start)
        original_indices: Tuple of (start, end) indices in original touch_events
        coordinates: dict with x, y (for tap/long_press)
        start: dict with x, y for swipe start position
        end: dict with x, y for swipe end position
        direction: Swipe direction ("up", "down", "left", "right")
        duration_ms: Duration in milliseconds (for long_press)
        tap_count: Number of taps in typing sequence (for type)
        text: User-provided text for typing (for type)
    """

    index: int
    action: str
    timestamp: float
    original_indices: tuple[int, int]
    coordinates: dict[str, int] | None = None
    start: dict[str, int] | None = None
    end: dict[str, int] | None = None
    direction: str | None = None
    duration_ms: int | None = None
    tap_count: int | None = None
    text: str | None = None


def _calculate_direction(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
) -> str:
    """Calculate swipe direction from start and end coordinates.

    Determines the primary direction based on which axis has the larger
    absolute delta. Returns "up", "down", "left", or "right".

    Args:
        start_x: Starting X coordinate
        start_y: Starting Y coordinate
        end_x: Ending X coordinate
        end_y: Ending Y coordinate

    Returns:
        Direction string: "up", "down", "left", or "right"
    """
    delta_x = end_x - start_x
    delta_y = end_y - start_y

    # Determine primary direction based on larger absolute delta
    if abs(delta_y) >= abs(delta_x):
        # Vertical movement is dominant
        return "up" if delta_y < 0 else "down"
    else:
        # Horizontal movement is dominant
        return "left" if delta_x < 0 else "right"


def collapse_steps(
    touch_events: list[dict[str, Any]],
    typing_sequences: list[TypingSequence],
) -> list[CollapsedStep]:
    """Collapse touch events with typing sequences into steps.

    Merges typing sequences into single 'type' steps while preserving
    tap/swipe/long_press as individual steps. Steps are renumbered
    sequentially starting from 1.

    Args:
        touch_events: List of raw touch event dicts with keys:
            - x, y: coordinates
            - timestamp: seconds from recording start
            - gesture: "tap", "swipe", or "long_press"
            - end_x, end_y: for swipe gestures
            - duration_ms: for long_press gestures
        typing_sequences: List of TypingSequence objects identifying
            which touch event ranges are keyboard typing

    Returns:
        List of CollapsedStep objects with sequential indices
    """
    if not touch_events:
        return []

    # Build a set of indices covered by typing sequences
    # and a map from start index to sequence for quick lookup
    typing_ranges: dict[int, TypingSequence] = {}
    covered_indices: set[int] = set()

    for seq in typing_sequences:
        typing_ranges[seq.start_index] = seq
        for i in range(seq.start_index, seq.end_index + 1):
            covered_indices.add(i)

    steps: list[CollapsedStep] = []
    step_index = 1
    i = 0

    while i < len(touch_events):
        event = touch_events[i]

        # Check if this is the start of a typing sequence
        if i in typing_ranges:
            seq = typing_ranges[i]
            steps.append(CollapsedStep(
                index=step_index,
                action="type",
                timestamp=event["timestamp"],
                original_indices=(seq.start_index, seq.end_index),
                tap_count=seq.tap_count,
                text=seq.text,
            ))
            step_index += 1
            # Skip all events in this typing sequence
            i = seq.end_index + 1
            continue

        # Skip events that are part of a typing sequence (shouldn't happen
        # if we process correctly, but safety check)
        if i in covered_indices:
            i += 1
            continue

        # Process non-typing gesture
        gesture = event.get("gesture", "tap")

        if gesture == "tap":
            steps.append(CollapsedStep(
                index=step_index,
                action="tap",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                coordinates={"x": event["x"], "y": event["y"]},
            ))

        elif gesture == "swipe":
            start_x = event["x"]
            start_y = event["y"]
            end_x = event.get("end_x", start_x)
            end_y = event.get("end_y", start_y)
            direction = _calculate_direction(start_x, start_y, end_x, end_y)

            steps.append(CollapsedStep(
                index=step_index,
                action="swipe",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                start={"x": start_x, "y": start_y},
                end={"x": end_x, "y": end_y},
                direction=direction,
            ))

        elif gesture == "long_press":
            steps.append(CollapsedStep(
                index=step_index,
                action="long_press",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                coordinates={"x": event["x"], "y": event["y"]},
                duration_ms=event.get("duration_ms"),
            ))

        else:
            # Unknown gesture - treat as tap
            steps.append(CollapsedStep(
                index=step_index,
                action="tap",
                timestamp=event["timestamp"],
                original_indices=(i, i),
                coordinates={"x": event["x"], "y": event["y"]},
            ))

        step_index += 1
        i += 1

    return steps
