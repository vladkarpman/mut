"""Tests for TypingDetector."""

import pytest

from mutcli.core.typing_detector import TypingDetector, TypingSequence


class TestTypingSequence:
    """Test TypingSequence dataclass."""

    def test_creation_without_text(self):
        """TypingSequence should store all fields correctly without text."""
        seq = TypingSequence(
            start_index=1,
            end_index=4,
            tap_count=4,
            duration=0.9,
        )

        assert seq.start_index == 1
        assert seq.end_index == 4
        assert seq.tap_count == 4
        assert seq.duration == 0.9
        assert seq.text is None

    def test_creation_with_text(self):
        """TypingSequence should store text when provided."""
        seq = TypingSequence(
            start_index=0,
            end_index=5,
            tap_count=6,
            duration=1.5,
            text="hello",
        )

        assert seq.text == "hello"


class TestTypingDetectorInitialization:
    """Test TypingDetector initialization."""

    def test_stores_screen_height(self):
        """Should store screen height for keyboard detection."""
        detector = TypingDetector(screen_height=2400)

        assert detector._screen_height == 2400

    def test_class_constants(self):
        """Should have correct class constants."""
        assert TypingDetector.KEYBOARD_THRESHOLD == 0.4
        assert TypingDetector.MAX_TAP_INTERVAL == 1.0
        assert TypingDetector.MIN_SEQUENCE_LENGTH == 3


class TestIsKeyboardTap:
    """Test is_keyboard_tap method."""

    def test_tap_in_keyboard_area_returns_true(self):
        """Tap in bottom 40% should return True."""
        detector = TypingDetector(screen_height=2400)
        # Keyboard area: y > 1440 (60% of 2400)

        assert detector.is_keyboard_tap(1800) is True
        assert detector.is_keyboard_tap(2400) is True
        assert detector.is_keyboard_tap(1441) is True

    def test_tap_outside_keyboard_area_returns_false(self):
        """Tap outside bottom 40% should return False."""
        detector = TypingDetector(screen_height=2400)
        # Non-keyboard area: y <= 1440

        assert detector.is_keyboard_tap(500) is False
        assert detector.is_keyboard_tap(1200) is False
        assert detector.is_keyboard_tap(1440) is False

    def test_tap_at_boundary(self):
        """Tap exactly at boundary should return False."""
        detector = TypingDetector(screen_height=2400)
        # Boundary is at y = 1440 (60% of 2400)

        # At boundary - should be False (keyboard area is y > threshold)
        assert detector.is_keyboard_tap(1440) is False

    def test_different_screen_heights(self):
        """Should work with different screen heights."""
        # Screen height 1000: keyboard area y > 600
        detector = TypingDetector(screen_height=1000)

        assert detector.is_keyboard_tap(601) is True
        assert detector.is_keyboard_tap(600) is False

        # Screen height 1920: keyboard area y > 1152
        detector2 = TypingDetector(screen_height=1920)

        assert detector2.is_keyboard_tap(1153) is True
        assert detector2.is_keyboard_tap(1152) is False


class TestDetectTypingSequences:
    """Test detect method for finding typing sequences."""

    def test_detects_typing_in_bottom_40_percent(self):
        """Should detect typing when taps are in keyboard area."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 100, "y": 500, "timestamp": 0.0},    # Non-keyboard tap
            {"x": 200, "y": 1800, "timestamp": 1.0},   # Keyboard tap 1
            {"x": 300, "y": 1850, "timestamp": 1.3},   # Keyboard tap 2
            {"x": 250, "y": 1900, "timestamp": 1.6},   # Keyboard tap 3
            {"x": 280, "y": 1820, "timestamp": 1.9},   # Keyboard tap 4
            {"x": 400, "y": 600, "timestamp": 2.5},    # Non-keyboard tap
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 1
        seq = sequences[0]
        assert seq.start_index == 1
        assert seq.end_index == 4
        assert seq.tap_count == 4
        assert seq.duration == pytest.approx(0.9, abs=0.01)

    def test_requires_minimum_3_consecutive_keyboard_taps(self):
        """Should not detect sequence with less than 3 keyboard taps."""
        detector = TypingDetector(screen_height=2400)

        # Only 2 keyboard taps
        touch_events = [
            {"x": 100, "y": 500, "timestamp": 0.0},    # Non-keyboard
            {"x": 200, "y": 1800, "timestamp": 1.0},   # Keyboard tap 1
            {"x": 300, "y": 1850, "timestamp": 1.3},   # Keyboard tap 2
            {"x": 400, "y": 600, "timestamp": 2.0},    # Non-keyboard
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 0

    def test_splits_sequences_on_time_gap(self):
        """Should split sequences when gap > 1s between taps."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            # First sequence
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 0.3},
            {"x": 250, "y": 1900, "timestamp": 0.6},
            # Gap > 1s
            # Second sequence
            {"x": 280, "y": 1820, "timestamp": 2.0},
            {"x": 320, "y": 1860, "timestamp": 2.3},
            {"x": 290, "y": 1840, "timestamp": 2.6},
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 2
        assert sequences[0].start_index == 0
        assert sequences[0].end_index == 2
        assert sequences[0].tap_count == 3
        assert sequences[1].start_index == 3
        assert sequences[1].end_index == 5
        assert sequences[1].tap_count == 3

    def test_ends_sequence_on_non_keyboard_tap(self):
        """Should end sequence when non-keyboard tap occurs."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},   # Keyboard
            {"x": 300, "y": 1850, "timestamp": 0.3},   # Keyboard
            {"x": 250, "y": 1900, "timestamp": 0.6},   # Keyboard
            {"x": 400, "y": 500, "timestamp": 0.9},    # Non-keyboard (ends seq)
            {"x": 280, "y": 1820, "timestamp": 1.2},   # Keyboard (new potential)
            {"x": 320, "y": 1860, "timestamp": 1.5},   # Keyboard
        ]

        sequences = detector.detect(touch_events)

        # Only first sequence of 3 taps should be detected
        # Second potential sequence only has 2 taps
        assert len(sequences) == 1
        assert sequences[0].end_index == 2
        assert sequences[0].tap_count == 3

    def test_returns_empty_list_when_no_typing(self):
        """Should return empty list when no typing detected."""
        detector = TypingDetector(screen_height=2400)

        # All taps outside keyboard area
        touch_events = [
            {"x": 100, "y": 500, "timestamp": 0.0},
            {"x": 200, "y": 600, "timestamp": 1.0},
            {"x": 300, "y": 700, "timestamp": 2.0},
        ]

        sequences = detector.detect(touch_events)

        assert sequences == []

    def test_handles_empty_touch_events(self):
        """Should handle empty touch events list."""
        detector = TypingDetector(screen_height=2400)

        sequences = detector.detect([])

        assert sequences == []

    def test_handles_single_tap(self):
        """Should handle single tap (no sequence possible)."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},
        ]

        sequences = detector.detect(touch_events)

        assert sequences == []

    def test_detects_multiple_separate_sequences(self):
        """Should detect multiple separate typing sequences."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            # First typing sequence
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 0.2},
            {"x": 250, "y": 1900, "timestamp": 0.4},
            # Non-keyboard tap
            {"x": 400, "y": 500, "timestamp": 1.0},
            # Second typing sequence
            {"x": 280, "y": 1820, "timestamp": 2.0},
            {"x": 320, "y": 1860, "timestamp": 2.2},
            {"x": 290, "y": 1840, "timestamp": 2.4},
            {"x": 310, "y": 1880, "timestamp": 2.6},
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 2

        assert sequences[0].start_index == 0
        assert sequences[0].end_index == 2
        assert sequences[0].tap_count == 3

        assert sequences[1].start_index == 4
        assert sequences[1].end_index == 7
        assert sequences[1].tap_count == 4

    def test_text_field_is_none_by_default(self):
        """Detected sequences should have text=None."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 0.3},
            {"x": 250, "y": 1900, "timestamp": 0.6},
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 1
        assert sequences[0].text is None

    def test_sequence_at_end_of_events(self):
        """Should detect sequence that ends at last event."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 100, "y": 500, "timestamp": 0.0},    # Non-keyboard
            {"x": 200, "y": 1800, "timestamp": 1.0},   # Keyboard
            {"x": 300, "y": 1850, "timestamp": 1.3},   # Keyboard
            {"x": 250, "y": 1900, "timestamp": 1.6},   # Keyboard (last)
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 1
        assert sequences[0].start_index == 1
        assert sequences[0].end_index == 3
        assert sequences[0].tap_count == 3

    def test_all_events_are_keyboard_taps(self):
        """Should detect when all events are keyboard taps."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 0.3},
            {"x": 250, "y": 1900, "timestamp": 0.6},
            {"x": 280, "y": 1820, "timestamp": 0.9},
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 1
        assert sequences[0].start_index == 0
        assert sequences[0].end_index == 3
        assert sequences[0].tap_count == 4

    def test_gap_exactly_at_threshold(self):
        """Gap exactly at 1.0s should still be part of same sequence."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 1.0},   # Exactly 1s gap
            {"x": 250, "y": 1900, "timestamp": 2.0},   # Exactly 1s gap
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 1
        assert sequences[0].tap_count == 3

    def test_gap_just_over_threshold(self):
        """Gap just over 1.0s should split sequences."""
        detector = TypingDetector(screen_height=2400)

        touch_events = [
            {"x": 200, "y": 1800, "timestamp": 0.0},
            {"x": 300, "y": 1850, "timestamp": 0.5},
            {"x": 250, "y": 1900, "timestamp": 1.0},
            {"x": 280, "y": 1820, "timestamp": 2.01},  # 1.01s gap - splits
            {"x": 320, "y": 1860, "timestamp": 2.5},
            {"x": 290, "y": 1840, "timestamp": 3.0},
        ]

        sequences = detector.detect(touch_events)

        assert len(sequences) == 2
