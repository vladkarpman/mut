"""Tests for VerificationSuggester."""

from unittest.mock import MagicMock

from mutcli.core.step_analyzer import AnalyzedStep
from mutcli.core.verification_suggester import VerificationPoint, VerificationSuggester


class TestVerificationPoint:
    """Test VerificationPoint dataclass."""

    def test_creation_with_all_fields(self):
        """VerificationPoint should store all fields correctly."""
        point = VerificationPoint(
            after_step_index=2,
            description="Login successful, dashboard displayed",
            confidence=0.9,
            reason="Form submission detected (tapped 'Login')",
        )

        assert point.after_step_index == 2
        assert point.description == "Login successful, dashboard displayed"
        assert point.confidence == 0.9
        assert point.reason == "Form submission detected (tapped 'Login')"

    def test_confidence_range(self):
        """Confidence should be between 0.0 and 1.0."""
        point_low = VerificationPoint(
            after_step_index=0,
            description="Screen loaded",
            confidence=0.0,
            reason="Low confidence",
        )
        point_high = VerificationPoint(
            after_step_index=1,
            description="Button tapped",
            confidence=1.0,
            reason="High confidence",
        )

        assert point_low.confidence == 0.0
        assert point_high.confidence == 1.0


class TestVerificationSuggesterInitialization:
    """Test VerificationSuggester initialization."""

    def test_stores_ai_analyzer(self):
        """Should store AIAnalyzer instance."""
        mock_ai = MagicMock()

        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        assert suggester._ai_analyzer is mock_ai


class TestSuggestAfterFormSubmission:
    """Test verification suggestion after form submission."""

    def test_suggests_verification_after_login_button(self):
        """Should suggest verification after tapping 'Login' button."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Email",
                before_description="Login form displayed",
                after_description="Email field focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300, "timestamp": 1.0},
                element_text="Password",
                before_description="Email entered",
                after_description="Password field focused",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=2,
                original_tap={"x": 200, "y": 400, "timestamp": 2.0},
                element_text="Login",
                before_description="Password entered",
                after_description="Loading spinner visible",
                suggested_verification="User logged in successfully",
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should suggest verification after the Login button tap
        assert len(suggestions) >= 1
        login_suggestion = next(
            (s for s in suggestions if s.after_step_index == 2), None
        )
        assert login_suggestion is not None
        assert login_suggestion.confidence > 0.5
        reason_lower = login_suggestion.reason.lower()
        assert "form" in reason_lower or "login" in reason_lower

    def test_suggests_verification_after_submit_button(self):
        """Should suggest verification after tapping 'Submit' button."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 500, "timestamp": 0.0},
                element_text="Submit",
                before_description="Form filled out",
                after_description="Form submitted",
                suggested_verification="Form submission successful",
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1
        submit_suggestion = next(
            (s for s in suggestions if s.after_step_index == 0), None
        )
        assert submit_suggestion is not None
        assert submit_suggestion.confidence > 0.5

    def test_suggests_verification_after_sign_in_button(self):
        """Should suggest verification after tapping 'Sign In' button."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 500, "timestamp": 0.0},
                element_text="Sign In",
                before_description="Login screen",
                after_description="Dashboard displayed",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1
        assert suggestions[0].after_step_index == 0


class TestFormSubmissionEdgeCases:
    """Test form submission edge cases."""

    def test_no_suggestion_when_element_text_is_none(self):
        """Should not suggest form submission when element_text is None."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 500, "timestamp": 0.0},
                element_text=None,  # No element text
                before_description="Form screen",
                after_description="Form modified",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should not suggest form submission since element_text is None
        form_suggestions = [
            s for s in suggestions if "form" in s.reason.lower()
        ]
        assert len(form_suggestions) == 0


class TestSuggestOnNavigationChange:
    """Test verification suggestion on navigation change."""

    def test_suggests_verification_on_screen_transition(self):
        """Should suggest verification when screen changes significantly."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 100, "timestamp": 0.0},
                element_text="Settings",
                before_description="Home screen with menu",
                after_description="Settings screen displayed",
                suggested_verification="Settings screen loaded",
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should suggest verification after navigation to Settings
        assert len(suggestions) >= 1
        nav_suggestion = next(
            (s for s in suggestions if s.after_step_index == 0), None
        )
        assert nav_suggestion is not None
        reason_lower = nav_suggestion.reason.lower()
        assert "navigation" in reason_lower or "screen" in reason_lower

    def test_suggests_verification_when_title_changes(self):
        """Should suggest verification when screen title/header changes."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 100, "timestamp": 0.0},
                element_text="Profile",
                before_description="Dashboard with title 'Home'",
                after_description="Profile screen with title 'My Profile'",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1


class TestSuggestAfterLongPause:
    """Test verification suggestion after long pause."""

    def test_suggests_verification_after_long_pause(self):
        """Should suggest verification when > 2 seconds pause before next tap."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        # Use element names that don't trigger form submission detection
        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Item 1",  # Not a form submission keyword
                before_description="List view",
                after_description="Item details",  # Not a flow completion keyword
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300, "timestamp": 5.0},  # 5 second pause
                element_text="Back",
                before_description="Item details",
                after_description="List view",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should suggest verification after step 0 due to long pause before step 1
        pause_suggestion = next(
            (s for s in suggestions if s.after_step_index == 0), None
        )
        assert pause_suggestion is not None
        assert "pause" in pause_suggestion.reason.lower()

    def test_no_suggestion_for_short_pause(self):
        """Should not suggest verification for pauses < 2 seconds."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Button1",
                before_description="Screen A",
                after_description="Screen A modified",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300, "timestamp": 0.5},  # 0.5 second pause
                element_text="Button2",
                before_description="Screen A modified",
                after_description="Screen A more modified",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should not suggest verification based on pause for step 0
        pause_suggestions = [
            s for s in suggestions
            if s.after_step_index == 0 and "pause" in s.reason.lower()
        ]
        assert len(pause_suggestions) == 0

    def test_no_pause_suggestion_when_timestamps_missing(self):
        """Should not suggest pause verification when timestamps are missing."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200},  # No timestamp
                element_text="Item 1",
                before_description="List view",
                after_description="Item details",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300},  # No timestamp
                element_text="Back",
                before_description="Item details",
                after_description="List view",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should not suggest pause verification without timestamps
        pause_suggestions = [
            s for s in suggestions if "pause" in s.reason.lower()
        ]
        assert len(pause_suggestions) == 0

    def test_no_pause_suggestion_when_current_timestamp_missing(self):
        """Should not suggest pause verification when current timestamp is missing."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200},  # No timestamp
                element_text="Item 1",
                before_description="List view",
                after_description="Item details",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300, "timestamp": 5.0},
                element_text="Back",
                before_description="Item details",
                after_description="List view",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should not suggest pause verification without current timestamp
        pause_suggestions = [
            s for s in suggestions if "pause" in s.reason.lower()
        ]
        assert len(pause_suggestions) == 0

    def test_no_pause_suggestion_when_next_timestamp_missing(self):
        """Should not suggest pause verification when next timestamp is missing."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Item 1",
                before_description="List view",
                after_description="Item details",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300},  # No timestamp
                element_text="Back",
                before_description="Item details",
                after_description="List view",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Should not suggest pause verification without next timestamp
        pause_suggestions = [
            s for s in suggestions if "pause" in s.reason.lower()
        ]
        assert len(pause_suggestions) == 0


class TestSuggestOnFlowKeywords:
    """Test verification suggestion on flow completion keywords."""

    def test_suggests_verification_on_success_keyword(self):
        """Should suggest verification when 'success' appears in after_description."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Confirm",
                before_description="Confirmation dialog",
                after_description="Success message displayed",
                suggested_verification="Operation completed successfully",
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1
        success_suggestion = next(
            (s for s in suggestions if s.after_step_index == 0), None
        )
        assert success_suggestion is not None

    def test_suggests_verification_on_welcome_keyword(self):
        """Should suggest verification when 'welcome' appears."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Get Started",
                before_description="Onboarding screen",
                after_description="Welcome screen with user name",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1

    def test_suggests_verification_on_dashboard_keyword(self):
        """Should suggest verification when 'dashboard' appears."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Login",
                before_description="Login form",
                after_description="User dashboard with stats",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1

    def test_suggests_verification_on_complete_keyword(self):
        """Should suggest verification when 'complete' appears."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Finish",
                before_description="Final step",
                after_description="Task complete confirmation",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1


class TestNoneDescriptionHandling:
    """Test handling of None values for descriptions."""

    def test_no_flow_completion_when_after_description_is_none(self):
        """Should not crash when after_description is None in flow completion check."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Button",
                before_description="Some screen",
                after_description=None,  # None after_description
                suggested_verification=None,
            ),
        ]

        # Should not raise AttributeError
        suggestions = suggester.suggest(steps)

        # No flow completion suggestions for None description
        flow_suggestions = [
            s for s in suggestions
            if "flow" in s.reason.lower() or "completion" in s.reason.lower()
        ]
        assert len(flow_suggestions) == 0

    def test_no_navigation_change_when_descriptions_are_none(self):
        """Should not crash when before/after descriptions are None in navigation check."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 100, "timestamp": 0.0},
                element_text="Menu",
                before_description=None,  # None before_description
                after_description=None,  # None after_description
                suggested_verification=None,
            ),
        ]

        # Should not raise AttributeError
        suggestions = suggester.suggest(steps)

        # No navigation suggestions for None descriptions
        nav_suggestions = [
            s for s in suggestions if "navigation" in s.reason.lower()
        ]
        assert len(nav_suggestions) == 0

    def test_no_navigation_when_only_before_description_is_none(self):
        """Should not crash when only before_description is None."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 100, "timestamp": 0.0},
                element_text="Settings",
                before_description=None,  # None before_description
                after_description="Settings screen displayed",
                suggested_verification=None,
            ),
        ]

        # Should not raise AttributeError
        suggestions = suggester.suggest(steps)

        # Should still detect navigation since after_description has keywords
        # (the comparison after_lower != before_lower will work with empty string)
        assert isinstance(suggestions, list)


class TestEmptyAndLimitedResults:
    """Test edge cases for empty results and limits."""

    def test_returns_empty_list_when_no_verifications_needed(self):
        """Should return empty list when no verification criteria met."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        # Simple taps with no significant changes
        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Tab1",
                before_description="Home tab",
                after_description="Home tab selected",
                suggested_verification=None,
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 200, "y": 200, "timestamp": 0.3},
                element_text="Tab2",
                before_description="Home tab selected",
                after_description="Tab2 selected",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        # Could be empty or have low confidence suggestions
        # The key is no false positives with high confidence
        high_confidence = [s for s in suggestions if s.confidence > 0.7]
        assert len(high_confidence) == 0

    def test_returns_empty_list_for_empty_steps(self):
        """Should return empty list when no steps provided."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        suggestions = suggester.suggest([])

        assert suggestions == []

    def test_limits_suggestions_to_max_five(self):
        """Should limit suggestions to maximum 5 per recording."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        # Create many steps that would all trigger suggestions
        steps = []
        for i in range(10):
            steps.append(
                AnalyzedStep(
                    index=i,
                    original_tap={"x": 100, "y": 200, "timestamp": float(i * 3)},  # 3s between each
                    element_text="Submit",
                    before_description="Form filled",
                    after_description="Success message displayed",
                    suggested_verification="Submission successful",
                )
            )

        suggestions = suggester.suggest(steps)

        # Should be limited to max 5
        assert len(suggestions) <= 5

    def test_suggestions_sorted_by_confidence(self):
        """Suggestions should be sorted by confidence (highest first)."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 100, "y": 200, "timestamp": 0.0},
                element_text="Login",  # Form submission - high confidence
                before_description="Login form",
                after_description="Dashboard with welcome message",  # Flow keyword
                suggested_verification="User logged in",
            ),
            AnalyzedStep(
                index=1,
                original_tap={"x": 100, "y": 300, "timestamp": 3.0},  # Long pause
                element_text="Menu",
                before_description="Dashboard",
                after_description="Menu opened",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        if len(suggestions) >= 2:
            # First suggestion should have higher or equal confidence
            for i in range(len(suggestions) - 1):
                assert suggestions[i].confidence >= suggestions[i + 1].confidence


class TestDescriptionGeneration:
    """Test verification description generation."""

    def test_uses_suggested_verification_when_available(self):
        """Should use AI's suggested_verification when available."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Submit",
                before_description="Form filled",
                after_description="Confirmation shown",
                suggested_verification="Form submitted successfully",
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1
        # Should use the AI-suggested verification
        assert suggestions[0].description == "Form submitted successfully"

    def test_generates_description_from_after_state(self):
        """Should generate description from after_description when no suggested_verification."""
        mock_ai = MagicMock()
        suggester = VerificationSuggester(ai_analyzer=mock_ai)

        steps = [
            AnalyzedStep(
                index=0,
                original_tap={"x": 200, "y": 400, "timestamp": 0.0},
                element_text="Login",
                before_description="Login form",
                after_description="User dashboard displayed",
                suggested_verification=None,
            ),
        ]

        suggestions = suggester.suggest(steps)

        assert len(suggestions) >= 1
        # Should generate from after_description
        assert "dashboard" in suggestions[0].description.lower()
