"""Tests for UI element parser."""

from mutcli.core.ui_element_parser import UIElementParser


class TestUIElementParser:
    """Tests for UI element parsing from uiautomator dumps."""

    SAMPLE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
    <node index="0" class="android.widget.Button" text="Sign In"
          resource-id="com.example:id/btn_login" bounds="[100,500][300,600]"
          clickable="true" enabled="true" />
    <node index="1" class="android.widget.EditText" text=""
          resource-id="com.example:id/email_input" bounds="[100,300][980,400]"
          clickable="true" enabled="true" content-desc="Email address" />
  </node>
</hierarchy>'''

    def test_parse_xml(self):
        """Test parsing XML to elements."""
        parser = UIElementParser()
        elements = parser.parse_xml_string(self.SAMPLE_XML)
        assert len(elements) == 3  # FrameLayout, Button, EditText

    def test_find_element_at_coordinates(self):
        """Test finding element at tap coordinates."""
        parser = UIElementParser()
        elements = parser.parse_xml_string(self.SAMPLE_XML)

        # Find button at (200, 550)
        element = parser.find_element_at(elements, 200, 550)
        assert element is not None
        assert element.text == "Sign In"
        assert element.resource_id == "com.example:id/btn_login"

    def test_find_element_at_coordinates_not_found(self):
        """Test when no element at coordinates."""
        parser = UIElementParser()
        elements = parser.parse_xml_string(self.SAMPLE_XML)

        # Find at coordinates outside any element
        element = parser.find_element_at(elements, 1000, 1000)
        # Should return closest parent or None
        assert element is None or element.class_name == "android.widget.FrameLayout"

    def test_element_properties(self):
        """Test UIElement properties."""
        parser = UIElementParser()
        elements = parser.parse_xml_string(self.SAMPLE_XML)

        # Find email input
        email_input = next(
            (e for e in elements if "email_input" in (e.resource_id or "")),
            None
        )
        assert email_input is not None
        assert email_input.content_desc == "Email address"
        assert email_input.clickable is True
        assert email_input.enabled is True
