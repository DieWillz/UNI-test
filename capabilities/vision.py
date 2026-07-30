"""Vision Capability - Screenshot analysis via LM Studio VLM"""

import asyncio
import base64
from typing import Any
from PIL import Image
from io import BytesIO

from ..brain import Brain
from ..config import Config
from ..capabilities.registry import Capability, ToolSchema


class VisionCapability(Capability):
    def __init__(self, brain: Brain, config: Config):
        super().__init__("vision")
        self.brain = brain
        self.vision_model = config.capabilities.vision.model
        self.enabled = config.capabilities.vision.enabled

        self.register_tool(ToolSchema(
            name="analyze_screen",
            description="Analyze screenshot with vision model",
            parameters={
                "type": "object",
                "properties": {
                    "image_base64": {"type": "string", "description": "Base64 encoded image"},
                    "prompt": {"type": "string", "description": "Analysis prompt"},
                },
                "required": ["image_base64", "prompt"],
            },
        ))
        self.register_tool(ToolSchema(
            name="find_element",
            description="Find UI element by description",
            parameters={
                "type": "object",
                "properties": {
                    "image_base64": {"type": "string", "description": "Base64 encoded screenshot"},
                    "description": {"type": "string", "description": "Element description (e.g., 'login button', 'search field')"},
                },
                "required": ["image_base64", "description"],
            },
        ))
        self.register_tool(ToolSchema(
            name="read_text",
            description="Extract text from screenshot (OCR via VLM)",
            parameters={
                "type": "object",
                "properties": {
                    "image_base64": {"type": "string", "description": "Base64 encoded image"},
                    "region": {"type": "string", "description": "Optional region description"},
                },
                "required": ["image_base64"],
            },
        ))

    async def execute(self, tool_name: str, args: dict) -> Any:
        if not self.enabled:
            return {"success": False, "error": "Vision capability disabled"}

        method = getattr(self, f"_tool_{tool_name}", None)
        if not method:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await method(args)

    async def _tool_analyze_screen(self, args: dict) -> dict:
        image_base64 = args["image_base64"]
        prompt = args["prompt"]

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ]

        try:
            response = await self.brain.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                max_tokens=500,
                temperature=0.1,
            )
            text = response.choices[0].message.content or ""
            return {"success": True, "analysis": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _tool_find_element(self, args: dict) -> dict:
        image_base64 = args["image_base64"]
        description = args["description"]

        prompt = f"""Find the {description} in this screenshot. 
Return ONLY a JSON object with: {{"x": int, "y": int, "width": int, "height": int, "confidence": float, "found": bool}}
Coordinates are relative to the image (0,0 = top-left)."""

        result = await self._tool_analyze_screen({"image_base64": image_base64, "prompt": prompt})
        
        if result["success"]:
            try:
                import json
                parsed = json.loads(result["analysis"])
                return {"success": True, **parsed}
            except:
                return {"success": False, "error": "Failed to parse element location", "raw": result["analysis"]}
        return result

    async def _tool_read_text(self, args: dict) -> dict:
        image_base64 = args["image_base64"]
        region = args.get("region", "")

        prompt = f"Extract all readable text from this screenshot{f' in the {region} region' if region else ''}. Return only the text content."

        result = await self._tool_analyze_screen({"image_base64": image_base64, "prompt": prompt})
        
        if result["success"]:
            return {"success": True, "text": result["analysis"]}
        return result