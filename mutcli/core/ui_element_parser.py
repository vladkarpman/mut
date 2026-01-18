"""Parse UI elements from uiautomator XML dumps."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UIElement:
    """Parsed UI element from uiautomator dump."""

    class_name: str
    text: str | None
    resource_id: str | None
    content_desc: str | None
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool
    enabled: bool
    index: int

    def contains_point(self, x: int, y: int) -> bool:
        """Check if point is within element bounds."""
        left, top, right, bottom = self.bounds
        return left <= x <= right and top <= y <= bottom

    def area(self) -> int:
        """Calculate element area."""
        left, top, right, bottom = self.bounds
        return (right - left) * (bottom - top)


class UIElementParser:
    """Parse uiautomator XML dumps to find UI elements."""

    def parse_xml_file(self, path: Path) -> list[UIElement]:
        """Parse XML file to list of UI elements.

        Args:
            path: Path to XML file

        Returns:
            List of UIElement objects
        """
        tree = ET.parse(path)
        return self._parse_tree(tree.getroot())

    def parse_xml_string(self, xml_string: str) -> list[UIElement]:
        """Parse XML string to list of UI elements.

        Args:
            xml_string: XML content as string

        Returns:
            List of UIElement objects
        """
        root = ET.fromstring(xml_string)
        return self._parse_tree(root)

    def _parse_tree(self, root: ET.Element) -> list[UIElement]:
        """Parse element tree recursively.

        Args:
            root: Root element

        Returns:
            Flat list of all elements
        """
        elements: list[UIElement] = []
        self._parse_node(root, elements)
        return elements

    def _parse_node(self, node: ET.Element, elements: list[UIElement]) -> None:
        """Parse single node and its children.

        Args:
            node: Current XML node
            elements: List to append elements to
        """
        # Parse bounds: [left,top][right,bottom]
        bounds_str = node.get("bounds", "[0,0][0,0]")
        bounds = self._parse_bounds(bounds_str)

        element = UIElement(
            class_name=node.get("class", ""),
            text=node.get("text") or None,
            resource_id=node.get("resource-id") or None,
            content_desc=node.get("content-desc") or None,
            bounds=bounds,
            clickable=node.get("clickable", "false") == "true",
            enabled=node.get("enabled", "true") == "true",
            index=int(node.get("index", 0)),
        )

        # Only add elements with valid bounds
        if bounds != (0, 0, 0, 0):
            elements.append(element)

        # Parse children
        for child in node:
            self._parse_node(child, elements)

    def _parse_bounds(self, bounds_str: str) -> tuple[int, int, int, int]:
        """Parse bounds string to tuple.

        Args:
            bounds_str: Format "[left,top][right,bottom]"

        Returns:
            Tuple of (left, top, right, bottom)
        """
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if match:
            left, top, right, bottom = match.groups()
            return (int(left), int(top), int(right), int(bottom))
        return (0, 0, 0, 0)

    def find_element_at(
        self,
        elements: list[UIElement],
        x: int,
        y: int,
    ) -> UIElement | None:
        """Find the smallest element containing the point.

        Args:
            elements: List of UI elements
            x: X coordinate
            y: Y coordinate

        Returns:
            Smallest element containing point, or None
        """
        matching = [e for e in elements if e.contains_point(x, y)]
        if not matching:
            return None

        # Return smallest element (most specific)
        return min(matching, key=lambda e: e.area())

    def get_element_context(self, element: UIElement) -> dict:
        """Build context dict for AI prompt enrichment.

        Args:
            element: UI element

        Returns:
            Dict with element properties for AI context
        """
        return {
            "class": element.class_name.split(".")[-1],  # Just class name
            "text": element.text,
            "resource_id": element.resource_id,
            "content_desc": element.content_desc,
            "clickable": element.clickable,
            "enabled": element.enabled,
            "bounds": {
                "left": element.bounds[0],
                "top": element.bounds[1],
                "right": element.bounds[2],
                "bottom": element.bounds[3],
            },
        }
