"""AI vision analysis using Gemini 2.5 Flash."""

import json
import logging
import os
from typing import Any, TypedDict

from google import genai
from google.genai import types

logger = logging.getLogger("mut.ai")


# TypedDict definitions for gesture analysis results


class TapAnalysisResult(TypedDict):
    """Result from analyze_tap() method."""

    element_text: str | None
    element_type: str  # button|text_field|link|icon|checkbox|other
    action_description: str  # Human-readable: "User taps on 5"
    before_description: str
    after_description: str
    suggested_verification: str | None


class SwipeAnalysisResult(TypedDict):
    """Result from analyze_swipe() method."""

    direction: str  # up|down|left|right
    content_changed: str
    action_description: str  # Human-readable: "User swipes up to scroll"
    before_description: str
    after_description: str
    suggested_verification: str | None


class LongPressAnalysisResult(TypedDict):
    """Result from analyze_long_press() method."""

    element_text: str | None
    element_type: str  # list_item|text|image|icon|other
    result_type: str  # context_menu|selection|drag_start|other
    action_description: str  # Human-readable: "User long-presses on item"
    before_description: str
    after_description: str
    suggested_verification: str | None


class TypeAnalysisResult(TypedDict):
    """Result from analyze_type() method."""

    element_text: str | None  # e.g., "Search field", "Email input"
    element_type: str  # text_field|search_box|password_field|textarea|other
    action_description: str  # Human-readable: "User types in search field"
    before_description: str
    after_description: str
    suggested_verification: str | None


class AIAnalyzer:
    """AI vision analysis using Gemini 2.5 Flash.

    Handles verify_screen, if_screen, and step analysis for test execution
    and recording workflows.

    Uses hybrid verification strategy:
    - verify_screen: Deferred (captures screenshot, continues, analyzes post-test)
    - if_screen: Real-time (immediate AI call for branching decisions)
    """

    DEFAULT_MODEL = "gemini-3-flash-preview"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Initialize analyzer.

        Args:
            api_key: Google API key. If not provided, reads from GOOGLE_API_KEY env var.
            model: Model to use. Defaults to gemini-3-flash-preview.
        """
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._model = model or self.DEFAULT_MODEL
        self._client: genai.Client | None = None

        if self._api_key:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize Gemini client."""
        try:
            self._client = genai.Client(api_key=self._api_key)
            logger.info(f"AIAnalyzer initialized with model: {self._model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if AI is available (API key configured)."""
        return self._api_key is not None

    def verify_screen(self, screenshot: bytes, description: str) -> dict[str, Any]:
        """Verify screen matches description.

        Args:
            screenshot: PNG image bytes
            description: Expected screen description

        Returns:
            Dict with pass (bool), reason (str), and optional skipped (bool)
        """
        if not self.is_available or self._client is None:
            return {
                "pass": True,
                "reason": "AI verification skipped (no API key)",
                "skipped": True,
            }

        prompt = f'''Analyze this mobile app screenshot.

Question: Does the screen show "{description}"?

Respond with JSON only (no markdown, no code blocks):
{{"pass": true/false, "reason": "brief explanation"}}'''

        try:
            # Create image part from bytes
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            # Parse response
            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"verify_screen failed: {e}")
            return {
                "pass": False,
                "reason": f"AI verification error: {str(e)}",
                "error": True,
            }

    def if_screen(self, screenshot: bytes, condition: str) -> bool:
        """Check if screen matches condition for branching.

        This is a real-time check used for conditional execution.
        When AI is unavailable, returns False (safe default - don't execute branch).

        Args:
            screenshot: PNG image bytes
            condition: Condition to check

        Returns:
            True if condition is met, False otherwise
        """
        if not self.is_available or self._client is None:
            logger.warning(f"if_screen skipped (no API key): {condition}")
            return False

        result = self.verify_screen(screenshot, condition)
        return bool(result.get("pass", False))

    def analyze_step(self, before: bytes, after: bytes) -> dict[str, Any]:
        """Analyze before/after frames to describe a step.

        Used in recording workflow to generate step descriptions and
        suggested verifications.

        Args:
            before: PNG image bytes before action
            after: PNG image bytes after action

        Returns:
            Dict with before, action, after descriptions and suggested_verification
        """
        if not self.is_available or self._client is None:
            return {
                "before": "Unknown (AI unavailable)",
                "action": "Unknown",
                "after": "Unknown",
                "suggested_verification": None,
                "skipped": True,
            }

        prompt = '''Compare these two mobile app screenshots (before and after an action).

The first image is BEFORE the action, the second is AFTER.

Describe:
1. What was the UI state before?
2. What action was likely performed?
3. What changed after?
4. What verification would confirm this step succeeded?

Respond with JSON only (no markdown, no code blocks):
{
  "before": "description of before state",
  "action": "description of action performed",
  "after": "description of after state",
  "suggested_verification": "verification description or null if not applicable"
}'''

        try:
            # Create image parts
            before_part = types.Part.from_bytes(
                data=before,
                mime_type="image/png",
            )
            after_part = types.Part.from_bytes(
                data=after,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[before_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"analyze_step failed: {e}")
            return {
                "before": "Analysis failed",
                "action": "Unknown",
                "after": "Analysis failed",
                "suggested_verification": None,
                "error": str(e),
            }

    def find_element(
        self, screenshot: bytes, description: str, screen_width: int, screen_height: int
    ) -> tuple[int, int] | None:
        """Find element on screen by description.

        Uses AI vision to locate an element matching the description.

        Args:
            screenshot: PNG image bytes
            description: Element description (e.g., "login button", "email field")
            screen_width: Screen width in pixels (for coordinate calculation)
            screen_height: Screen height in pixels (for coordinate calculation)

        Returns:
            (x, y) pixel coordinates of element center, or None if not found
        """
        if not self.is_available or self._client is None:
            logger.warning(f"find_element skipped (no API key): {description}")
            return None

        prompt = f'''Find the UI element described as "{description}" in this mobile app screenshot.

The screen dimensions are {screen_width}x{screen_height} pixels.

If you find the element, respond with its CENTER coordinates as percentages of screen dimensions.
If you cannot find the element, respond with null coordinates.

Respond with JSON only (no markdown, no code blocks):
{{"found": true/false, "x_percent": 0-100 or null, "y_percent": 0-100 or null,
"reason": "brief explanation"}}'''

        try:
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            if result.get("found") and result.get("x_percent") and result.get("y_percent"):
                x = int(float(result["x_percent"]) * screen_width / 100)
                y = int(float(result["y_percent"]) * screen_height / 100)
                logger.info(f"AI found '{description}' at ({x}, {y})")
                return (x, y)

            logger.info(f"AI could not find '{description}': {result.get('reason', 'unknown')}")
            return None

        except Exception as e:
            logger.error(f"find_element failed: {e}")
            return None

    def validate_element_at(
        self, screenshot: bytes, description: str, x_percent: float, y_percent: float
    ) -> dict[str, Any]:
        """Validate that element at coordinates matches description.

        Used when 'at:' coordinates are provided with text description.

        Args:
            screenshot: PNG image bytes
            description: Expected element description
            x_percent: X coordinate as percentage (0-100)
            y_percent: Y coordinate as percentage (0-100)

        Returns:
            Dict with valid (bool), reason (str)
        """
        if not self.is_available or self._client is None:
            return {"valid": True, "reason": "Validation skipped (no API key)", "skipped": True}

        prompt = f'''Look at the UI element at approximately ({x_percent:.0f}%, {y_percent:.0f}%)
of the screen in this mobile app screenshot.

The coordinates are percentages from the top-left corner.

Question: Is there a "{description}" at or near those coordinates?

Respond with JSON only (no markdown, no code blocks):
{{"valid": true/false, "reason": "brief explanation of what is actually at those coordinates"}}'''

        try:
            image_part = types.Part.from_bytes(
                data=screenshot,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            return self._parse_json_response(response_text)

        except Exception as e:
            logger.error(f"validate_element_at failed: {e}")
            return {"valid": False, "reason": f"Validation error: {str(e)}", "error": True}

    def analyze_image(self, image_data: bytes, prompt: str) -> str | None:
        """Analyze image with custom prompt.

        Args:
            image_data: PNG image bytes
            prompt: Custom analysis prompt

        Returns:
            AI response text, or None if unavailable
        """
        if not self.is_available or self._client is None:
            return None

        try:
            image_part = types.Part.from_bytes(
                data=image_data,
                mime_type="image/png",
            )

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],  # type: ignore[arg-type]
            )
            return response.text
        except Exception as e:
            logger.error(f"analyze_image failed: {e}")
            return None

    # -------------------------------------------------------------------------
    # Async gesture-specific analysis methods
    # -------------------------------------------------------------------------

    async def analyze_tap(
        self,
        before: bytes,
        touch: bytes,
        after: bytes,
        x: int,
        y: int,
        adb_context: dict[str, Any] | None = None,
    ) -> TapAnalysisResult:
        """Analyze a TAP gesture using 3 frames.

        Args:
            before: PNG image bytes - stable state before tap
            touch: PNG image bytes - moment of tap (shows target element)
            after: PNG image bytes - result after UI settled
            x: Tap X coordinate in pixels
            y: Tap Y coordinate in pixels
            adb_context: Optional device context from ADB (keyboard_visible, activity,
                        windows, element info)

        Returns:
            TapAnalysisResult with element info and descriptions
        """
        if not self.is_available or self._client is None:
            return TapAnalysisResult(
                element_text=None,
                element_type="other",
                action_description="User taps on element",
                before_description="Unknown (AI unavailable)",
                after_description="Unknown (AI unavailable)",
                suggested_verification=None,
            )

        # Build enhanced prompt with ADB context
        context_section = self._build_adb_context_section(adb_context)

        prompt = f"""Analyze this TAP interaction on a mobile app.

{context_section}Screenshots:
1. BEFORE - stable state before tap
2. TOUCH - moment of tap (shows target element)
3. AFTER - result after UI settled

Tap coordinates: ({x}, {y})

Respond with JSON only (no markdown, no code blocks):
{{
  "element_text": "button/field text or null",
  "element_type": "button|text_field|link|icon|checkbox|other",
  "action_description": "User taps on [element name/text]",
  "before_description": "Brief UI state before tap.",
  "after_description": "Brief UI state after tap.",
  "suggested_verification": "Expected visible state or null"
}}

FORMAT REQUIREMENTS (follow exactly):

element_text:
- IMPORTANT: If UI HIERARCHY DATA is provided above, use the SUGGESTED element_text value
- Priority: content-desc > text > resource-id (last part only)
- Only use null if no UI hierarchy data AND element is unclear from screenshots

action_description:
- Format: "User taps on [element]"
- Use element_text value for [element]
- Examples: "User taps on Submit", "User taps on menu icon", "User taps on Login"

before_description and after_description:
- Start with capital letter, end with period
- Be concise (5-15 words)
- Describe the visible UI state objectively
- Examples:
  - "Home screen is displayed."
  - "Login form with email and password fields."
  - "List shows 5 items."

suggested_verification:
- Describe expected visible state after this action, or null if not meaningful
- Examples: "Welcome message is visible.", "Item is added to cart.", null"""

        try:
            before_part = types.Part.from_bytes(data=before, mime_type="image/png")
            touch_part = types.Part.from_bytes(data=touch, mime_type="image/png")
            after_part = types.Part.from_bytes(data=after, mime_type="image/png")

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[before_part, touch_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            return TapAnalysisResult(
                element_text=result.get("element_text"),
                element_type=result.get("element_type", "other"),
                action_description=result.get("action_description", "User taps on element"),
                before_description=result.get("before_description", ""),
                after_description=result.get("after_description", ""),
                suggested_verification=result.get("suggested_verification"),
            )

        except Exception as e:
            logger.error(f"analyze_tap failed: {e}")
            return TapAnalysisResult(
                element_text=None,
                element_type="other",
                action_description="User taps on element",
                before_description=f"Analysis failed: {e}",
                after_description=f"Analysis failed: {e}",
                suggested_verification=None,
            )

    async def analyze_swipe(
        self,
        before: bytes,
        swipe_start: bytes,
        swipe_end: bytes,
        after: bytes,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        adb_context: dict[str, Any] | None = None,
    ) -> SwipeAnalysisResult:
        """Analyze a SWIPE gesture using 4 frames.

        Args:
            before: PNG image bytes - stable state before swipe
            swipe_start: PNG image bytes - finger down position
            swipe_end: PNG image bytes - finger up position
            after: PNG image bytes - result after UI settled
            start_x: Swipe start X coordinate in pixels
            start_y: Swipe start Y coordinate in pixels
            end_x: Swipe end X coordinate in pixels
            end_y: Swipe end Y coordinate in pixels
            adb_context: Optional device context from ADB (keyboard_visible, activity,
                        windows, element info)

        Returns:
            SwipeAnalysisResult with direction and content change info
        """
        if not self.is_available or self._client is None:
            return SwipeAnalysisResult(
                direction="unknown",
                content_changed="Unknown (AI unavailable)",
                action_description="User swipes",
                before_description="Unknown (AI unavailable)",
                after_description="Unknown (AI unavailable)",
                suggested_verification=None,
            )

        # Build enhanced prompt with ADB context
        context_section = self._build_adb_context_section(adb_context)

        prompt = f"""Analyze this SWIPE gesture on a mobile app.

{context_section}Screenshots:
1. BEFORE - stable state before swipe
2. SWIPE_START - finger down position
3. SWIPE_END - finger up position
4. AFTER - result after UI settled

Start: ({start_x}, {start_y}) -> End: ({end_x}, {end_y})

Respond with JSON only (no markdown, no code blocks):
{{
  "direction": "up|down|left|right",
  "content_changed": "what scrolled into/out of view",
  "action_description": "User swipes [direction] [context]",
  "before_description": "Brief UI state before swipe.",
  "after_description": "Brief UI state after swipe.",
  "suggested_verification": "Description of expected state." or null
}}

FORMAT REQUIREMENTS (follow exactly):

action_description:
- Format: "User swipes [direction]" or "User swipes [direction] to [purpose]"
- Examples: "User swipes up", "User swipes down to scroll list", "User swipes left to dismiss"

before_description and after_description:
- Start with capital letter, end with period
- Be concise (5-15 words)
- Focus on visible content that changed
- Examples:
  - "List shows items 1-5."
  - "List now shows items 6-10."
  - "Card is fully visible."

suggested_verification:
- Format: "[Element] is visible." or "[Content] appears." or null
- Examples: "Item 'Settings' is visible.", "Next page content appears.", null"""

        try:
            before_part = types.Part.from_bytes(data=before, mime_type="image/png")
            start_part = types.Part.from_bytes(data=swipe_start, mime_type="image/png")
            end_part = types.Part.from_bytes(data=swipe_end, mime_type="image/png")
            after_part = types.Part.from_bytes(data=after, mime_type="image/png")

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[before_part, start_part, end_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            direction = result.get("direction", "unknown")
            return SwipeAnalysisResult(
                direction=direction,
                content_changed=result.get("content_changed", ""),
                action_description=result.get("action_description", f"User swipes {direction}"),
                before_description=result.get("before_description", ""),
                after_description=result.get("after_description", ""),
                suggested_verification=result.get("suggested_verification"),
            )

        except Exception as e:
            logger.error(f"analyze_swipe failed: {e}")
            return SwipeAnalysisResult(
                direction="unknown",
                content_changed=f"Analysis failed: {e}",
                action_description="User swipes",
                before_description=f"Analysis failed: {e}",
                after_description=f"Analysis failed: {e}",
                suggested_verification=None,
            )

    async def analyze_long_press(
        self,
        before: bytes,
        press_start: bytes,
        press_held: bytes,
        after: bytes,
        x: int,
        y: int,
        duration_ms: int,
        adb_context: dict[str, Any] | None = None,
    ) -> LongPressAnalysisResult:
        """Analyze a LONG PRESS gesture using 4 frames.

        Args:
            before: PNG image bytes - stable state before press
            press_start: PNG image bytes - finger down on element
            press_held: PNG image bytes - during hold (may show visual feedback)
            after: PNG image bytes - result (context menu, selection, etc.)
            x: Press X coordinate in pixels
            y: Press Y coordinate in pixels
            duration_ms: Press duration in milliseconds
            adb_context: Optional device context from ADB (keyboard_visible, activity,
                        windows, element info)

        Returns:
            LongPressAnalysisResult with element and result type info
        """
        if not self.is_available or self._client is None:
            return LongPressAnalysisResult(
                element_text=None,
                element_type="other",
                result_type="other",
                action_description="User long-presses on element",
                before_description="Unknown (AI unavailable)",
                after_description="Unknown (AI unavailable)",
                suggested_verification=None,
            )

        # Build enhanced prompt with ADB context
        context_section = self._build_adb_context_section(adb_context)

        prompt = f"""Analyze this LONG PRESS gesture on a mobile app.

{context_section}Screenshots:
1. BEFORE - stable state before press
2. PRESS_START - finger down on element
3. PRESS_HELD - during hold (may show visual feedback)
4. AFTER - result (context menu, selection, etc.)

Press coordinates: ({x}, {y}), Duration: {duration_ms}ms

Respond with JSON only (no markdown, no code blocks):
{{
  "element_text": "pressed element text or null",
  "element_type": "list_item|text|image|icon|other",
  "result_type": "context_menu|selection|drag_start|other",
  "action_description": "User long-presses on [element]",
  "before_description": "Brief UI state before press.",
  "after_description": "Brief UI state after press.",
  "suggested_verification": "Description of expected state." or null
}}

FORMAT REQUIREMENTS (follow exactly):

element_text:
- IMPORTANT: If UI HIERARCHY DATA is provided above, use the SUGGESTED element_text value
- Priority: content-desc > text > resource-id (last part only)
- Only use null if no UI hierarchy data AND element is unclear from screenshots

action_description:
- Format: "User long-presses on [element]"
- Examples: "User long-presses on message", "User long-presses on item"

before_description and after_description:
- Start with capital letter, end with period
- Be concise (5-15 words)
- Examples:
  - "Message list is displayed."
  - "Context menu appears with options."
  - "Item is highlighted."

suggested_verification:
- Format: "[Menu/Selection] is visible." or null
- Examples: "Context menu is visible.", "Item is selected.", null"""

        try:
            before_part = types.Part.from_bytes(data=before, mime_type="image/png")
            start_part = types.Part.from_bytes(data=press_start, mime_type="image/png")
            held_part = types.Part.from_bytes(data=press_held, mime_type="image/png")
            after_part = types.Part.from_bytes(data=after, mime_type="image/png")

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[before_part, start_part, held_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            return LongPressAnalysisResult(
                element_text=result.get("element_text"),
                element_type=result.get("element_type", "other"),
                result_type=result.get("result_type", "other"),
                action_description=result.get("action_description", "User long-presses on element"),
                before_description=result.get("before_description", ""),
                after_description=result.get("after_description", ""),
                suggested_verification=result.get("suggested_verification"),
            )

        except Exception as e:
            logger.error(f"analyze_long_press failed: {e}")
            return LongPressAnalysisResult(
                element_text=None,
                element_type="other",
                result_type="other",
                action_description="User long-presses on element",
                before_description=f"Analysis failed: {e}",
                after_description=f"Analysis failed: {e}",
                suggested_verification=None,
            )

    async def analyze_type(
        self,
        before: bytes,
        after: bytes,
        adb_context: dict[str, Any] | None = None,
    ) -> TypeAnalysisResult:
        """Analyze a typing action using before and after frames.

        Args:
            before: PNG image bytes - screen state before typing (with keyboard)
            after: PNG image bytes - screen state after typing completed
            adb_context: Optional device context from ADB (keyboard_visible, activity,
                        windows, element info)

        Returns:
            TypeAnalysisResult with element info and descriptions
        """
        if not self.is_available or self._client is None:
            return TypeAnalysisResult(
                element_text=None,
                element_type="other",
                action_description="User types in text field",
                before_description="Unknown (AI unavailable)",
                after_description="Unknown (AI unavailable)",
                suggested_verification=None,
            )

        # Build enhanced prompt with ADB context
        context_section = self._build_adb_context_section(adb_context)

        prompt = f"""Analyze this TYPING interaction on a mobile app.

{context_section}Screenshots:
1. BEFORE - screen state before/during typing (may show keyboard)
2. AFTER - screen state after typing completed

Focus on:
1. What text field or input element was focused for typing?
2. What does the screen look like after typing?

Respond with JSON only (no markdown, no code blocks):
{{
  "element_text": "field name like 'Search field', 'Email input', 'Password field', or null",
  "element_type": "text_field|search_box|password_field|textarea|other",
  "action_description": "User types in [field name]",
  "before_description": "Brief UI state before typing.",
  "after_description": "Brief UI state after typing.",
  "suggested_verification": "Field contains '[text]'." or null
}}

FORMAT REQUIREMENTS (follow exactly):

element_text:
- If UI HIERARCHY DATA is provided above, use it to identify the field
- Priority: content-desc > text > resource-id (last part only)
- Examples: "Search field", "Email input", "Password field"

action_description:
- Format: "User types in [field name]"
- Examples: "User types in search field", "User types in email input"

before_description and after_description:
- Start with capital letter, end with period
- Be concise (5-15 words)
- Examples:
  - "Search field is empty with keyboard visible."
  - "Email field now contains 'user@example.com'."
  - "Text field shows entered value."

suggested_verification:
- Format: "Field contains '[text]'." or "[Field] shows '[value]'." or null
- Examples: "Search field contains 'query'.", "Email shows 'test@test.com'.", null"""

        try:
            before_part = types.Part.from_bytes(data=before, mime_type="image/png")
            after_part = types.Part.from_bytes(data=after, mime_type="image/png")

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[before_part, after_part, prompt],  # type: ignore[arg-type]
            )

            response_text = response.text or ""
            result = self._parse_json_response(response_text)

            return TypeAnalysisResult(
                element_text=result.get("element_text"),
                element_type=result.get("element_type", "other"),
                action_description=result.get("action_description", "User types in text field"),
                before_description=result.get("before_description", ""),
                after_description=result.get("after_description", ""),
                suggested_verification=result.get("suggested_verification"),
            )

        except Exception as e:
            logger.error(f"analyze_type failed: {e}")
            return TypeAnalysisResult(
                element_text=None,
                element_type="other",
                action_description="User types in text field",
                before_description=f"Analysis failed: {e}",
                after_description=f"Analysis failed: {e}",
                suggested_verification=None,
            )

    def _build_adb_context_section(self, adb_context: dict[str, Any] | None) -> str:
        """Build context section for AI prompts from ADB device context.

        Args:
            adb_context: Optional dict containing keyboard_visible, activity,
                        windows, and element info from ADB

        Returns:
            Formatted context section string (empty if no context provided)
        """
        if not adb_context:
            return ""

        context_section = "Device Context:\n"

        if "activity" in adb_context:
            context_section += f"- Current app activity: {adb_context['activity']}\n"

        if "keyboard_visible" in adb_context:
            context_section += f"- Keyboard visible: {adb_context['keyboard_visible']}\n"

        if "windows" in adb_context:
            windows = adb_context["windows"]
            if isinstance(windows, list):
                context_section += f"- Active dialogs: {', '.join(windows) or 'None'}\n"
            else:
                context_section += f"- Active dialogs: {windows}\n"

        if adb_context.get("element"):
            elem = adb_context["element"]
            # Extract short resource-id (e.g., "digit_1" from "...id/digit_1")
            resource_id = elem.get("resource_id") or ""
            short_rid = resource_id.split("/")[-1] if "/" in resource_id else resource_id

            # Determine the best element identifier (priority: content_desc > text > resource_id)
            content_desc = elem.get("content_desc")
            text = elem.get("text")
            suggested_text = content_desc or text or short_rid or None

            context_section += "\n=== UI HIERARCHY DATA (GROUND TRUTH) ===\n"
            context_section += "Use this data for element_text - it's from the actual UI tree.\n"
            context_section += f"- text: {text or 'None'}\n"
            context_section += f"- content-desc (accessibility label): {content_desc or 'None'}\n"
            context_section += f"- resource-id: {short_rid or 'None'}\n"
            context_section += f"- class: {elem.get('class', 'Unknown')}\n"
            if suggested_text:
                context_section += f"- SUGGESTED element_text: \"{suggested_text}\"\n"
            context_section += "=========================================\n"

        context_section += "\n"
        return context_section

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from model response, handling markdown code blocks."""
        text = text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            text = text.strip()

        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {
                "pass": False,
                "reason": f"Failed to parse AI response: {text[:100]}",
                "error": True,
            }
