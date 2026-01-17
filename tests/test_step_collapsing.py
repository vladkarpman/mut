"""Tests for step collapsing module."""

from mutcli.core.step_collapsing import (
    CollapsedStep,
    _calculate_direction,
    collapse_steps,
)
from mutcli.core.typing_detector import TypingSequence


class TestCollapsedStep:
    """Test CollapsedStep dataclass."""

    def test_tap_step_creation(self):
        """CollapsedStep should store tap step fields correctly."""
        step = CollapsedStep(
            index=1,
            action="tap",
            timestamp=1.5,
            original_indices=(0, 0),
            coordinates={"x": 540, "y": 1200},
        )

        assert step.index == 1
        assert step.action == "tap"
        assert step.timestamp == 1.5
        assert step.original_indices == (0, 0)
        assert step.coordinates == {"x": 540, "y": 1200}
        # Defaults for non-tap fields
        assert step.start is None
        assert step.end is None
        assert step.direction is None
        assert step.duration_ms is None
        assert step.tap_count is None
        assert step.text is None

    def test_type_step_creation(self):
        """CollapsedStep should store type step fields correctly."""
        step = CollapsedStep(
            index=2,
            action="type",
            timestamp=2.0,
            original_indices=(1, 5),
            tap_count=5,
            text="hello",
        )

        assert step.index == 2
        assert step.action == "type"
        assert step.original_indices == (1, 5)
        assert step.tap_count == 5
        assert step.text == "hello"
        assert step.coordinates is None

    def test_swipe_step_creation(self):
        """CollapsedStep should store swipe step fields correctly."""
        step = CollapsedStep(
            index=3,
            action="swipe",
            timestamp=3.0,
            original_indices=(6, 6),
            start={"x": 540, "y": 1500},
            end={"x": 540, "y": 500},
            direction="up",
        )

        assert step.action == "swipe"
        assert step.start == {"x": 540, "y": 1500}
        assert step.end == {"x": 540, "y": 500}
        assert step.direction == "up"

    def test_long_press_step_creation(self):
        """CollapsedStep should store long_press step fields correctly."""
        step = CollapsedStep(
            index=4,
            action="long_press",
            timestamp=4.0,
            original_indices=(7, 7),
            coordinates={"x": 300, "y": 800},
            duration_ms=1500,
        )

        assert step.action == "long_press"
        assert step.coordinates == {"x": 300, "y": 800}
        assert step.duration_ms == 1500


class TestCalculateDirection:
    """Test _calculate_direction helper function."""

    def test_swipe_up(self):
        """Should detect upward swipe (y decreases significantly)."""
        # Swipe from bottom to top
        direction = _calculate_direction(540, 1500, 540, 500)
        assert direction == "up"

    def test_swipe_down(self):
        """Should detect downward swipe (y increases significantly)."""
        direction = _calculate_direction(540, 500, 540, 1500)
        assert direction == "down"

    def test_swipe_left(self):
        """Should detect leftward swipe (x decreases significantly)."""
        direction = _calculate_direction(800, 1000, 200, 1000)
        assert direction == "left"

    def test_swipe_right(self):
        """Should detect rightward swipe (x increases significantly)."""
        direction = _calculate_direction(200, 1000, 800, 1000)
        assert direction == "right"

    def test_diagonal_swipe_predominantly_vertical(self):
        """Diagonal swipe with larger y delta should be up/down."""
        # More y movement than x movement
        direction = _calculate_direction(540, 1500, 600, 500)
        assert direction == "up"

    def test_diagonal_swipe_predominantly_horizontal(self):
        """Diagonal swipe with larger x delta should be left/right."""
        # More x movement than y movement
        direction = _calculate_direction(200, 1000, 800, 950)
        assert direction == "right"


class TestCollapseStepsNoTyping:
    """Test collapse_steps with no typing sequences."""

    def test_no_typing_sequences_returns_all_taps(self):
        """When no typing sequences, all taps should be preserved as-is."""
        touch_events = [
            {"x": 540, "y": 1200, "timestamp": 1.0, "gesture": "tap"},
            {"x": 600, "y": 800, "timestamp": 2.0, "gesture": "tap"},
            {"x": 300, "y": 600, "timestamp": 3.0, "gesture": "tap"},
        ]
        typing_sequences: list[TypingSequence] = []

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 3
        assert all(s.action == "tap" for s in steps)
        assert steps[0].index == 1
        assert steps[1].index == 2
        assert steps[2].index == 3
        assert steps[0].coordinates == {"x": 540, "y": 1200}
        assert steps[1].coordinates == {"x": 600, "y": 800}
        assert steps[2].coordinates == {"x": 300, "y": 600}

    def test_empty_touch_events_returns_empty_list(self):
        """Empty touch events should return empty list."""
        steps = collapse_steps([], [])
        assert steps == []


class TestCollapseStepsWithTyping:
    """Test collapse_steps with typing sequences."""

    def test_typing_sequence_collapsed_into_single_step(self):
        """Typing sequence should become single 'type' step."""
        touch_events = [
            {"x": 540, "y": 500, "timestamp": 0.5, "gesture": "tap"},   # Regular tap
            {"x": 200, "y": 1800, "timestamp": 1.0, "gesture": "tap"},  # Typing start
            {"x": 250, "y": 1850, "timestamp": 1.2, "gesture": "tap"},  # Typing
            {"x": 300, "y": 1820, "timestamp": 1.4, "gesture": "tap"},  # Typing
            {"x": 280, "y": 1860, "timestamp": 1.6, "gesture": "tap"},  # Typing end
            {"x": 540, "y": 600, "timestamp": 2.0, "gesture": "tap"},   # Regular tap
        ]
        typing_sequences = [
            TypingSequence(
                start_index=1,
                end_index=4,
                tap_count=4,
                duration=0.6,
                text="test",
            )
        ]

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 3  # tap, type, tap
        assert steps[0].action == "tap"
        assert steps[0].index == 1
        assert steps[0].coordinates == {"x": 540, "y": 500}

        assert steps[1].action == "type"
        assert steps[1].index == 2
        assert steps[1].original_indices == (1, 4)
        assert steps[1].tap_count == 4
        assert steps[1].text == "test"
        assert steps[1].timestamp == 1.0  # First tap of sequence

        assert steps[2].action == "tap"
        assert steps[2].index == 3
        assert steps[2].coordinates == {"x": 540, "y": 600}

    def test_multiple_typing_sequences_collapsed(self):
        """Multiple typing sequences should each become single step."""
        touch_events = [
            # First typing sequence (indices 0-2)
            {"x": 200, "y": 1800, "timestamp": 0.0, "gesture": "tap"},
            {"x": 250, "y": 1850, "timestamp": 0.2, "gesture": "tap"},
            {"x": 300, "y": 1820, "timestamp": 0.4, "gesture": "tap"},
            # Regular tap (index 3)
            {"x": 540, "y": 500, "timestamp": 1.0, "gesture": "tap"},
            # Second typing sequence (indices 4-6)
            {"x": 200, "y": 1800, "timestamp": 2.0, "gesture": "tap"},
            {"x": 250, "y": 1850, "timestamp": 2.2, "gesture": "tap"},
            {"x": 300, "y": 1820, "timestamp": 2.4, "gesture": "tap"},
        ]
        typing_sequences = [
            TypingSequence(start_index=0, end_index=2, tap_count=3, duration=0.4, text="abc"),
            TypingSequence(start_index=4, end_index=6, tap_count=3, duration=0.4, text="def"),
        ]

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 3  # type, tap, type
        assert steps[0].action == "type"
        assert steps[0].text == "abc"
        assert steps[0].index == 1

        assert steps[1].action == "tap"
        assert steps[1].index == 2

        assert steps[2].action == "type"
        assert steps[2].text == "def"
        assert steps[2].index == 3


class TestCollapseStepsWithSwipe:
    """Test collapse_steps preserves swipe gestures."""

    def test_swipe_gesture_preserved(self):
        """Swipe gestures should preserve start/end coords and direction."""
        touch_events = [
            {"x": 540, "y": 500, "timestamp": 1.0, "gesture": "tap"},
            {
                "x": 540, "y": 1500, "end_x": 540, "end_y": 500,
                "timestamp": 2.0, "gesture": "swipe", "duration_ms": 300
            },
            {"x": 300, "y": 600, "timestamp": 3.0, "gesture": "tap"},
        ]
        typing_sequences: list[TypingSequence] = []

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 3
        assert steps[1].action == "swipe"
        assert steps[1].index == 2
        assert steps[1].start == {"x": 540, "y": 1500}
        assert steps[1].end == {"x": 540, "y": 500}
        assert steps[1].direction == "up"
        assert steps[1].original_indices == (1, 1)


class TestCollapseStepsWithLongPress:
    """Test collapse_steps preserves long_press gestures."""

    def test_long_press_includes_duration(self):
        """Long press should include duration_ms."""
        touch_events = [
            {"x": 540, "y": 500, "timestamp": 1.0, "gesture": "tap"},
            {
                "x": 300, "y": 800, "timestamp": 2.0,
                "gesture": "long_press", "duration_ms": 1500
            },
            {"x": 600, "y": 900, "timestamp": 4.0, "gesture": "tap"},
        ]
        typing_sequences: list[TypingSequence] = []

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 3
        assert steps[1].action == "long_press"
        assert steps[1].index == 2
        assert steps[1].coordinates == {"x": 300, "y": 800}
        assert steps[1].duration_ms == 1500
        assert steps[1].original_indices == (1, 1)


class TestIndicesRenumbering:
    """Test that indices are renumbered sequentially after collapse."""

    def test_indices_renumbered_after_collapse(self):
        """After collapsing, indices should be sequential starting from 1."""
        touch_events = [
            # Typing sequence (indices 0-4)
            {"x": 200, "y": 1800, "timestamp": 0.0, "gesture": "tap"},
            {"x": 250, "y": 1850, "timestamp": 0.1, "gesture": "tap"},
            {"x": 300, "y": 1820, "timestamp": 0.2, "gesture": "tap"},
            {"x": 280, "y": 1860, "timestamp": 0.3, "gesture": "tap"},
            {"x": 320, "y": 1840, "timestamp": 0.4, "gesture": "tap"},
            # Regular taps (indices 5, 6)
            {"x": 540, "y": 500, "timestamp": 1.0, "gesture": "tap"},
            {"x": 600, "y": 600, "timestamp": 2.0, "gesture": "tap"},
        ]
        typing_sequences = [
            TypingSequence(start_index=0, end_index=4, tap_count=5, duration=0.4, text="hello")
        ]

        steps = collapse_steps(touch_events, typing_sequences)

        # 5 keyboard taps -> 1 type step, 2 regular taps -> 3 total steps
        assert len(steps) == 3
        assert steps[0].index == 1
        assert steps[1].index == 2
        assert steps[2].index == 3

    def test_original_indices_track_source_events(self):
        """original_indices should track which raw events contributed to step."""
        touch_events = [
            {"x": 540, "y": 500, "timestamp": 0.5, "gesture": "tap"},   # index 0
            {"x": 200, "y": 1800, "timestamp": 1.0, "gesture": "tap"},  # index 1
            {"x": 250, "y": 1850, "timestamp": 1.2, "gesture": "tap"},  # index 2
            {"x": 300, "y": 1820, "timestamp": 1.4, "gesture": "tap"},  # index 3
        ]
        typing_sequences = [
            TypingSequence(start_index=1, end_index=3, tap_count=3, duration=0.4)
        ]

        steps = collapse_steps(touch_events, typing_sequences)

        assert len(steps) == 2
        # First step: single tap at index 0
        assert steps[0].original_indices == (0, 0)
        # Second step: typing spanning indices 1-3
        assert steps[1].original_indices == (1, 3)
