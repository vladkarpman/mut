"""Report server for viewing test reports."""

from __future__ import annotations

import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ReportServer:
    """Local HTTP server for viewing test reports.

    Regenerates HTML from template + report.json data on each request.
    This ensures bug fixes in the template apply to old reports.
    """

    def __init__(self, report_dir: Path, port: int = 8766):
        """Initialize report server.

        Args:
            report_dir: Directory containing report.json, screenshots/, recording/
            port: Port to serve on
        """
        self.report_dir = Path(report_dir)
        self.port = port
        self._server: HTTPServer | None = None

    def start_and_wait(self) -> None:
        """Start server, open browser, serve until interrupted."""
        handler = self._create_handler()
        self._server = self._create_server_with_available_port(handler)

        # Open browser
        url = f"http://localhost:{self.port}/"
        webbrowser.open(url)

        # Serve forever
        self._server.serve_forever()

    def _create_server_with_available_port(
        self, handler: type[BaseHTTPRequestHandler], max_attempts: int = 10
    ) -> HTTPServer:
        """Create HTTP server, trying subsequent ports if default is busy."""
        import errno

        for attempt in range(max_attempts):
            port = self.port + attempt
            try:
                server = HTTPServer(("localhost", port), handler)
                self.port = port
                return server
            except OSError as e:
                if e.errno == errno.EADDRINUSE and attempt < max_attempts - 1:
                    continue
                raise

        raise OSError(f"Could not find available port after {max_attempts} attempts")

    def _load_template(self) -> str:
        """Load HTML template from templates directory."""
        template_path = Path(__file__).parent.parent / "templates" / "report.html"
        return template_path.read_text()

    def _load_report_data(self) -> dict[str, Any]:
        """Load report.json data."""
        report_json = self.report_dir / "report.json"
        with open(report_json) as f:
            return json.load(f)

    def _fix_screenshot_paths(self, data: dict[str, Any]) -> dict[str, Any]:
        """Fix screenshot paths to include screenshots/ prefix if needed."""
        for step in data.get("steps", []):
            for key in ["screenshot_before", "screenshot_after", "screenshot_action", "screenshot_action_end"]:
                path = step.get(key)
                if path and not path.startswith("data:") and not path.startswith("screenshots/"):
                    # Check if file exists in screenshots folder
                    if (self.report_dir / "screenshots" / path).exists():
                        step[key] = f"screenshots/{path}"
        return data

    def _generate_html(self) -> str:
        """Generate HTML report from template and data."""
        from mutcli.core.report import ReportGenerator

        template = self._load_template()
        data = self._load_report_data()
        data = self._fix_screenshot_paths(data)

        # Get video path
        video_path = "recording/video.mp4"
        if not (self.report_dir / "recording" / "video.mp4").exists():
            # Check for source video in parent test dir
            parent_video = self.report_dir.parent.parent / "video.mp4"
            if parent_video.exists():
                video_path = f"../../video.mp4"

        # Create a temporary generator just to use its HTML generation methods
        generator = ReportGenerator(self.report_dir)

        # Generate steps HTML
        steps_html = generator._generate_steps_html(data["steps"])

        # Determine status
        status = data.get("status", "unknown")
        status_icons = {"passed": "check_circle", "failed": "cancel", "error": "error"}
        status_icon = status_icons.get(status, "help")
        status_class = status if status in ("passed", "failed") else "unknown"

        # Calculate summary
        summary = data.get("summary", {})
        total = summary.get("total", len(data.get("steps", [])))
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)

        # Format duration
        duration = data.get("duration", "0s")

        # Generate step navigator
        step_numbers = [s.get("number", i+1) for i, s in enumerate(data.get("steps", []))]
        step_nav_html = "\n".join([
            f'<button class="step-nav-btn" onclick="scrollToStep({n})">{n}</button>'
            for n in step_numbers
        ])

        # Generate video HTML with proper wrapper structure
        video_html = f'''<div class="video-panel">
            <div class="video-container">
                <div class="video-wrapper">
                    <video controls preload="metadata">
                        <source src="{video_path}" type="video/mp4">
                    </video>
                </div>
            </div>
        </div>'''

        # Escape data for JSON embedding
        import html as html_module
        json_data = json.dumps(data)
        json_data_escaped = html_module.escape(json_data)

        # Fill template using {{placeholder}} syntax (double braces)
        # NOTE: json_data is inserted AFTER brace unescaping to preserve JSON structure
        replacements = {
            "{{test_name}}": data.get("test", "Unknown Test"),
            "{{status}}": status,
            "{{status_icon}}": status_icon,
            "{{status_class}}": status_class,
            "{{duration}}": duration,
            "{{summary_total}}": str(total),
            "{{summary_passed}}": str(passed),
            "{{summary_failed}}": str(failed),
            "{{video_html}}": video_html,
            "{{steps_html}}": steps_html,
        }

        html = template
        for placeholder, value in replacements.items():
            html = html.replace(placeholder, value)

        # Convert escaped braces to single braces for valid CSS/JS
        # IMPORTANT: Do this BEFORE inserting JSON data, because JSON contains
        # nested objects with }} that would be corrupted by the replacement
        html = html.replace("{{", "{").replace("}}", "}")

        # Insert JSON data AFTER brace unescaping to preserve JSON structure
        html = html.replace("{json_data}", json_data)

        return html

    def _create_handler(self) -> type[BaseHTTPRequestHandler]:
        """Create request handler with access to server state."""
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress default HTTP logging - we have our own
                pass

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                print(f"[ReportServer] GET {path}")

                try:
                    if path == "/" or path == "/report.html":
                        self._serve_report()
                    elif path.startswith("/screenshots/") or path.startswith("/recording/"):
                        self._serve_file(path)
                    elif path == "/video.mp4":
                        self._serve_file("/recording/video.mp4")
                    else:
                        print(f"[ReportServer] 404 for {path}")
                        self.send_error(404)
                except BrokenPipeError:
                    # Client disconnected mid-transfer (common during video seeking)
                    pass
                except ConnectionResetError:
                    # Client reset connection
                    pass

            def _serve_report(self) -> None:
                try:
                    print("[ReportServer] Generating HTML...")
                    html = server._generate_html()
                    print(f"[ReportServer] Generated {len(html)} bytes")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                except Exception as e:
                    self.send_error(500, str(e))

            def _serve_file(self, path: str) -> None:
                """Serve files from report directory."""
                relative_path = path.lstrip("/")
                file_path = server.report_dir / relative_path

                if not (file_path.exists() and file_path.is_file()):
                    self.send_error(404)
                    return

                file_size = file_path.stat().st_size
                content_type, _ = mimetypes.guess_type(str(file_path))
                if content_type is None:
                    content_type = "application/octet-stream"

                # Handle Range requests for video seeking
                range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    range_spec = range_header[6:]
                    parts = range_spec.split("-")
                    start = int(parts[0]) if parts[0] else 0
                    end = int(parts[1]) if parts[1] else file_size - 1
                    end = min(end, file_size - 1)
                    content_length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(content_length))
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(file_path, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(content_length))
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(file_size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())

        return Handler
