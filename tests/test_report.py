# tests/test_report.py
import base64
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
        assert "failed" in content.lower()
        assert 'class="step-error"' in content

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
        # Verify that user-provided HTML special characters are escaped in HTML context
        # Test name appears in header (HTML escaped)
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in content
        # Action appears in step card (HTML escaped)
        assert "&lt;img src=x onerror=alert(1)&gt;" in content
        # Error message appears in step error (HTML escaped)
        assert "&lt;b&gt;malicious&lt;/b&gt;" in content

        # Verify that script-breaking sequences are escaped in JSON data
        # The </script> in user input must be escaped in JSON (as <\/script>)
        # to prevent breaking out of the script tag
        assert r"<\/script>" in content  # Escaped version should be present
        # The unescaped malicious input should not appear in the JSON context
        assert "<script>alert('xss')</script>" not in content

    def test_generate_html_uses_template(self, test_result, tmp_path):
        """HTML report uses the external template file."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(test_result)

        content = html_path.read_text()
        # Template contains these distinctive elements
        assert "<!DOCTYPE html>" in content
        assert '<html lang="en">' in content
        assert "step-card" in content
        assert "summary-bar" in content

    def test_html_contains_status_badge(self, tmp_path):
        """HTML report contains status badge with correct class."""
        result = TestResult(
            name="badge-test",
            status="passed",
            duration=1.0,
            steps=[
                StepResult(step_number=1, action="tap", status="passed", duration=0.5),
            ],
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(result)

        content = html_path.read_text()
        assert 'class="status-badge passed"' in content

    def test_html_contains_step_cards(self, test_result, tmp_path):
        """HTML report contains step cards with correct structure."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(test_result)

        content = html_path.read_text()
        # Check for step card structure
        assert 'class="step-card passed"' in content
        assert 'class="step-number passed"' in content
        assert 'class="action-badge tap"' in content
        assert 'class="action-badge type"' in content
        assert 'class="action-badge verify_screen"' in content

    def test_html_embeds_screenshots_as_base64(self, tmp_path):
        """HTML report embeds screenshots as base64 data URIs."""
        # Create a simple 1x1 PNG (minimal valid PNG)
        png_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
            b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
            b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        result = TestResult(
            name="screenshot-test",
            status="passed",
            duration=1.0,
            steps=[
                StepResult(
                    step_number=1,
                    action="tap",
                    status="passed",
                    duration=0.5,
                    screenshot_before=png_bytes,
                    screenshot_after=png_bytes,
                ),
            ],
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(result)

        content = html_path.read_text()
        # Check for base64 data URI
        expected_base64 = base64.b64encode(png_bytes).decode()
        assert f"data:image/png;base64,{expected_base64}" in content
        assert 'class="frame-column before"' in content
        assert 'class="frame-column after"' in content

    def test_html_shows_error_for_failed_steps(self, tmp_path):
        """HTML report shows error message for failed steps."""
        result = TestResult(
            name="error-display-test",
            status="failed",
            duration=1.0,
            steps=[
                StepResult(
                    step_number=1,
                    action="tap",
                    status="failed",
                    duration=0.5,
                    error="Could not find element 'Submit Button'",
                ),
            ],
            error="Test failed",
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(result)

        content = html_path.read_text()
        assert "Could not find element" in content
        assert 'class="step-error"' in content
        assert 'class="step-card failed"' in content

    def test_html_includes_json_export(self, test_result, tmp_path):
        """HTML report includes JSON data for export functionality."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(test_result)

        content = html_path.read_text()
        # Check that JSON data is embedded
        assert "const reportData =" in content
        assert '"test": "login-test"' in content
        assert "exportJSON()" in content

    def test_html_includes_video_player_when_video_exists(self, test_result, tmp_path):
        """HTML report includes video player when recording exists."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        # Create recording directory with video file
        recording_dir = output_dir / "recording"
        recording_dir.mkdir()
        video_file = recording_dir / "recording.mp4"
        video_file.write_bytes(b"fake video content")

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(test_result)

        content = html_path.read_text()
        assert 'class="video-panel"' in content
        assert 'id="reportVideo"' in content
        assert 'src="recording/recording.mp4"' in content

    def test_html_hides_video_player_when_no_video(self, test_result, tmp_path):
        """HTML report hides video player when no recording exists."""
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        html_path = generator.generate_html(test_result)

        content = html_path.read_text()
        # Video panel should not be present
        assert 'class="video-panel"' not in content

    def test_json_includes_screenshot_data(self, tmp_path):
        """JSON report includes screenshot data as base64."""
        png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...'

        result = TestResult(
            name="json-screenshot-test",
            status="passed",
            duration=1.0,
            steps=[
                StepResult(
                    step_number=1,
                    action="tap",
                    status="passed",
                    duration=0.5,
                    screenshot_before=png_bytes,
                    screenshot_after=None,
                ),
            ],
        )
        output_dir = tmp_path / "report"
        output_dir.mkdir()

        generator = ReportGenerator(output_dir)
        json_path = generator.generate_json(result)

        data = json.loads(json_path.read_text())
        step = data["steps"][0]
        assert step["screenshot_before"] is not None
        assert step["screenshot_before"].startswith("data:image/png;base64,")
        assert step["screenshot_after"] is None
