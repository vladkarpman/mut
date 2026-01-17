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

    def list_elements(self) -> list[dict[str, Any]]:
        """Get UI elements via uiautomator.

        Returns:
            List of element dicts with text, bounds, class, etc.
        """
        remote_path = "/sdcard/ui_dump.xml"
        local_path = Path(f"/tmp/ui_{self._device_id}.xml")

        # Dump UI hierarchy
        self._adb(["shell", "uiautomator", "dump", remote_path])

        # Pull to local
        self._adb(["pull", remote_path, str(local_path)])

        # Parse XML
        return self._parse_ui_xml(local_path)

    def find_element(self, text: str) -> tuple[int, int] | None:
        """Find element by text, content-desc, or resource-id.

        Args:
            text: Text to find. Matches against:
                  - text attribute
                  - content-desc (accessibility label)
                  - resource-id (full or partial, e.g. "digit_1" matches
                    "com.google.android.calculator:id/digit_1")

        Returns:
            (x, y) center coordinates or None if not found
        """
        elements = self.list_elements()

        for el in elements:
            # Match text or content-desc exactly
            if el.get("text") == text or el.get("content-desc") == text:
                bounds = el.get("bounds")
                if bounds:
                    x = (bounds[0] + bounds[2]) // 2
                    y = (bounds[1] + bounds[3]) // 2
                    return (x, y)

            # Match resource-id (full or partial after last /)
            resource_id = el.get("resource-id", "")
            if resource_id:
                # Full match or partial match (e.g. "digit_1" matches "...id/digit_1")
                if resource_id == text or resource_id.endswith(f"/{text}"):
                    bounds = el.get("bounds")
                    if bounds:
                        x = (bounds[0] + bounds[2]) // 2
                        y = (bounds[1] + bounds[3]) // 2
                        return (x, y)

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
        """Parse uiautomator XML dump.

        Args:
            xml_path: Path to XML file

        Returns:
            List of element dicts
        """
        elements = []

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

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

        except ET.ParseError:
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
