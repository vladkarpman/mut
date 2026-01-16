"""Test report generation."""

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mutcli.core.executor import TestResult


class ReportGenerator:
    """Generate JSON and HTML test reports."""

    def __init__(self, output_dir: Path):
        """Initialize generator.

        Args:
            output_dir: Directory to write reports
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

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
        """Generate HTML report.

        Args:
            result: Test execution result

        Returns:
            Path to generated report.html
        """
        data = self._result_to_dict(result)
        html = self._render_html(data)

        path = self._output_dir / "report.html"
        with open(path, "w") as f:
            f.write(html)

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

    def _render_html(self, data: dict[str, Any]) -> str:  # noqa: E501
        """Render HTML report from data."""
        status_color = {
            "passed": "#22c55e",
            "failed": "#ef4444",
            "error": "#ef4444",
            "skipped": "#f59e0b",
        }

        # Escape user-controlled values to prevent XSS
        test_name = html.escape(data["test"])

        steps_html = ""
        for step in data["steps"]:
            color = status_color.get(step["status"], "#6b7280")
            if step["status"] == "passed":
                icon = "[PASS]"
            elif step["status"] == "failed":
                icon = "[FAIL]"
            else:
                icon = "[SKIP]"
            error_html = ""
            if step["error"]:
                escaped_error = html.escape(step["error"])
                error_html = f'<div class="error">{escaped_error}</div>'
            escaped_action = html.escape(step["action"])
            steps_html += f"""
            <div class="step-wrapper">
                <div class="step">
                    <span class="icon">{icon}</span>
                    <span class="action">Step {step["number"]}: {escaped_action}</span>
                    <span class="duration">{step["duration"]}</span>
                    <span class="status" style="color: {color}">{step["status"]}</span>
                </div>
                {error_html}
            </div>
            """

        main_color = status_color.get(data["status"], "#6b7280")
        status_upper = data["status"].upper()
        skipped_count = data["summary"]["skipped"]

        # Build HTML with CSS split across lines for readability
        css = """
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0; padding: 20px;
            background: #0f172a; color: #e2e8f0;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #f8fafc; }
        .summary {
            background: #1e293b; padding: 20px;
            border-radius: 8px; margin: 20px 0;
        }
        .summary-grid {
            display: grid; grid-template-columns: repeat(4, 1fr);
            gap: 16px; margin-top: 16px;
        }
        .stat { text-align: center; }
        .stat-value { font-size: 2rem; font-weight: bold; }
        .stat-label { color: #94a3b8; }
        .status { font-weight: bold; }
        .steps { background: #1e293b; padding: 20px; border-radius: 8px; }
        .step-wrapper { padding: 12px 0; border-bottom: 1px solid #334155; }
        .step-wrapper:last-child { border-bottom: none; }
        .step {
            display: flex; align-items: center; gap: 12px;
        }
        .icon { font-size: 1.2rem; }
        .action { flex: 1; }
        .duration { color: #94a3b8; }
        .error { color: #fca5a5; font-size: 0.9rem; margin-top: 8px; padding-left: 32px; }
        """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Test Report: {test_name}</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <h1>Test Report</h1>

        <div class="summary">
            <div>
                <strong>Test:</strong> {test_name}<br>
                <strong>Status:</strong>
                <span class="status" style="color: {main_color}">{status_upper}</span><br>
                <strong>Duration:</strong> {data["duration"]}<br>
                <strong>Time:</strong> {data["timestamp"]}
            </div>

            <div class="summary-grid">
                <div class="stat">
                    <div class="stat-value">{data["summary"]["total"]}</div>
                    <div class="stat-label">Total</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #22c55e">
                        {data["summary"]["passed"]}
                    </div>
                    <div class="stat-label">Passed</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #ef4444">
                        {data["summary"]["failed"]}
                    </div>
                    <div class="stat-label">Failed</div>
                </div>
                <div class="stat">
                    <div class="stat-value" style="color: #f59e0b">{skipped_count}</div>
                    <div class="stat-label">Skipped</div>
                </div>
            </div>
        </div>

        <div class="steps">
            <h2>Steps</h2>
            {steps_html}
        </div>
    </div>
</body>
</html>"""
