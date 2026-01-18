"""Test report generation."""

import base64
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from mutcli.core.executor import TestResult


class ReportGenerator:
    """Generate JSON and HTML test reports."""

    # Status icons (Material Symbols names)
    STATUS_ICONS = {
        "passed": "check_circle",
        "failed": "cancel",
        "skipped": "remove_circle_outline",
    }

    # Gesture icons (Material Symbols names)
    GESTURE_ICONS = {
        "tap": "touch_app",
        "double_tap": "ads_click",
        "long_press": "pan_tool_alt",
        "swipe": "swipe_vertical",
        "verify_screen": "verified",
        "verify": "verified",
        "wait": "schedule",
        "wait_for": "schedule",
        "type": "keyboard",
        "scroll_to": "unfold_more",
        "launch_app": "rocket_launch",
        "terminate_app": "cancel",
        "back": "arrow_back",
        "hide_keyboard": "keyboard_hide",
        "if_present": "rule",
        "if_absent": "rule",
        "if_screen": "rule",
        "repeat": "repeat",
    }

    # Suggested failure reasons based on error patterns
    FAILURE_SUGGESTIONS = {
        "element not found": "The target element may have changed or doesn't exist. "
        "Try updating the element selector or adding a wait_for step before this action.",
        "timeout": "The operation took too long. Consider increasing the timeout "
        "or adding a wait step to ensure the app is ready.",
        "coordinates": "The tap coordinates may be incorrect for this screen size. "
        "Consider using element text instead of fixed coordinates.",
        "verify_screen failed": "The screen state doesn't match the expected description. "
        "The app may be showing different content or the description may need adjustment.",
        "unknown action": "This action type is not supported. Check the test YAML syntax.",
    }

    def __init__(self, output_dir: Path, source_video_path: Path | None = None):
        """Initialize generator.

        Args:
            output_dir: Directory to write reports
            source_video_path: Optional path to source video from recording session
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._source_video_path = Path(source_video_path) if source_video_path else None

    def _load_template(self) -> str:
        """Load HTML template from templates directory."""
        template_path = Path(__file__).parent.parent / "templates" / "report.html"
        return template_path.read_text()

    def _encode_screenshot(self, data: bytes | None) -> str | None:
        """Encode screenshot as base64 data URI."""
        if data is None:
            return None
        return f"data:image/png;base64,{base64.b64encode(data).decode()}"

    def _escape_json_for_html(self, json_str: str) -> str:
        """Escape JSON string for safe embedding in HTML script tags.

        Prevents XSS by escaping sequences that could close the script tag
        or start an HTML comment.
        """
        # Escape </script> by replacing </ with <\/
        # This is safe in JSON strings and prevents script tag injection
        return json_str.replace("</", r"<\/").replace("<!--", r"<\!--")

    def generate_json(self, result: TestResult) -> Path:
        """Generate JSON report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.json
        """
        data = self._result_to_dict(result)

        path = self._output_dir / "report.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return path

    def generate_html(self, result: TestResult) -> Path:
        """Generate interactive HTML report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.html
        """
        data = self._result_to_dict(result)

        # Generate steps HTML
        steps_html = self._generate_steps_html(data["steps"])

        # Determine status icon
        status_icons = {
            "passed": "check_circle",
            "failed": "cancel",
            "error": "error",
        }
        status_icon = status_icons.get(data["status"], "help")

        # Load and populate template
        template = self._load_template()
        html_content = template.replace("{{test_name}}", html.escape(data["test"]))
        html_content = html_content.replace("{{status}}", data["status"])
        html_content = html_content.replace("{{status_class}}", data["status"])
        html_content = html_content.replace("{{status_icon}}", status_icon)
        html_content = html_content.replace("{{duration}}", data["duration"])
        html_content = html_content.replace("{{timestamp}}", data["timestamp"])
        html_content = html_content.replace("{{steps_html}}", steps_html)
        html_content = html_content.replace(
            "{{summary_total}}", str(data["summary"]["total"])
        )
        html_content = html_content.replace(
            "{{summary_passed}}", str(data["summary"]["passed"])
        )
        html_content = html_content.replace(
            "{{summary_failed}}", str(data["summary"]["failed"])
        )
        html_content = html_content.replace(
            "{{summary_skipped}}", str(data["summary"]["skipped"])
        )
        json_data = self._escape_json_for_html(json.dumps(data))
        html_content = html_content.replace("{{json_data}}", json_data)
        html_content = html_content.replace("{{video_html}}", self._generate_video_html())

        # Convert escaped braces back to single braces for CSS/JS
        # Template uses {{ and }} to avoid conflicts with placeholder syntax
        html_content = html_content.replace("{{", "{").replace("}}", "}")

        path = self._output_dir / "report.html"
        path.write_text(html_content)
        return path

    def _result_to_dict(self, result: TestResult) -> dict[str, Any]:
        """Convert TestResult to dictionary."""
        passed = sum(1 for s in result.steps if s.status == "passed")
        failed = sum(1 for s in result.steps if s.status == "failed")
        skipped = sum(1 for s in result.steps if s.status == "skipped")

        return {
            "test": result.name,
            "status": result.status,
            "duration": f"{result.duration:.1f}s",
            "timestamp": datetime.now().isoformat(),
            "error": result.error,
            "steps": [
                {
                    "number": s.step_number,
                    "action": s.action,
                    "status": s.status,
                    "target": s.target,
                    "description": s.description,
                    "duration": f"{s.duration:.1f}s",
                    "error": s.error,
                    "screenshot_before": self._encode_screenshot(s.screenshot_before),
                    "screenshot_after": self._encode_screenshot(s.screenshot_after),
                    # Action screenshots (varies by gesture type)
                    "screenshot_action": self._encode_screenshot(s.screenshot_action),
                    "screenshot_action_end": self._encode_screenshot(s.screenshot_action_end),
                    # AI analysis results
                    "ai_verified": s.ai_verified,
                    "ai_outcome": s.ai_outcome,
                    "ai_suggestion": s.ai_suggestion,
                    # Gesture coordinates for visualization
                    "coords": s.details.get("coords"),
                    "end_coords": s.details.get("end_coords"),
                    "direction": s.details.get("direction"),
                    # Trajectory data for swipe visualization
                    "trajectory": s.details.get("trajectory"),
                    "duration_ms": s.details.get("duration_ms"),
                }
                for s in result.steps
            ],
            "summary": {
                "total": len(result.steps),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
        }

    def _generate_steps_html(self, steps: list[dict[str, Any]]) -> str:
        """Generate HTML for all steps."""
        html_parts = []
        for index, step in enumerate(steps):
            step_html = self._generate_step_html(step, index)
            html_parts.append(step_html)
        return "\n".join(html_parts)

    def _generate_step_html(self, step: dict[str, Any], index: int) -> str:
        """Generate HTML for a single step card."""
        status = step["status"]
        action = step["action"]
        gesture_icon = self.GESTURE_ICONS.get(action, "radio_button_unchecked")
        status_icon = self.STATUS_ICONS.get(status, "help")

        # Action class for CSS (no underscores)
        action_class = action.replace("_", "")

        # Step description: prefer description, fallback to target
        step_desc = step.get("description") or step.get("target") or ""
        escaped_desc = html.escape(str(step_desc))

        # AI analysis section (if available)
        ai_html = self._generate_ai_analysis_html(step)

        # Failure section HTML (for failed steps)
        failure_html = ""
        if step["error"]:
            escaped_error = html.escape(step["error"])
            # Prefer AI suggestion over pattern-based suggestion
            suggestion = step.get("ai_suggestion") or self._get_failure_suggestion(
                step["error"]
            )
            failure_html = f"""
            <div class="step-failure">
                <div class="failure-header">
                    <span class="material-symbols-outlined">error</span>
                    Step Failed
                </div>
                <div class="failure-error">{escaped_error}</div>
                <div class="failure-suggestion">
                    <span class="failure-suggestion-label">Suggested Fix</span>
                    <span class="failure-suggestion-text">{html.escape(suggestion)}</span>
                </div>
            </div>"""

        # Screenshots HTML (if any)
        screenshots_html = self._generate_screenshots_html(step)

        return f"""<div class="step-card" data-status="{status}" data-index="{index}">
    <div class="step-header">
        <div class="step-title">
            <div class="step-number {status}">{step["number"]}</div>
            <span class="gesture-badge {action_class}">
                <span class="material-symbols-outlined">{gesture_icon}</span>
                {action.upper().replace("_", " ")}
            </span>
            <span class="step-action-title">{escaped_desc}</span>
        </div>
        <div class="step-status">
            <span class="step-duration">{step["duration"]}</span>
            <div class="step-status-indicator {status}">
                <span class="material-symbols-outlined">{status_icon}</span>
            </div>
        </div>
    </div>
    <div class="step-content">
        {screenshots_html}
        {ai_html}
        {failure_html}
    </div>
</div>"""

    def _generate_ai_analysis_html(self, step: dict[str, Any]) -> str:
        """Generate HTML for AI analysis section.

        Distinguishes between:
        - Verification: explicit verify_screen steps (pass/fail judgment)
        - Observation: other steps where AI describes what happened (informational)
        """
        ai_outcome = step.get("ai_outcome")
        ai_verified = step.get("ai_verified")
        action = step.get("action", "")

        if not ai_outcome:
            return ""

        # Check if this is an explicit verification step
        is_verification = action in ("verify_screen", "verify")

        if is_verification:
            # Verification: prominent pass/fail styling
            if ai_verified is True:
                verify_icon = "verified"
                verify_class = "verified"
                header_text = "Verification Passed"
            elif ai_verified is False:
                verify_icon = "gpp_bad"
                verify_class = "not-verified"
                header_text = "Verification Failed"
            else:
                verify_icon = "verified"
                verify_class = ""
                header_text = "Verification"

            return f"""
        <div class="step-ai-analysis {verify_class}">
            <div class="ai-header">
                <span class="material-symbols-outlined">{verify_icon}</span>
                {header_text}
            </div>
            <div class="ai-outcome">{html.escape(ai_outcome)}</div>
        </div>"""
        else:
            # Observation: muted informational styling
            return f"""
        <div class="step-ai-observation">
            <div class="ai-observation-header">
                <span class="material-symbols-outlined">visibility</span>
                AI Observation
            </div>
            <div class="ai-observation-text">{html.escape(ai_outcome)}</div>
        </div>"""

    def _get_failure_suggestion(self, error: str) -> str:
        """Get a suggested reason based on the error message."""
        error_lower = error.lower()
        for pattern, suggestion in self.FAILURE_SUGGESTIONS.items():
            if pattern in error_lower:
                return suggestion
        return (
            "An unexpected error occurred. Check the error message for details "
            "and verify the test configuration."
        )

    def _get_action_frame_for_step(self, step: dict[str, Any]) -> str | None:
        """Select the primary action frame to display based on gesture type.

        For swipe/long_press with two action frames, shows the more informative one.
        """
        action = step.get("action", "")
        screenshot_action = step.get("screenshot_action")
        screenshot_action_end = step.get("screenshot_action_end")

        if action == "swipe":
            # For swipe: prefer swipe_start (shows finger position at start)
            return screenshot_action or screenshot_action_end
        elif action == "long_press":
            # For long_press: prefer press_held (shows held state)
            return screenshot_action_end or screenshot_action
        else:
            # For tap/double_tap: single action frame
            return screenshot_action

    def _generate_screenshots_html(self, step: dict[str, Any]) -> str:
        """Generate HTML for before/action/after screenshots.

        Uses 3-column layout when action screenshot is available,
        falls back to 2-column layout otherwise.
        """
        before = step.get("screenshot_before")
        after = step.get("screenshot_after")
        action_frame = self._get_action_frame_for_step(step)

        if not before and not after:
            return ""

        # Generate gesture indicator for action frame
        gesture_html = self._generate_gesture_indicator_html(step)

        # 3-column layout if action frame available
        if action_frame:
            before_html = self._generate_frame_html("before", "Before", before)
            action_html = self._generate_frame_html("action", "Action", action_frame, gesture_html)
            after_html = self._generate_frame_html("after", "After", after)

            return f"""<div class="step-frames">
    {before_html}
    {action_html}
    {after_html}
</div>"""

        # 2-column fallback for steps without action frames
        before_html = self._generate_frame_html("before", "Before", before, gesture_html)
        after_html = self._generate_frame_html("after", "After", after)

        return f"""<div class="step-frames two-column">
    {before_html}
    {after_html}
</div>"""

    def _generate_gesture_indicator_html(self, step: dict[str, Any]) -> str:
        """Generate HTML for gesture indicator overlay with animations."""
        coords = step.get("coords")
        if not coords:
            return ""

        action = step.get("action", "")
        x = coords.get("x", 0)
        y = coords.get("y", 0)

        if action in ("tap", "double_tap"):
            return f"""<div class="gesture-indicator-container">
    <div class="tap-indicator" style="left: {x:.1f}%; top: {y:.1f}%;"></div>
</div>"""

        if action == "long_press":
            return f"""<div class="gesture-indicator-container">
    <div class="long-press-indicator" style="left: {x:.1f}%; top: {y:.1f}%;"></div>
</div>"""

        if action == "swipe":
            end_coords = step.get("end_coords", {})
            end_x = end_coords.get("x", x)
            end_y = end_coords.get("y", y)
            trajectory = step.get("trajectory", [])
            direction = step.get("direction", "up")

            # Encode trajectory as JSON for JavaScript
            traj_json = html.escape(json.dumps(trajectory)) if trajectory else "[]"

            return f"""<div class="gesture-indicator-container">
<div class="swipe-indicator"
    data-x="{x:.1f}" data-y="{y:.1f}"
    data-end-x="{end_x:.1f}" data-end-y="{end_y:.1f}"
    data-trajectory="{traj_json}"
    data-direction="{direction}">
    <div class="swipe-trajectory-line"></div>
    <div class="swipe-dot"></div>
</div>
</div>"""

        return ""

    def _generate_frame_html(
        self, frame_type: str, label: str, image_data: str | None,
        overlay_html: str = ""
    ) -> str:
        """Generate HTML for a single frame column."""
        if image_data:
            image_html = (
                f'<img src="{image_data}" alt="{label}" '
                f'onclick="openImageModal(this.src)">'
            )
        else:
            image_html = '<div class="frame-placeholder">No screenshot</div>'

        return f"""<div class="frame-column {frame_type}">
    <div class="frame-column-header">{label}</div>
    <div class="frame-image-container">
        {image_html}
        {overlay_html}
    </div>
</div>"""

    def _generate_video_html(self) -> str:
        """Generate video player HTML if video exists.

        Checks multiple locations:
        1. output_dir/recording/video.mp4 (from --video flag during test run)
        2. source_video_path (from original recording session)
        """
        # Check for video recorded during test run
        run_video_path = self._output_dir / "recording" / "video.mp4"
        if run_video_path.exists():
            return """<div class="video-panel" id="videoPanel">
    <div class="video-container">
        <div class="video-wrapper">
            <video id="reportVideo" src="recording/video.mp4" controls></video>
        </div>
    </div>
</div>"""

        # Check for source video from recording session
        if self._source_video_path and self._source_video_path.exists():
            # Calculate relative path from output_dir to source video
            try:
                rel_path = self._source_video_path.resolve().relative_to(
                    self._output_dir.resolve()
                )
                video_src = str(rel_path)
            except ValueError:
                # Not relative, use path relative to report's parent directories
                # e.g., reports/2024-01-18/report.html -> ../../video.mp4
                video_src = str(
                    Path("..") / ".." / self._source_video_path.name
                )
            return f"""<div class="video-panel" id="videoPanel">
    <div class="video-container">
        <div class="video-wrapper">
            <video id="reportVideo" src="{video_src}" controls></video>
        </div>
    </div>
</div>"""

        return """<div class="video-panel" id="videoPanel">
    <div class="video-container">
        <div class="no-video">
            <span class="material-symbols-outlined">videocam_off</span>
            <span>No recording available</span>
        </div>
    </div>
</div>"""
