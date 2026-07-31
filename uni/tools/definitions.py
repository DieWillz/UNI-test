"""Tool definitions - all 18 tools mapped to capabilities"""

from typing import Any
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameter] = []

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        properties = {}
        required = []
        for param in self.parameters:
            prop: dict = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# Tool Registry - maps tool name to capability
TOOL_TO_CAPABILITY = {
    # Browser tools
    "navigate": "browser",
    "click_selector": "browser",
    "type_selector": "browser",
    "extract_text": "browser",
    "screenshot": "browser",
    "wait_for_selector": "browser",
    "get_page_info": "browser",
    # Computer tools
    "click": "computer",
    "type": "computer",
    "press": "computer",
    "move": "computer",
    "scroll": "computer",
    "screenshot_region": "computer",
    "focus_window": "computer",
    "get_window_list": "computer",
    # Speech tools
    "listen": "speech",
    "speak": "speech",
    # Vision tools
    "analyze_screen": "vision",
    "find_element": "vision",
    "read_text": "vision",
    # Memory tools
    "remember": "memory",
    "recall": "memory",
    "forget": "memory",
    "list_memory": "memory",
    "get_context": "memory",
}


# All tool definitions
TOOL_DEFINITIONS = [
    # Browser
    ToolSchema(
        name="navigate",
        description="Navigate to URL in browser",
        parameters=[
            ToolParameter(name="url", type="string", description="URL to navigate to", required=True),
            ToolParameter(name="wait_until", type="string", description="Wait condition", default="domcontentloaded", enum=["load", "domcontentloaded", "networkidle"]),
        ],
    ),
    ToolSchema(
        name="click_selector",
        description="Click element by CSS selector",
        parameters=[
            ToolParameter(name="selector", type="string", description="CSS selector", required=True),
            ToolParameter(name="button", type="string", description="Mouse button", default="left", enum=["left", "right", "middle"]),
            ToolParameter(name="click_count", type="integer", description="Number of clicks", default=1),
        ],
    ),
    ToolSchema(
        name="type_selector",
        description="Type text into element",
        parameters=[
            ToolParameter(name="selector", type="string", description="CSS selector", required=True),
            ToolParameter(name="text", type="string", description="Text to type", required=True),
            ToolParameter(name="delay", type="integer", description="Delay between keystrokes (ms)", default=50),
            ToolParameter(name="clear_first", type="boolean", description="Clear field first", default=True),
        ],
    ),
    ToolSchema(
        name="extract_text",
        description="Extract text from element",
        parameters=[
            ToolParameter(name="selector", type="string", description="CSS selector", required=True),
        ],
    ),
    ToolSchema(
        name="screenshot",
        description="Take page screenshot",
        parameters=[
            ToolParameter(name="full_page", type="boolean", description="Full page screenshot", default=False),
            ToolParameter(name="save_path", type="string", description="Optional save path"),
        ],
    ),
    ToolSchema(
        name="wait_for_selector",
        description="Wait for element to appear",
        parameters=[
            ToolParameter(name="selector", type="string", description="CSS selector", required=True),
            ToolParameter(name="state", type="string", description="Wait state", default="visible", enum=["attached", "detached", "visible", "hidden"]),
            ToolParameter(name="timeout", type="integer", description="Timeout (ms)", default=30000),
        ],
    ),
    ToolSchema(
        name="get_page_info",
        description="Get current page URL and title",
        parameters=[],
    ),
    # Computer
    ToolSchema(
        name="click",
        description="Click at screen coordinates",
        parameters=[
            ToolParameter(name="x", type="integer", description="X coordinate", required=True),
            ToolParameter(name="y", type="integer", description="Y coordinate", required=True),
            ToolParameter(name="button", type="string", description="Mouse button", default="left", enum=["left", "right", "middle"]),
            ToolParameter(name="clicks", type="integer", description="Number of clicks", default=1),
        ],
    ),
    ToolSchema(
        name="type",
        description="Type text at current cursor",
        parameters=[
            ToolParameter(name="text", type="string", description="Text to type", required=True),
            ToolParameter(name="interval", type="number", description="Delay between keystrokes", default=0.05),
        ],
    ),
    ToolSchema(
        name="press",
        description="Press key or key combination",
        parameters=[
            ToolParameter(name="key", type="string", description="Key name (e.g., 'enter', 'ctrl+c')", required=True),
        ],
    ),
    ToolSchema(
        name="move",
        description="Move mouse to coordinates",
        parameters=[
            ToolParameter(name="x", type="integer", description="X coordinate", required=True),
            ToolParameter(name="y", type="integer", description="Y coordinate", required=True),
            ToolParameter(name="duration", type="number", description="Move duration", default=0.2),
        ],
    ),
    ToolSchema(
        name="scroll",
        description="Scroll mouse wheel",
        parameters=[
            ToolParameter(name="clicks", type="integer", description="Scroll clicks (positive=up)", required=True),
            ToolParameter(name="x", type="integer", description="X coordinate"),
            ToolParameter(name="y", type="integer", description="Y coordinate"),
        ],
    ),
    ToolSchema(
        name="screenshot_region",
        description="Capture screen region",
        parameters=[
            ToolParameter(name="x", type="integer", description="X coordinate", default=0),
            ToolParameter(name="y", type="integer", description="Y coordinate", default=0),
            ToolParameter(name="width", type="integer", description="Width"),
            ToolParameter(name="height", type="integer", description="Height"),
            ToolParameter(name="save_path", type="string", description="Optional save path"),
        ],
    ),
    ToolSchema(
        name="focus_window",
        description="Focus window by title",
        parameters=[
            ToolParameter(name="title", type="string", description="Window title substring", required=True),
        ],
    ),
    ToolSchema(
        name="get_window_list",
        description="List all visible windows",
        parameters=[],
    ),
    # Speech
    ToolSchema(
        name="listen",
        description="Record and transcribe audio",
        parameters=[
            ToolParameter(name="duration", type="number", description="Recording duration (seconds)", default=5),
            ToolParameter(name="language", type="string", description="Language code", default="ru"),
        ],
    ),
    ToolSchema(
        name="speak",
        description="Convert text to speech and play",
        parameters=[
            ToolParameter(name="text", type="string", description="Text to speak", required=True),
            ToolParameter(name="voice", type="string", description="Voice override"),
        ],
    ),
    # Vision
    ToolSchema(
        name="analyze_screen",
        description="Analyze screenshot with vision model",
        parameters=[
            ToolParameter(name="image_base64", type="string", description="Base64 encoded image", required=True),
            ToolParameter(name="prompt", type="string", description="Analysis prompt", required=True),
        ],
    ),
    ToolSchema(
        name="find_element",
        description="Find UI element by description",
        parameters=[
            ToolParameter(name="image_base64", type="string", description="Base64 encoded screenshot", required=True),
            ToolParameter(name="description", type="string", description="Element description", required=True),
        ],
    ),
    ToolSchema(
        name="read_text",
        description="Extract text from screenshot (OCR)",
        parameters=[
            ToolParameter(name="image_base64", type="string", description="Base64 encoded image", required=True),
            ToolParameter(name="region", type="string", description="Optional region description"),
        ],
    ),
    # Memory
    ToolSchema(
        name="remember",
        description="Store key-value in working memory",
        parameters=[
            ToolParameter(name="key", type="string", description="Key", required=True),
            ToolParameter(name="value", type="string", description="Value", required=True),
        ],
    ),
    ToolSchema(
        name="recall",
        description="Retrieve value from working memory",
        parameters=[
            ToolParameter(name="key", type="string", description="Key", required=True),
        ],
    ),
    ToolSchema(
        name="forget",
        description="Remove key from working memory",
        parameters=[
            ToolParameter(name="key", type="string", description="Key", required=True),
        ],
    ),
    ToolSchema(
        name="list_memory",
        description="List all memory keys",
        parameters=[],
    ),
    ToolSchema(
        name="get_context",
        description="Get formatted memory context for prompt",
        parameters=[
            ToolParameter(name="max_items", type="integer", description="Max items", default=20),
        ],
    ),
]


def get_tool_schemas() -> list[dict]:
    """Get all tool schemas in OpenAI format."""
    return [tool.to_openai_schema() for tool in TOOL_DEFINITIONS]


def get_tool_by_name(name: str) -> ToolSchema | None:
    """Get tool definition by name."""
    for tool in TOOL_DEFINITIONS:
        if tool.name == name:
            return tool
    return None


def get_capability_for_tool(tool_name: str) -> str | None:
    """Get capability name for a tool."""
    return TOOL_TO_CAPABILITY.get(tool_name)