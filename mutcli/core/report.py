"""Test report generation."""

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mutcli.core.executor import TestResult


class ReportGenerator:
    """Generate JSON and HTML test reports."""

    # Status icons
    STATUS_ICONS = {
        "passed": "&#10003;",  # checkmark
        "failed": "&#10007;",  # X mark
        "skipped": "&#8212;",  # em dash
    }

    # Action CSS class mappings
    ACTION_CLASSES = {
        "tap": "tap",
        "swipe": "swipe",
        "verify_screen": "verify_screen",
        "verify": "verify",
        "wait": "wait",
        "wait_for": "wait_for",
        "type": "type",
        "long_press": "long_press",
        "scroll_to": "scroll_to",
        "launch_app": "launch_app",
        "terminate_app": "terminate_app",
    }

    def __init__(self, output_dir: Path):
        """Initialize generator.

        Args:
            output_dir: Directory to write reports
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

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

        # Load and populate template
        template = self._load_template()
        html_content = template.replace("{{test_name}}", html.escape(data["test"]))
        html_content = html_content.replace("{{status}}", data["status"])
        html_content = html_content.replace("{{status_class}}", data["status"])
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
                    "duration": f"{s.duration:.1f}s",
                    "error": s.error,
                    "screenshot_before": self._encode_screenshot(s.screenshot_before),
                    "screenshot_after": self._encode_screenshot(s.screenshot_after),
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
        action_class = self.ACTION_CLASSES.get(action, action)
        status_icon = self.STATUS_ICONS.get(status, "")
        escaped_action = html.escape(action)

        # Error message HTML (if any)
        error_html = ""
        if step["error"]:
            escaped_error = html.escape(step["error"])
            error_html = f'<div class="step-error">{escaped_error}</div>'

        # Screenshots HTML (if any)
        screenshots_html = self._generate_screenshots_html(step)

        return f"""<div class="step-card {status}" data-status="{status}" \
data-index="{index}" onclick="selectStep({index})">
    <div class="step-header">
        <div class="step-title">
            <div class="step-number {status}">{step["number"]}</div>
            <span class="action-badge {action_class}">{escaped_action}</span>
            <span class="step-description">{html.escape(str(step.get("target", "")))}</span>
        </div>
        <div class="step-meta">
            <span class="step-duration">{step["duration"]}</span>
            <span class="step-status-icon {status}">{status_icon}</span>
        </div>
    </div>
    {error_html}
    {screenshots_html}
</div>"""

    def _generate_screenshots_html(self, step: dict[str, Any]) -> str:
        """Generate HTML for before/after screenshots."""
        before = step.get("screenshot_before")
        after = step.get("screenshot_after")

        if not before and not after:
            return ""

        before_html = self._generate_frame_html("before", "Before", before)
        after_html = self._generate_frame_html("after", "After", after)

        return f"""<div class="step-frames">
    {before_html}
    {after_html}
</div>"""

    def _generate_frame_html(
        self, frame_type: str, label: str, image_data: str | None
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
    </div>
</div>"""

    def _generate_video_html(self) -> str:
        """Generate video player HTML if video exists."""
        video_path = self._output_dir / "recording" / "recording.mp4"
        if not video_path.exists():
            return ""

        return """<div class="video-panel" id="videoPanel">
    <div class="video-panel-header">Recording</div>
    <div class="video-container">
        <div class="video-wrapper">
            <video id="reportVideo" preload="metadata">
                <source src="recording/recording.mp4" type="video/mp4">
                Your browser does not support video playback.
            </video>
        </div>
        <div class="video-controls">
            <button class="video-play-btn" id="videoPlayBtn">&#9658;</button>
            <input type="range" class="video-scrubber" id="videoScrubber"
                   value="0" min="0" max="100">
            <span class="video-time" id="videoTime">0:00 / 0:00</span>
        </div>
    </div>
</div>"""
