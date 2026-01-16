# tests/test_report.py
import json

import pytest

from mutcli.core.executor import StepResult, TestResult
from mutcli.core.report import ReportGenerator


class TestReportGenerator:
    @pytest.fixture
    def test_result(self):
        """Sample test result."""
        return TestResult(
            name="login-test",
            status="passed",
            duration=5.2,
            steps=[
                StepResult(step_number=1, action="tap", status="passed", duration=0.5),
                StepResult(step_number=2, action="type", status="passed", duration=0.3),
                StepResult(step_number=3, action="verify_screen", status="passed", duration=1.0),
            ],
        )

    def test_generates_json_report(self, test_result, tmp_path):
        """Generates valid JSON report."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        json_path = generator.generate_json(test_result)

        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["test"] == "login-test"
        assert data["status"] == "passed"
        assert data["summary"]["total"] == 3
        assert data["summary"]["passed"] == 3

    def test_generates_html_report(self, test_result, tmp_path):
        """Generates HTML report."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        generator.generate_json(test_result)
        html_path = generator.generate_html(test_result)

        assert html_path.exists()
        content = html_path.read_text()
        assert "login-test" in content
        assert "passed" in content.lower()

    def test_generates_json_report_with_failed_steps(self, tmp_path):
        """JSON report includes error details for failed steps."""
        result = TestResult(
            name="failed-test",
            status="failed",
            duration=2.5,
            steps=[
                StepResult(step_number=1, action="tap", status="passed", duration=0.5),
                StepResult(
                    step_number=2,
                    action="tap",
                    status="failed",
                    duration=0.3,
                    error="Element 'Submit' not found",
                ),
            ],
            error="Test failed at step 2",
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        json_path = generator.generate_json(result)
        data = json.loads(json_path.read_text())

        assert data["status"] == "failed"
        assert data["error"] == "Test failed at step 2"
        assert data["summary"]["failed"] == 1
        assert data["steps"][1]["error"] == "Element 'Submit' not found"

    def test_generates_report_with_empty_steps(self, tmp_path):
        """Handles test with no steps."""
        result = TestResult(name="empty-test", status="passed", duration=0.1, steps=[])
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        json_path = generator.generate_json(result)
        data = json.loads(json_path.read_text())

        assert data["summary"]["total"] == 0
        assert data["summary"]["passed"] == 0
        assert data["summary"]["failed"] == 0

    def test_html_report_with_errors_displays_correctly(self, tmp_path):
        """HTML report displays error messages for failed steps."""
        result = TestResult(
            name="error-test",
            status="failed",
            duration=1.5,
            steps=[
                StepResult(
                    step_number=1,
                    action="tap",
                    status="failed",
                    duration=0.5,
                    error="Element not found",
                ),
            ],
            error="Test failed",
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(result)

        content = html_path.read_text()
        assert "Element not found" in content
        assert "FAILED" in content
        assert 'class="error"' in content

    def test_html_escapes_special_characters(self, tmp_path):
        """HTML report escapes special characters to prevent XSS."""
        result = TestResult(
            name="<script>alert('xss')</script>",
            status="failed",
            duration=1.0,
            steps=[
                StepResult(
                    step_number=1,
                    action="<img src=x onerror=alert(1)>",
                    status="failed",
                    duration=0.5,
                    error="Error: <b>malicious</b> content",
                ),
            ],
            error="Test failed",
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(result)

        content = html_path.read_text()
        # Verify that HTML special characters are escaped
        assert "<script>" not in content
        assert "&lt;script&gt;" in content
        assert "<img src=x" not in content
        assert "&lt;img src=x" in content
        assert "<b>malicious</b>" not in content
        assert "&lt;b&gt;malicious&lt;/b&gt;" in content
