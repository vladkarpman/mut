"""Preview server for recording approval UI."""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class PreviewStep:
    """A step shown in the preview UI."""

    index: int
    action: str  # tap, swipe, type, etc.
    element_text: str | None
    coordinates: tuple[int, int]
    screenshot_path: str | None
    enabled: bool = True
    before_description: str = ""
    after_description: str = ""
    direction: str | None = None
    timestamp: float = 0.0
    frames: dict[str, str | None] = field(default_factory=dict)
    analysis: dict[str, str] = field(default_factory=dict)
    suggested_verification: str | None = None
    tap_count: int | None = None  # Number of keyboard taps for type action
    text: str | None = None  # User-entered text for type action


@dataclass
class ApprovalResult:
    """Result from the approval UI."""

    approved: bool
    steps: list[dict[str, Any]]
    verifications: list[dict[str, Any]]


class PreviewServer:
    """Local HTTP server for recording preview and approval."""

    def __init__(
        self,
        steps: list[PreviewStep],
        verifications: list[dict[str, Any]],
        test_name: str,
        app_package: str,
        recording_dir: Path,
        port: int = 8765,
        screen_width: int = 1080,
        screen_height: int = 2340,
        video_duration: str = "0:00",
    ):
        self.steps = steps
        self.verifications = verifications
        self.test_name = test_name
        self.app_package = app_package
        self.recording_dir = recording_dir
        self.port = port
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.video_duration = video_duration
        self.result: ApprovalResult | None = None
        self._server: HTTPServer | None = None
        self._shutdown_event = threading.Event()

    def start_and_wait(self) -> ApprovalResult | None:
        """Start server, open browser, wait for approval, return result."""
        handler = self._create_handler()
        self._server = self._create_server_with_available_port(handler)

        # Open browser
        url = f"http://localhost:{self.port}/preview"
        webbrowser.open(url)

        # Serve until approval or cancel
        while not self._shutdown_event.is_set():
            self._server.handle_request()

        return self.result

    def _create_server_with_available_port(
        self, handler: type[BaseHTTPRequestHandler], max_attempts: int = 10
    ) -> HTTPServer:
        """Create HTTP server, trying subsequent ports if default is busy."""
        import errno

        for attempt in range(max_attempts):
            port = self.port + attempt
            try:
                server = HTTPServer(("localhost", port), handler)
                self.port = port  # Update to actual port used
                return server
            except OSError as e:
                if e.errno == errno.EADDRINUSE and attempt < max_attempts - 1:
                    continue
                raise

        raise OSError(f"Could not find available port after {max_attempts} attempts")

    def _load_template(self) -> str:
        """Load HTML template from templates directory."""
        template_path = Path(__file__).parent.parent / "templates" / "approval.html"
        return template_path.read_text()

    def _create_handler(self) -> type[BaseHTTPRequestHandler]:
        """Create request handler with access to server state."""
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress logging
                pass

            def do_GET(self) -> None:
                parsed = urlparse(self.path)

                if parsed.path == "/preview":
                    self._serve_preview()
                elif parsed.path.startswith("/recording/"):
                    self._serve_recording_file(parsed.path)
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                if self.path == "/approve":
                    self._handle_approve()
                elif self.path == "/cancel":
                    self._handle_cancel()
                else:
                    self.send_error(404)

            def _serve_preview(self) -> None:
                html = server._generate_html()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def _serve_recording_file(self, path: str) -> None:
                """Serve files from recording directory (video, screenshots)."""
                # Remove /recording/ prefix
                relative_path = path.replace("/recording/", "", 1)
                file_path = server.recording_dir / relative_path

                if file_path.exists() and file_path.is_file():
                    # Determine content type
                    content_type, _ = mimetypes.guess_type(str(file_path))
                    if content_type is None:
                        content_type = "application/octet-stream"

                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(file_path.stat().st_size))
                    # Allow range requests for video seeking
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                else:
                    self.send_error(404)

            def _handle_approve(self) -> None:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)

                server.result = ApprovalResult(
                    approved=True,
                    steps=data.get("steps", []),
                    verifications=data.get("verifications", []),
                )

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())

                server._shutdown_event.set()

            def _handle_cancel(self) -> None:
                server.result = ApprovalResult(
                    approved=False,
                    steps=[],
                    verifications=[],
                )

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "cancelled"}).encode())

                server._shutdown_event.set()

        return Handler

    def _generate_html(self) -> str:
        """Generate the preview HTML page from template."""
        # Build test data structure matching the template's expectations
        test_data = {
            "testName": self.test_name,
            "appPackage": self.app_package,
            "device": {},
            "videoFile": "video.mp4",
            "videoDuration": self.video_duration,
            "steps": self._build_steps_data(),
            "availablePreconditions": [],
        }

        # Load and populate template
        template = self._load_template()

        # Replace placeholders
        html = template.replace("TEST_NAME_PLACEHOLDER", self.test_name)
        html = html.replace("TEST_DATA_PLACEHOLDER", json.dumps(test_data, indent=2))
        html = html.replace("SCREEN_WIDTH_PLACEHOLDER", str(self.screen_width))
        html = html.replace("SCREEN_HEIGHT_PLACEHOLDER", str(self.screen_height))

        return html

    def _build_steps_data(self) -> list[dict[str, Any]]:
        """Convert PreviewStep objects to template-compatible dicts."""
        steps_data = []

        for step in self.steps:
            step_id = f"step_{step.index:03d}"

            # Build frames dict with paths relative to recording/
            frames = {}
            if step.frames:
                frames = step.frames
            elif step.screenshot_path:
                # Legacy: single screenshot becomes before frame
                frames["before"] = f"recording/screenshots/before_{step.index:03d}.png"

            # Build analysis dict
            analysis = step.analysis if step.analysis else {
                "before": step.before_description or "",
                "action": "",
                "after": step.after_description or "",
            }

            step_data = {
                "id": step_id,
                "timestamp": step.timestamp,
                "action": step.action,
                "target": {
                    "x": step.coordinates[0],
                    "y": step.coordinates[1],
                    "text": step.element_text or "",
                },
                "direction": step.direction or "up",
                "waitAfter": 0,
                "frames": frames,
                "analysis": analysis,
                "suggestedVerification": step.suggested_verification,
                "enabled": step.enabled,
                "tapCount": step.tap_count,
                "text": step.text,
            }

            steps_data.append(step_data)

        return steps_data
