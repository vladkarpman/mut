"""Tests for PreviewServer port fallback functionality."""

from unittest.mock import patch

import pytest

from mutcli.core.preview_server import PreviewServer


@pytest.fixture
def minimal_server_args(tmp_path):
    """Minimal arguments required to create a PreviewServer."""
    return {
        "steps": [],
        "verifications": [],
        "test_name": "test",
        "app_package": "com.example",
        "recording_dir": tmp_path,
    }


class TestPortFallback:
    """Tests for PreviewServer port fallback mechanism."""

    def test_port_fallback_when_default_port_busy(self, minimal_server_args):
        """Verify second server uses next available port when default is busy."""
        # Use a unique base port to avoid conflicts with other services
        base_port = 18765

        # Create first server
        server1 = PreviewServer(**minimal_server_args, port=base_port)
        # Create second server with same default port
        server2 = PreviewServer(**minimal_server_args, port=base_port)

        with patch("webbrowser.open"):
            # Create handler for server1
            handler1 = server1._create_handler()
            # Actually bind server1 to the port
            http_server1 = server1._create_server_with_available_port(handler1)

            try:
                # Server1 should bind to base_port
                assert server1.port == base_port

                # Create handler for server2
                handler2 = server2._create_handler()
                # Server2 should find next available port
                http_server2 = server2._create_server_with_available_port(handler2)

                try:
                    # Server2 should have incremented to next port
                    assert server2.port == base_port + 1
                    assert server1.port != server2.port
                finally:
                    http_server2.server_close()
            finally:
                http_server1.server_close()

    def test_multiple_port_fallbacks(self, minimal_server_args):
        """Verify multiple servers find sequential available ports."""
        base_port = 18775
        servers = []
        http_servers = []

        try:
            with patch("webbrowser.open"):
                # Create 3 servers, all starting with the same default port
                for i in range(3):
                    server = PreviewServer(**minimal_server_args, port=base_port)
                    handler = server._create_handler()
                    http_server = server._create_server_with_available_port(handler)
                    servers.append(server)
                    http_servers.append(http_server)

                # Each server should have gotten a unique sequential port
                ports = [s.port for s in servers]
                assert ports == [base_port, base_port + 1, base_port + 2]
        finally:
            for hs in http_servers:
                hs.server_close()

    def test_port_fallback_exhausted_raises_error(self, minimal_server_args):
        """Verify OSError raised when max_attempts exceeded."""
        base_port = 18785
        servers = []
        http_servers = []
        max_attempts = 3

        try:
            with patch("webbrowser.open"):
                # Occupy all ports in the range
                for i in range(max_attempts):
                    server = PreviewServer(**minimal_server_args, port=base_port)
                    handler = server._create_handler()
                    http_server = server._create_server_with_available_port(
                        handler, max_attempts=max_attempts
                    )
                    servers.append(server)
                    http_servers.append(http_server)

                # Try to create one more server - should fail
                extra_server = PreviewServer(**minimal_server_args, port=base_port)
                handler = extra_server._create_handler()

                with pytest.raises(OSError):
                    extra_server._create_server_with_available_port(
                        handler, max_attempts=max_attempts
                    )
        finally:
            for hs in http_servers:
                hs.server_close()

    def test_server_updates_port_attribute(self, minimal_server_args):
        """Verify server.port is updated to actual bound port."""
        base_port = 18795

        server1 = PreviewServer(**minimal_server_args, port=base_port)
        server2 = PreviewServer(**minimal_server_args, port=base_port)

        # Initially both have the same requested port
        assert server1.port == base_port
        assert server2.port == base_port

        with patch("webbrowser.open"):
            handler1 = server1._create_handler()
            http_server1 = server1._create_server_with_available_port(handler1)

            try:
                # After binding, server1.port should still be base_port
                assert server1.port == base_port

                handler2 = server2._create_handler()
                http_server2 = server2._create_server_with_available_port(handler2)

                try:
                    # After binding, server2.port should be updated to the actual port
                    assert server2.port == base_port + 1
                finally:
                    http_server2.server_close()
            finally:
                http_server1.server_close()
