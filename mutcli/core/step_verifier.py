"""AI-powered step verification for test execution."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from google.api_core import exceptions as google_exceptions

from mutcli.core.ai_analyzer import AIAnalyzer

logger = logging.getLogger("mut.verifier")

# Exceptions that indicate transient errors and should trigger retry
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    google_exceptions.TooManyRequests,
    google_exceptions.ResourceExhausted,
    google_exceptions.InternalServerError,
    google_exceptions.BadGateway,
    google_exceptions.ServiceUnavailable,
    google_exceptions.DeadlineExceeded,
    TimeoutError,
    ConnectionError,
)


@dataclass
class StepAnalysis:
    """Result of AI analysis for a single step."""

    verified: bool  # AI confirms step succeeded visually
    outcome_description: str  # What actually happened on screen
    suggestion: str | None  # Suggested fix if step failed


class StepVerifier:
    """AI-powered verification of test step execution.

    Analyzes before/after screenshots to verify step success,
    describe what happened, and suggest fixes for failures.
    """

    def __init__(self, analyzer: AIAnalyzer):
        """Initialize verifier.

        Args:
            analyzer: AIAnalyzer instance for vision analysis
        """
        self._analyzer = analyzer

    @property
    def is_available(self) -> bool:
        """Check if AI verification is available."""
        return self._analyzer.is_available

    def analyze_step(
        self,
        action: str,
        target: str | None,
        description: str | None,
        reported_status: str,
        error: str | None,
        screenshot_before: bytes,
        screenshot_after: bytes,
    ) -> StepAnalysis:
        """Analyze a single step with AI.

        Args:
            action: Step action type (tap, type, verify_screen, etc.)
            target: Target element or screen description
            description: Human-readable step description
            reported_status: Status reported by executor (passed/failed)
            error: Error message if step failed
            screenshot_before: Screenshot before action
            screenshot_after: Screenshot after action

        Returns:
            StepAnalysis with verification result, outcome, and suggestion
        """
        if not self.is_available or not self._analyzer._client:
            logger.warning("AI not available, creating placeholder analysis")
            return StepAnalysis(
                verified=reported_status == "passed",
                outcome_description="AI analysis unavailable",
                suggestion=None,
            )

        prompt = self._build_analysis_prompt(
            action, target, description, reported_status, error
        )

        try:
            from google.genai import types

            before_part = types.Part.from_bytes(
                data=screenshot_before,
                mime_type="image/png",
            )
            after_part = types.Part.from_bytes(
                data=screenshot_after,
                mime_type="image/png",
            )

            response = self._analyzer._client.models.generate_content(
                model=self._analyzer._model,
                contents=[before_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._analyzer._parse_json_response(response_text)

            return StepAnalysis(
                verified=result.get("verified", reported_status == "passed"),
                outcome_description=result.get("outcome", "Analysis completed"),
                suggestion=result.get("suggestion"),
            )

        except Exception as e:
            logger.error(f"Step analysis failed: {e}")
            return StepAnalysis(
                verified=reported_status == "passed",
                outcome_description=f"Analysis error: {e}",
                suggestion=None,
            )

    def analyze_all_steps(
        self,
        steps: list[dict[str, Any]],
    ) -> list[StepAnalysis]:
        """Analyze all steps from a test result.

        Args:
            steps: List of step dicts with action, target, status, etc.

        Returns:
            List of StepAnalysis results (same order as input)
        """
        analyses = []
        total = len(steps)

        for i, step in enumerate(steps):
            logger.debug("Analyzing step %d/%d: %s", i + 1, total, step.get("action"))

            screenshot_before = step.get("screenshot_before")
            screenshot_after = step.get("screenshot_after")

            if not screenshot_before or not screenshot_after:
                # No screenshots available - create placeholder
                logger.debug("Step %d: No screenshots, creating placeholder", i + 1)
                analyses.append(
                    StepAnalysis(
                        verified=step.get("status") == "passed",
                        outcome_description="No visual analysis available (missing screenshots)",
                        suggestion=None,
                    )
                )
                continue

            analysis = self.analyze_step(
                action=step.get("action", "unknown"),
                target=step.get("target"),
                description=step.get("description"),
                reported_status=step.get("status", "unknown"),
                error=step.get("error"),
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
            )
            analyses.append(analysis)

        logger.info("Analyzed %d steps", total)
        return analyses

    async def analyze_all_steps_parallel(
        self,
        steps: list[dict[str, Any]],
        on_progress: Callable[[int, int], None] | None = None,
        app_package: str | None = None,
        test_name: str | None = None,
    ) -> list[StepAnalysis]:
        """Analyze all steps in parallel with progress callback.

        Args:
            steps: List of step dicts with action, target, status, screenshots, etc.
            on_progress: Callback(completed, total) called as each finishes
            app_package: App package name for context
            test_name: Test name for context

        Returns:
            List of StepAnalysis results (same order as input)
        """
        if not steps:
            return []

        total = len(steps)

        # Create tasks for all steps
        tasks = []
        for i, step in enumerate(steps):
            task = self._analyze_step_with_retry(
                i, step, total, app_package, test_name, steps[:i]
            )
            tasks.append(task)

        # Execute in parallel, collecting results as they complete
        results: list[StepAnalysis | None] = [None] * len(tasks)
        completed = 0

        for coro in asyncio.as_completed(tasks):
            index, result = await coro
            results[index] = result
            completed += 1
            if on_progress:
                on_progress(completed, total)

        # Fill any None values with placeholders (should not happen)
        return [
            r if r is not None else StepAnalysis(
                verified=False,
                outcome_description="Analysis failed",
                suggestion=None,
            )
            for r in results
        ]

    async def _analyze_step_with_retry(
        self,
        index: int,
        step: dict[str, Any],
        total_steps: int,
        app_package: str | None,
        test_name: str | None,
        previous_steps: list[dict[str, Any]],
        max_retries: int = 2,
    ) -> tuple[int, StepAnalysis]:
        """Analyze single step with exponential backoff retry.

        Args:
            index: Step index (0-based)
            step: Step dict with action, target, status, screenshots
            total_steps: Total number of steps in test
            app_package: App package name
            test_name: Test name
            previous_steps: Steps that ran before this one
            max_retries: Maximum retries for transient errors

        Returns:
            Tuple of (index, StepAnalysis) to preserve ordering
        """
        delay = 0.5
        last_error: Exception | None = None
        step_num = index + 1

        for attempt in range(max_retries + 1):
            try:
                result = await self._analyze_step_async(
                    index, step, total_steps, app_package, test_name, previous_steps
                )
                return (index, result)
            except RETRYABLE_EXCEPTIONS as e:
                last_error = e
                attempt_num = attempt + 1
                total_attempts = max_retries + 1
                logger.warning(
                    f"Step {step_num} analysis failed (attempt {attempt_num}/{total_attempts}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2
            except Exception as e:
                logger.error(f"Step {step_num} analysis failed with non-retryable error: {e}")
                return (index, StepAnalysis(
                    verified=step.get("status") == "passed",
                    outcome_description=f"Analysis error: {e}",
                    suggestion=None,
                ))

        # All retries exhausted
        return (index, StepAnalysis(
            verified=step.get("status") == "passed",
            outcome_description=f"Analysis failed after retries: {last_error}",
            suggestion=None,
        ))

    async def _analyze_step_async(
        self,
        index: int,
        step: dict[str, Any],
        total_steps: int,
        app_package: str | None,
        test_name: str | None,
        previous_steps: list[dict[str, Any]],
    ) -> StepAnalysis:
        """Analyze a single step asynchronously.

        Args:
            index: Step index (0-based)
            step: Step dict
            total_steps: Total steps in test
            app_package: App package name
            test_name: Test name
            previous_steps: Steps that ran before this one

        Returns:
            StepAnalysis result
        """
        screenshot_before = step.get("screenshot_before")
        screenshot_after = step.get("screenshot_after")

        if not screenshot_before or not screenshot_after:
            return StepAnalysis(
                verified=step.get("status") == "passed",
                outcome_description="No visual analysis available (missing screenshots)",
                suggestion=None,
            )

        if not self.is_available or not self._analyzer._client:
            return StepAnalysis(
                verified=step.get("status") == "passed",
                outcome_description="AI analysis unavailable",
                suggestion=None,
            )

        prompt = self._build_analysis_prompt_enhanced(
            action=step.get("action", "unknown"),
            target=step.get("target"),
            description=step.get("description"),
            reported_status=step.get("status", "unknown"),
            error=step.get("error"),
            step_number=index + 1,
            total_steps=total_steps,
            app_package=app_package,
            test_name=test_name,
            previous_steps=previous_steps,
            coordinates=step.get("details", {}).get("coords"),
        )

        try:
            from google.genai import types

            before_part = types.Part.from_bytes(
                data=screenshot_before,
                mime_type="image/png",
            )
            after_part = types.Part.from_bytes(
                data=screenshot_after,
                mime_type="image/png",
            )

            # Run in executor to not block event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._analyzer._client.models.generate_content(
                    model=self._analyzer._model,
                    contents=[before_part, after_part, prompt],
                ),
            )

            response_text = response.text or ""
            result = self._analyzer._parse_json_response(response_text)

            return StepAnalysis(
                verified=result.get("verified", step.get("status") == "passed"),
                outcome_description=result.get("outcome", "Analysis completed"),
                suggestion=result.get("suggestion"),
            )

        except Exception as e:
            raise e  # Let retry logic handle it

    def _build_analysis_prompt_enhanced(
        self,
        action: str,
        target: str | None,
        description: str | None,
        reported_status: str,
        error: str | None,
        step_number: int,
        total_steps: int,
        app_package: str | None,
        test_name: str | None,
        previous_steps: list[dict[str, Any]],
        coordinates: dict[str, float] | None,
    ) -> str:
        """Build enhanced analysis prompt with full context.

        Args:
            action: Step action type
            target: Target element
            description: Step description
            reported_status: Execution status
            error: Error message if any
            step_number: Current step number (1-based)
            total_steps: Total steps in test
            app_package: App package name
            test_name: Test name
            previous_steps: Previous steps for context
            coordinates: Tap coordinates as percentages

        Returns:
            Formatted prompt string
        """
        # Build context section
        context_parts = []
        if app_package:
            context_parts.append(f"- App: {app_package}")
        if test_name:
            context_parts.append(f"- Test: {test_name}")
        context_parts.append(f"- Step {step_number} of {total_steps}")

        # Build brief history of previous steps
        if previous_steps:
            history = []
            for i, prev in enumerate(previous_steps[-3:], start=max(1, step_number - 3)):
                prev_action = prev.get("action", "?")
                prev_target = prev.get("target", "")
                prev_status = "✓" if prev.get("status") == "passed" else "✗"
                history.append(f"  {i}. {prev_status} {prev_action} {prev_target}".strip())
            if history:
                context_parts.append("- Recent steps:\n" + "\n".join(history))

        context_section = "\n".join(context_parts)

        # Build step details
        details = [f"- Action: {action}"]
        if target:
            details.append(f'- Target: "{target}"')
        if coordinates:
            x_coord = coordinates.get('x', 0)
            y_coord = coordinates.get('y', 0)
            details.append(f"- Coordinates: ({x_coord:.1f}%, {y_coord:.1f}%)")
        if description:
            details.append(f"- Description: {description}")
        details.append(f"- Reported Status: {reported_status}")
        if error:
            details.append(f"- Error: {error}")

        details_section = "\n".join(details)

        return f"""You are analyzing a mobile UI test step execution.

## Context
{context_section}

## Step Details
{details_section}

## Screenshots
Image 1: BEFORE the action was performed
Image 2: AFTER the action was performed

## Your Task

Analyze the visual difference between the two screenshots to determine:

1. **Verification**: Did the action succeed visually?
   - For tap: Was the element tapped? Did expected UI response occur?
   - For type: Was text entered in the correct field?
   - For swipe: Did content scroll/move as expected?

2. **Outcome**: What actually happened on screen?
   - Be specific: "Login button was tapped, loading spinner appeared"
   - Note unexpected changes: "Keyboard appeared blocking the target element"
   - Describe visual state changes

3. **Suggestion** (only if verification failed): What should be fixed?

## Common Failure Patterns to Check
- Element exists but has different text (e.g., "Sign In" vs "Login")
- Element is off-screen and needs scroll_to first
- Element is covered by keyboard, dialog, or overlay
- Screen hasn't finished loading (needs wait or wait_for step)
- App navigated to wrong screen
- Element found but tap coordinates missed it

## Response Format
Respond with JSON only (no markdown, no code blocks):
{{
  "verified": true or false,
  "outcome": "1-2 sentence description of what actually happened visually",
  "suggestion": "specific actionable fix if failed, or null if passed"
}}

Guidelines:
- verified=true only if visual evidence confirms the action completed successfully
- outcome should describe what you SEE changed, not what was intended
- suggestion should be a specific fix like "Add wait_for step" or "Change target text"
- If screenshots are identical, the action likely had no effect"""

    def _build_analysis_prompt(
        self,
        action: str,
        target: str | None,
        description: str | None,
        reported_status: str,
        error: str | None,
    ) -> str:
        """Build the analysis prompt for AI.

        Args:
            action: Step action type
            target: Target element
            description: Step description
            reported_status: Execution status
            error: Error message if any

        Returns:
            Formatted prompt string
        """
        target_info = f"Target: {target}" if target else "Target: (none specified)"
        desc_info = f"Description: {description}" if description else ""
        error_info = f"Error: {error}" if error else ""

        return f"""Analyze this test step execution by comparing the BEFORE and AFTER screenshots.

Step Details:
- Action: {action}
- {target_info}
{desc_info}
- Reported Status: {reported_status}
{error_info}

The first image is BEFORE the action, the second is AFTER.

Your task:
1. Verify if the action actually succeeded visually (regardless of reported status)
2. Describe what actually happened on screen
3. If the step failed or looks incorrect, suggest a fix

Respond with JSON only (no markdown, no code blocks):
{{
  "verified": true/false,
  "outcome": "Brief description of what happened (1-2 sentences)",
  "suggestion": "Suggested fix if failed, or null if step succeeded"
}}

Guidelines:
- verified: true if the visual state shows the action completed successfully
- outcome: Describe the actual visual change, not the intended action
  Examples: "Button was tapped, dialog appeared", "Text was entered in search field",
            "Element was not found on screen", "Screen state unchanged"
- suggestion: Provide actionable fix for failures
  Examples: "Element may have different text - try 'Login' instead of 'Sign In'",
            "Add a wait_for step before this action", "Check if app is on correct screen",
            null (for successful steps)"""
