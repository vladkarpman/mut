"""Device interaction via adb."""

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class DeviceController:
    """Device interaction via adb commands."""

    def __init__(self, device_id: str):
        """Initialize controller for a specific device.

        Args:
            device_id: ADB device identifier
        """
        self._device_id = device_id

    @staticmethod
    def list_devices() -> list[dict[str, str]]:
        """List connected Android devices.

        Returns:
            List of device dicts with id, name, status
        """
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
        )

        devices = []
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]

                # Extract device name from properties
                name = "unknown"
                model_match = re.search(r"model:(\S+)", line)
                if model_match:
                    name = model_match.group(1).replace("_", " ")

                devices.append({
                    "id": device_id,
                    "name": name,
                    "status": status,
                })

        return devices

    def tap(self, x: int, y: int) -> None:
        """Tap at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        self._adb(["shell", "input", "tap", str(x), str(y)])

    def long_press(self, x: int, y: int, duration_ms: int = 500) -> None:
        """Long press at coordinates.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            duration_ms: Duration in milliseconds (default: 500)
        """
        if x < 0 or y < 0:
            raise ValueError(f"Coordinates must be non-negative: ({x}, {y})")
        if duration_ms <= 0:
            raise ValueError(f"Duration must be positive: {duration_ms}")
        # Swipe from same point to same point = long press
        self._adb([
            "shell", "input", "swipe",
            str(x), str(y), str(x), str(y), str(duration_ms)
        ])

    def long_press_async(self, x: int, y: int, duration_ms: int = 500) -> subprocess.Popen:
        """Start long press without blocking.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            duration_ms: Duration in milliseconds (default: 500)

        Returns:
            Popen process to wait on for completion
        """
        if x < 0 or y < 0:
            raise ValueError(f"Coordinates must be non-negative: ({x}, {y})")
        if duration_ms <= 0:
            raise ValueError(f"Duration must be positive: {duration_ms}")
        cmd = [
            "adb", "-s", self._device_id, "shell", "input", "swipe",
            str(x), str(y), str(x), str(y), str(duration_ms)
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def double_tap(self, x: int, y: int, delay_ms: int = 100) -> None:
        """Double tap at coordinates.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            delay_ms: Delay between taps in milliseconds (default: 100)
        """
        if x < 0 or y < 0:
            raise ValueError(f"Coordinates must be non-negative: ({x}, {y})")
        if delay_ms < 0:
            raise ValueError(f"Delay must be non-negative: {delay_ms}")
        self._adb(["shell", "input", "tap", str(x), str(y)])
        time.sleep(delay_ms / 1000)
        self._adb(["shell", "input", "tap", str(x), str(y)])

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        """Swipe gesture.

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate
            duration_ms: Swipe duration in milliseconds
        """
        self._adb([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        ])

    def swipe_async(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> subprocess.Popen:
        """Start swipe gesture without blocking.

        Args:
            x1: Start X coordinate
            y1: Start Y coordinate
            x2: End X coordinate
            y2: End Y coordinate
            duration_ms: Swipe duration in milliseconds

        Returns:
            Popen process to wait on for completion
        """
        cmd = [
            "adb", "-s", self._device_id, "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def type_text(self, text: str) -> None:
        """Type text into focused field.

        Args:
            text: Text to type
        """
        # Escape special characters for adb
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self._adb(["shell", "input", "text", escaped])

    def press_key(self, keycode: str) -> None:
        """Press a key.

        Args:
            keycode: Key name (BACK, HOME, ENTER, etc.)
        """
        keycodes = {
            "BACK": 4,
            "HOME": 3,
            "ENTER": 66,
            "VOLUME_UP": 24,
            "VOLUME_DOWN": 25,
            "POWER": 26,
            "MENU": 82,
        }

        code = keycodes.get(keycode.upper())
        if code is None:
            raise ValueError(f"Unknown keycode: {keycode}")

        self._adb(["shell", "input", "keyevent", str(code)])

    def list_elements(self, max_retries: int = 10) -> list[dict[str, Any]]:
        """Get UI elements via uiautomator with retry (mobile-mcp style).

        Uses exec-out for faster dump (no file write/pull).
        Retries up to 10 times for "null root node" errors.

        Args:
            max_retries: Maximum dump attempts

        Returns:
            List of element dicts with text, bounds, class, etc.
        """
        for attempt in range(max_retries):
            try:
                # Fast dump directly to stdout (mobile-mcp style)
                result = subprocess.run(
                    ["adb", "-s", self._device_id, "exec-out", "uiautomator", "dump", "/dev/tty"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                output = result.stdout

                # Check for known error that requires retry
                if "null root node returned" in output.lower():
                    if attempt < max_retries - 1:
                        time.sleep(0.3)
                        continue
                    return []

                # Extract XML portion (skip any warnings before <?xml)
                xml_start = output.find("<?xml")
                if xml_start == -1:
                    xml_start = output.find("<hierarchy")
                if xml_start == -1:
                    if attempt < max_retries - 1:
                        time.sleep(0.3)
                        continue
                    return []

                xml_content = output[xml_start:]

                # Parse XML
                elements = self._parse_ui_xml_string(xml_content)

                # Filter elements with positive dimensions
                elements = [
                    el for el in elements
                    if el.get("bounds") and
                    el["bounds"][2] > el["bounds"][0] and
                    el["bounds"][3] > el["bounds"][1]
                ]

                if elements:
                    return elements

                # Empty result - retry
                if attempt < max_retries - 1:
                    time.sleep(0.3)

            except (subprocess.TimeoutExpired, RuntimeError):
                if attempt < max_retries - 1:
                    time.sleep(0.3)

        return []

    def _parse_ui_xml_string(self, xml_content: str) -> list[dict[str, Any]]:
        """Parse uiautomator XML string directly.

        Args:
            xml_content: XML string content

        Returns:
            List of element dicts
        """
        elements = []

        try:
            root = ET.fromstring(xml_content)

            for node in root.iter("node"):
                bounds_str = node.get("bounds", "")
                bounds = self._parse_bounds(bounds_str)

                elements.append({
                    "text": node.get("text", ""),
                    "content-desc": node.get("content-desc", ""),
                    "class": node.get("class", ""),
                    "resource-id": node.get("resource-id", ""),
                    "clickable": node.get("clickable") == "true",
                    "focused": node.get("focused") == "true",
                    "bounds": bounds,
                })

        except ET.ParseError:
            pass

        return elements

    def find_element(self, text: str) -> tuple[int, int] | None:
        """Find element by text, content-desc, or resource-id (mobile-mcp style).

        Uses multi-pass matching strategy:
        1. Exact match on text/content-desc
        2. Case-insensitive match
        3. Contains match
        4. Resource-id match (full or partial)

        Args:
            text: Text to find

        Returns:
            (x, y) center coordinates or None if not found
        """
        elements = self.list_elements()
        text_lower = text.lower()

        def get_center(el: dict[str, Any]) -> tuple[int, int] | None:
            bounds = el.get("bounds")
            if bounds:
                return ((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2)
            return None

        # Pass 1: Exact match on text or content-desc
        for el in elements:
            if el.get("text") == text or el.get("content-desc") == text:
                coords = get_center(el)
                if coords:
                    return coords

        # Pass 2: Case-insensitive match
        for el in elements:
            el_text = (el.get("text") or "").lower()
            el_desc = (el.get("content-desc") or "").lower()
            if el_text == text_lower or el_desc == text_lower:
                coords = get_center(el)
                if coords:
                    return coords

        # Pass 3: Contains match (text contains search term)
        for el in elements:
            el_text = (el.get("text") or "").lower()
            el_desc = (el.get("content-desc") or "").lower()
            if text_lower in el_text or text_lower in el_desc:
                coords = get_center(el)
                if coords:
                    return coords

        # Pass 4: Resource-id match (full or partial)
        for el in elements:
            resource_id = el.get("resource-id", "")
            if resource_id:
                rid_lower = resource_id.lower()
                # Full match, ends-with, or contains
                if (rid_lower == text_lower or
                    rid_lower.endswith(f"/{text_lower}") or
                    text_lower in rid_lower):
                    coords = get_center(el)
                    if coords:
                        return coords

        return None

    def get_screen_size(self) -> tuple[int, int]:
        """Get device screen size.

        Returns:
            (width, height) in pixels
        """
        result = self._adb(["shell", "wm", "size"])
        # Output: "Physical size: 1080x2340"
        match = re.search(r"(\d+)x(\d+)", result)
        if match:
            return int(match.group(1)), int(match.group(2))
        raise RuntimeError("Could not determine screen size")

    def take_screenshot(self) -> bytes:
        """Capture screenshot from device.

        Returns:
            PNG image bytes
        """
        # Capture screenshot directly to stdout as PNG
        result = subprocess.run(
            ["adb", "-s", self._device_id, "exec-out", "screencap", "-p"],
            capture_output=True,
            check=True,
        )
        return result.stdout

    def launch_app(self, package: str) -> None:
        """Launch an app by package name.

        Args:
            package: App package name (e.g., com.example.app)
        """
        self._adb([
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1"
        ])

    def terminate_app(self, package: str) -> None:
        """Force stop an app.

        Args:
            package: App package name
        """
        self._adb(["shell", "am", "force-stop", package])

    def set_show_touches(self, enabled: bool) -> None:
        """Enable or disable touch visualization on screen.

        This shows visual indicators for touches on the device screen,
        useful for recording demonstrations or debugging.

        Args:
            enabled: True to show touches, False to hide
        """
        value = "1" if enabled else "0"
        self._adb(["shell", "settings", "put", "system", "show_touches", value])

    def get_show_touches(self) -> bool:
        """Get current show_touches setting.

        Returns:
            True if show_touches is enabled
        """
        result = self._adb(["shell", "settings", "get", "system", "show_touches"])
        return result.strip() == "1"

    def _adb(self, args: list[str]) -> str:
        """Execute adb command.

        Args:
            args: Command arguments (without 'adb -s device')

        Returns:
            Command stdout
        """
        cmd = ["adb", "-s", self._device_id] + args
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"adb command failed: {result.stderr}")

        return result.stdout

    def _parse_ui_xml(self, xml_path: Path) -> list[dict[str, Any]]:
        """Parse uiautomator XML dump (handles warnings before XML).

        uiautomator sometimes prints warnings before the actual XML content.
        This method strips those warnings and parses just the XML.

        Args:
            xml_path: Path to XML file

        Returns:
            List of element dicts
        """
        elements = []

        try:
            content = xml_path.read_text(encoding="utf-8", errors="ignore")

            # Strip any content before the XML declaration or root element
            # uiautomator may print warnings like "UI hierchary dumped to: ..."
            xml_start = content.find("<?xml")
            if xml_start == -1:
                xml_start = content.find("<hierarchy")
            if xml_start > 0:
                content = content[xml_start:]

            # Parse the cleaned XML
            root = ET.fromstring(content)

            for node in root.iter("node"):
                bounds_str = node.get("bounds", "")
                bounds = self._parse_bounds(bounds_str)

                elements.append({
                    "text": node.get("text", ""),
                    "content-desc": node.get("content-desc", ""),
                    "class": node.get("class", ""),
                    "resource-id": node.get("resource-id", ""),
                    "clickable": node.get("clickable") == "true",
                    "bounds": bounds,
                })

        except (ET.ParseError, OSError):
            pass

        return elements

    def _parse_bounds(self, bounds_str: str) -> list[int] | None:
        """Parse bounds string like '[0,0][1080,2340]'.

        Returns:
            [x1, y1, x2, y2] or None
        """
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if match:
            return [int(g) for g in match.groups()]
        return None
