"""Background polling of UI hierarchy via uiautomator dump."""

import logging
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from mutcli.core.ui_element_parser import UIElement, UIElementParser

logger = logging.getLogger("mut.ui_hierarchy")


class UIHierarchyMonitor:
    """Background polling of UI hierarchy via uiautomator dump.

    Continuously polls uiautomator dump in a background thread during recording.
    Each dump is timestamped relative to the recording start time for synchronization
    with video and touch events.

    Usage:
        monitor = UIHierarchyMonitor("device-id")
        monitor.start(reference_time=video_start_time)
        # ... recording in progress ...
        monitor.stop()
        dumps = monitor.get_dumps()
    """

    def __init__(self, device_id: str, app_package: str):
        """Initialize monitor for a specific device.

        Args:
            device_id: ADB device identifier
            app_package: App package to filter dumps. Only dumps when this
                        app has focus are saved.
        """
        self._device_id = device_id
        self._app_package = app_package
        self._dumps: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._reference_time: float | None = None
        self._parser = UIElementParser()
        self._dump_count = 0
        self._skipped_count = 0

    @property
    def is_running(self) -> bool:
        """Check if monitoring is active."""
        return self._running

    def start(self, reference_time: float | None = None) -> bool:
        """Start background polling.

        Args:
            reference_time: Reference timestamp (time.time()) for synchronization.
                           Should be the same as video recording start time.
                           If None, uses current time.

        Returns:
            True if started successfully, False on error.
        """
        if self._running:
            return True

        self._reference_time = reference_time if reference_time is not None else time.time()
        self._running = True
        self._dumps = []
        self._dump_count = 0

        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
        )
        self._thread.start()

        logger.info(f"UI hierarchy monitoring started for {self._device_id}")
        return True

    def stop(self) -> None:
        """Stop polling."""
        self._running = False

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        msg = f"UI hierarchy monitoring stopped ({self._dump_count} dumps captured"
        if self._skipped_count > 0:
            msg += f", {self._skipped_count} skipped due to wrong focus"
        msg += ")"
        logger.info(msg)

    def get_dumps(self) -> list[dict[str, Any]]:
        """Get all captured dumps (thread-safe copy).

        Returns:
            List of dump dicts with timestamp and elements.
        """
        with self._lock:
            return list(self._dumps)

    def get_dump_at(self, timestamp: float) -> dict[str, Any] | None:
        """Get closest preceding dump for a timestamp.

        Args:
            timestamp: Event timestamp (relative to reference_time)

        Returns:
            Dump dict with timestamp and elements, or None if no preceding dump.
        """
        with self._lock:
            preceding = [d for d in self._dumps if d["timestamp"] <= timestamp]

        if not preceding:
            return None

        return preceding[-1]  # Last one before timestamp

    def find_element_at(
        self,
        timestamp: float,
        x: int,
        y: int,
    ) -> dict[str, Any] | None:
        """Find element at coordinates from closest preceding UI dump.

        Args:
            timestamp: Event timestamp (relative to reference_time)
            x: X coordinate
            y: Y coordinate

        Returns:
            Element context dict or None if not found.
        """
        dump = self.get_dump_at(timestamp)
        if not dump:
            return None

        elements = dump.get("elements", [])
        if not elements:
            return None

        # Find smallest element containing (x, y)
        matching = []
        for elem_dict in elements:
            bounds = elem_dict.get("bounds")
            if bounds and len(bounds) == 4:
                left, top, right, bottom = bounds
                if left <= x <= right and top <= y <= bottom:
                    area = (right - left) * (bottom - top)
                    matching.append((area, elem_dict))

        if not matching:
            return None

        # Return smallest (most specific) element
        matching.sort(key=lambda x: x[0])
        return matching[0][1]

    def _get_focused_window(self) -> str | None:
        """Get the currently focused window's package name.

        Returns:
            Package name of focused window, or None if unable to determine.
        """
        try:
            result = subprocess.run(
                ["adb", "-s", self._device_id, "shell", "dumpsys", "window", "windows"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            # Look for mCurrentFocus line
            for line in result.stdout.split("\n"):
                if "mCurrentFocus" in line:
                    # Extract package from: mCurrentFocus=Window{... u0 package/activity}
                    # or: mCurrentFocus=Window{... u0 WindowName}
                    parts = line.split()
                    for part in parts:
                        if "/" in part and "}" not in part:
                            # Format: package/activity
                            return part.split("/")[0]
                        elif part.endswith("}"):
                            # Try to get package from window name
                            window_name = part.rstrip("}")
                            if "." in window_name:
                                return window_name
            return None

        except Exception as e:
            logger.debug(f"Failed to get focused window: {e}")
            return None

    def _poll_loop(self) -> None:
        """Background thread: continuously poll uiautomator dump."""
        if self._reference_time is None:
            logger.error("Reference time not set, cannot poll")
            return

        while self._running:
            try:
                # Check if target app has focus before dumping
                focused = self._get_focused_window()
                if focused and self._app_package not in focused:
                    logger.debug(
                        f"Skipping dump: {focused} has focus, "
                        f"not {self._app_package}"
                    )
                    self._skipped_count += 1
                    time.sleep(0.5)  # Brief sleep before retry
                    continue

                timestamp = time.time() - self._reference_time
                elements = self._dump_hierarchy()

                if elements is not None:
                    dump_entry = {
                        "timestamp": round(timestamp, 3),
                        "elements": elements,
                    }

                    with self._lock:
                        self._dumps.append(dump_entry)
                        self._dump_count += 1

                    logger.debug(
                        f"UI dump #{self._dump_count} at t={timestamp:.3f}s: "
                        f"{len(elements)} elements"
                    )

            except Exception as e:
                # Don't crash on dump failures - just log and continue
                logger.debug(f"UI dump failed: {e}")

            # No sleep - dump as fast as possible
            # Each dump takes ~500ms-1s naturally

    def _dump_hierarchy(self) -> list[dict[str, Any]] | None:
        """Execute uiautomator dump and parse XML.

        Returns:
            List of element dicts, or None on failure.
        """
        remote_path = "/sdcard/ui_dump.xml"

        # Create temp file for local copy
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            local_path = Path(tmp.name)

        try:
            # Dump UI hierarchy on device
            # Timeout set to 10s as uiautomator dump can take 2-5s depending on UI complexity
            result = subprocess.run(
                ["adb", "-s", self._device_id, "shell", "uiautomator", "dump", remote_path],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.debug(f"uiautomator dump failed: {result.stderr}")
                return None

            # Pull XML to local
            result = subprocess.run(
                ["adb", "-s", self._device_id, "pull", remote_path, str(local_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.debug(f"adb pull failed: {result.stderr}")
                return None

            # Parse XML
            ui_elements = self._parser.parse_xml_file(local_path)

            # Convert UIElement objects to dicts
            return [self._element_to_dict(elem) for elem in ui_elements]

        except subprocess.TimeoutExpired:
            logger.debug("UI dump timed out")
            return None
        except Exception as e:
            logger.debug(f"UI dump error: {e}")
            return None
        finally:
            # Cleanup temp file
            try:
                local_path.unlink()
            except Exception:
                pass

    def _element_to_dict(self, elem: UIElement) -> dict[str, Any]:
        """Convert UIElement to serializable dict.

        Args:
            elem: UIElement object

        Returns:
            Dict representation
        """
        return {
            "class": elem.class_name.split(".")[-1],  # Short class name
            "text": elem.text,
            "resource_id": elem.resource_id,
            "content_desc": elem.content_desc,
            "bounds": list(elem.bounds),  # [left, top, right, bottom]
            "clickable": elem.clickable,
            "enabled": elem.enabled,
        }
