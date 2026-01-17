"""Verification suggester for smart verification point detection."""

import logging
from dataclasses import dataclass

from mutcli.core.ai_analyzer import AIAnalyzer
from mutcli.core.step_analyzer import AnalyzedStep

logger = logging.getLogger("mut.verification_suggester")


# Keywords that indicate form submission buttons
FORM_SUBMISSION_KEYWORDS = frozenset({
    "login",
    "log in",
    "sign in",
    "signin",
    "submit",
    "send",
    "confirm",
    "save",
    "register",
    "sign up",
    "signup",
    "create account",
    "continue",
    "next",
    "done",
    "finish",
    "complete",
    "apply",
    "ok",
    "proceed",
    "checkout",
    "pay",
    "purchase",
    "buy",
    "order",
    "book",
})

# Keywords indicating flow completion in after_description
FLOW_COMPLETION_KEYWORDS = frozenset({
    "success",
    "successful",
    "complete",
    "completed",
    "welcome",
    "dashboard",
    "home screen",
    "confirmation",
    "confirmed",
    "done",
    "finished",
    "thank you",
    "logged in",
    "signed in",
})

# Keywords indicating navigation/screen change
NAVIGATION_KEYWORDS = frozenset({
    "screen",
    "page",
    "view",
    "displayed",
    "opened",
    "navigated",
    "loaded",
    "transitioned",
})

# Minimum pause duration (seconds) to suggest verification
MIN_PAUSE_DURATION = 2.0

# Maximum suggestions to return
MAX_SUGGESTIONS = 5


@dataclass
class VerificationPoint:
    """A suggested verification point.

    Attributes:
        after_step_index: Insert verification after this step (0-based index)
        description: Suggested verify_screen description
        confidence: Confidence score (0.0-1.0)
        reason: Why this verification was suggested
    """

    after_step_index: int
    description: str
    confidence: float
    reason: str


class VerificationSuggester:
    """Suggests verification points based on analyzed steps.

    Uses heuristics to identify verification-worthy moments:
    1. Form submission: Tapping buttons like "Login", "Submit", "Sign In"
    2. Navigation change: Screen title/header changes
    3. Long pause: > 2 seconds before next action (user was verifying visually)
    4. Flow completion: Keywords like "success", "welcome", "dashboard"
    """

    def __init__(self, ai_analyzer: AIAnalyzer):
        """Initialize with AIAnalyzer.

        Args:
            ai_analyzer: AIAnalyzer instance (for potential future AI-based suggestions)
        """
        self._ai_analyzer = ai_analyzer

    def suggest(
        self,
        analyzed_steps: list[AnalyzedStep],
    ) -> list[VerificationPoint]:
        """Suggest verification points based on analyzed steps.

        Suggests verifications when:
        - Significant UI change detected (navigation, form submission)
        - Long pause before next action (user was verifying visually)
        - Flow completion (login, checkout, etc.)

        Args:
            analyzed_steps: List of analyzed steps from StepAnalyzer

        Returns:
            List of VerificationPoint suggestions, sorted by confidence (highest first),
            limited to MAX_SUGGESTIONS
        """
        if not analyzed_steps:
            return []

        suggestions: list[VerificationPoint] = []

        for i, step in enumerate(analyzed_steps):
            step_suggestions = self._analyze_step(step, analyzed_steps, i)
            suggestions.extend(step_suggestions)

        # Deduplicate by step index (keep highest confidence for each step)
        suggestions = self._deduplicate_by_step(suggestions)

        # Sort by confidence (highest first)
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        # Limit to MAX_SUGGESTIONS
        return suggestions[:MAX_SUGGESTIONS]

    def _analyze_step(
        self,
        step: AnalyzedStep,
        all_steps: list[AnalyzedStep],
        index: int,
    ) -> list[VerificationPoint]:
        """Analyze a single step for potential verification points.

        Args:
            step: The step to analyze
            all_steps: All steps (for context like pause detection)
            index: Index of this step in all_steps

        Returns:
            List of verification suggestions for this step
        """
        suggestions: list[VerificationPoint] = []

        # Check for form submission
        form_suggestion = self._check_form_submission(step)
        if form_suggestion:
            suggestions.append(form_suggestion)

        # Check for flow completion keywords
        flow_suggestion = self._check_flow_completion(step)
        if flow_suggestion:
            suggestions.append(flow_suggestion)

        # Check for navigation change
        nav_suggestion = self._check_navigation_change(step)
        if nav_suggestion:
            suggestions.append(nav_suggestion)

        # Check for long pause before next step
        pause_suggestion = self._check_long_pause(step, all_steps, index)
        if pause_suggestion:
            suggestions.append(pause_suggestion)

        return suggestions

    def _check_form_submission(self, step: AnalyzedStep) -> VerificationPoint | None:
        """Check if step is a form submission.

        Args:
            step: Step to check

        Returns:
            VerificationPoint if form submission detected, None otherwise
        """
        element_text = step.element_text
        if not element_text:
            return None

        element_lower = element_text.lower().strip()

        # Check against form submission keywords
        for keyword in FORM_SUBMISSION_KEYWORDS:
            if keyword in element_lower or element_lower in keyword:
                description = self._generate_description(step)
                return VerificationPoint(
                    after_step_index=step.index,
                    description=description,
                    confidence=0.85,
                    reason=f"Form submission detected (tapped '{element_text}')",
                )

        return None

    def _check_flow_completion(self, step: AnalyzedStep) -> VerificationPoint | None:
        """Check for flow completion keywords in after_description.

        Args:
            step: Step to check

        Returns:
            VerificationPoint if flow completion detected, None otherwise
        """
        after_desc = step.after_description or ""
        after_lower = after_desc.lower()

        for keyword in FLOW_COMPLETION_KEYWORDS:
            if keyword in after_lower:
                description = self._generate_description(step)
                return VerificationPoint(
                    after_step_index=step.index,
                    description=description,
                    confidence=0.80,
                    reason=f"Flow completion detected ('{keyword}' in screen state)",
                )

        return None

    def _check_navigation_change(self, step: AnalyzedStep) -> VerificationPoint | None:
        """Check for significant navigation/screen change.

        Args:
            step: Step to check

        Returns:
            VerificationPoint if navigation change detected, None otherwise
        """
        before_desc = step.before_description or ""
        after_desc = step.after_description or ""
        before_lower = before_desc.lower()
        after_lower = after_desc.lower()

        # Check if screen/page changed
        nav_keywords_in_after = sum(
            1 for kw in NAVIGATION_KEYWORDS if kw in after_lower
        )

        # Look for title/screen name changes
        if nav_keywords_in_after >= 1:
            # Check if it's a different screen (not just modification of current)
            # Simple heuristic: "displayed", "opened", "loaded" suggest new screen
            significant_change = any(
                kw in after_lower for kw in ["displayed", "opened", "loaded", "screen"]
            )

            if significant_change and after_lower != before_lower:
                description = self._generate_description(step)
                return VerificationPoint(
                    after_step_index=step.index,
                    description=description,
                    confidence=0.70,
                    reason="Navigation/screen change detected",
                )

        return None

    def _check_long_pause(
        self,
        step: AnalyzedStep,
        all_steps: list[AnalyzedStep],
        index: int,
    ) -> VerificationPoint | None:
        """Check if there's a long pause after this step.

        Args:
            step: Current step
            all_steps: All steps
            index: Index of current step

        Returns:
            VerificationPoint if long pause detected, None otherwise
        """
        # Can't detect pause after last step
        if index >= len(all_steps) - 1:
            return None

        next_step = all_steps[index + 1]

        current_timestamp = step.original_tap.get("timestamp")
        next_timestamp = next_step.original_tap.get("timestamp")

        # Cannot calculate pause without timestamps
        if current_timestamp is None or next_timestamp is None:
            return None

        pause_duration = next_timestamp - current_timestamp

        if pause_duration >= MIN_PAUSE_DURATION:
            description = self._generate_description(step)
            return VerificationPoint(
                after_step_index=step.index,
                description=description,
                confidence=0.65,
                reason=f"Long pause detected ({pause_duration:.1f}s before next action)",
            )

        return None

    def _generate_description(self, step: AnalyzedStep) -> str:
        """Generate verification description for a step.

        Args:
            step: Step to generate description for

        Returns:
            Verification description string
        """
        # Use AI-suggested verification if available
        if step.suggested_verification:
            return step.suggested_verification

        # Generate from after_description
        after_desc = step.after_description
        if after_desc and after_desc not in ("Unknown", "Screenshot missing"):
            return after_desc

        # Fallback
        return "Screen state as expected"

    def _deduplicate_by_step(
        self,
        suggestions: list[VerificationPoint],
    ) -> list[VerificationPoint]:
        """Deduplicate suggestions, keeping highest confidence for each step.

        Args:
            suggestions: List of suggestions (may have duplicates for same step)

        Returns:
            Deduplicated list with highest confidence per step
        """
        best_by_step: dict[int, VerificationPoint] = {}

        for suggestion in suggestions:
            step_idx = suggestion.after_step_index
            if step_idx not in best_by_step:
                best_by_step[step_idx] = suggestion
            elif suggestion.confidence > best_by_step[step_idx].confidence:
                best_by_step[step_idx] = suggestion

        return list(best_by_step.values())
