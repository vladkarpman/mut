"""Typing detection from touch events."""

from dataclasses import dataclass


@dataclass
class TypingSequence:
    """A detected typing sequence from touch events.

    Attributes:
        start_index: Index of first tap in sequence
        end_index: Index of last tap in sequence (inclusive)
        tap_count: Number of taps in the sequence
        duration: Total duration in seconds
        text: User-provided text (filled later via interview)
    """

    start_index: int
    end_index: int
    tap_count: int
    duration: float
    text: str | None = None


class TypingDetector:
    """Detect keyboard typing sequences from touch events.

    Identifies when users are typing on the keyboard by analyzing
    touch event patterns. Typing is detected when:
    - Taps occur in the bottom 40% of the screen (keyboard area)
    - Taps occur within 1 second of each other
    - At least 3 consecutive keyboard taps form a sequence

    Usage:
        detector = TypingDetector(screen_height=2400)
        sequences = detector.detect(touch_events)
        for seq in sequences:
            print(f"Typing at taps {seq.start_index}-{seq.end_index}")
    """

    KEYBOARD_THRESHOLD = 0.4  # Bottom 40% of screen
    MAX_TAP_INTERVAL = 1.0    # Max seconds between keyboard taps
    MIN_SEQUENCE_LENGTH = 3   # Minimum taps to consider typing

    def __init__(self, screen_height: int):
        """Initialize with screen height for keyboard detection.

        Args:
            screen_height: Screen height in pixels
        """
        self._screen_height = screen_height

    def is_keyboard_tap(self, y: int) -> bool:
        """Check if Y coordinate is in keyboard area (bottom 40%).

        Args:
            y: Y coordinate in pixels

        Returns:
            True if tap is in keyboard area, False otherwise
        """
        keyboard_boundary = self._screen_height * (1 - self.KEYBOARD_THRESHOLD)
        return y > keyboard_boundary

    def detect(self, touch_events: list[dict]) -> list[TypingSequence]:
        """Detect typing sequences in touch events.

        Analyzes touch events to find sequences of keyboard taps.
        A sequence is defined as 3+ consecutive taps in the keyboard
        area with <= 1 second between each tap.

        Args:
            touch_events: List of dicts with 'x', 'y', 'timestamp' keys

        Returns:
            List of detected TypingSequence objects
        """
        if not touch_events:
            return []

        sequences: list[TypingSequence] = []
        current_sequence_start: int | None = None
        prev_timestamp: float | None = None

        for i, event in enumerate(touch_events):
            y = event["y"]
            timestamp = event["timestamp"]

            is_keyboard = self.is_keyboard_tap(y)
            time_gap_ok = (
                prev_timestamp is None
                or timestamp - prev_timestamp <= self.MAX_TAP_INTERVAL
            )

            if is_keyboard and time_gap_ok:
                # Continue or start a keyboard sequence
                if current_sequence_start is None:
                    current_sequence_start = i
                prev_timestamp = timestamp
            else:
                # Sequence ends (non-keyboard tap or time gap)
                if current_sequence_start is not None:
                    sequence = self._create_sequence(
                        touch_events, current_sequence_start, i - 1
                    )
                    if sequence is not None:
                        sequences.append(sequence)
                    current_sequence_start = None

                # If this is a keyboard tap with time gap, start new potential sequence
                if is_keyboard:
                    current_sequence_start = i
                    prev_timestamp = timestamp
                else:
                    prev_timestamp = None

        # Handle sequence at end of events
        if current_sequence_start is not None:
            sequence = self._create_sequence(
                touch_events, current_sequence_start, len(touch_events) - 1
            )
            if sequence is not None:
                sequences.append(sequence)

        return sequences

    def _create_sequence(
        self,
        touch_events: list[dict],
        start_index: int,
        end_index: int,
    ) -> TypingSequence | None:
        """Create a TypingSequence if it meets minimum length requirement.

        Args:
            touch_events: List of touch event dicts
            start_index: Index of first tap in sequence
            end_index: Index of last tap in sequence (inclusive)

        Returns:
            TypingSequence if valid, None if too short
        """
        tap_count = end_index - start_index + 1

        if tap_count < self.MIN_SEQUENCE_LENGTH:
            return None

        start_timestamp = touch_events[start_index]["timestamp"]
        end_timestamp = touch_events[end_index]["timestamp"]
        duration = end_timestamp - start_timestamp

        return TypingSequence(
            start_index=start_index,
            end_index=end_index,
            tap_count=tap_count,
            duration=duration,
        )
