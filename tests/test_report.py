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
