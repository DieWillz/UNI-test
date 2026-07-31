import json
from typing import Any, List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel
from uni.config import BrainConfig

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]

class BrainResponse(BaseModel):
    text: str
    tool_calls: List[ToolCall] = []

class Brain:
    def __init__(self, config: BrainConfig):
        self.config = config
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key="lm-studio",
            timeout=60.0,
        )
        self.model = config.model
        self.vision_model = config.vision_model or config.model

    async def chat(self, messages: List[dict], tools: Optional[List[dict]] = None,
                   temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> BrainResponse:
        temp = temperature or self.config.temperature
        max_tok = max_tokens or self.config.max_tokens
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or [],
                temperature=temp,
                max_tokens=max_tok,
            )
            msg = resp.choices[0].message
            text = msg.content or ""
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except:
                        args = {}
                    tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
            return BrainResponse(text=text, tool_calls=tool_calls)
        except Exception as e:
            return BrainResponse(text=f"❌ Brain error: {e}")

    async def vision(self, image_data: str, prompt: str, max_tokens: Optional[int] = None) -> str:
        max_tok = max_tokens or self.config.max_tokens
        if not image_data.startswith("data:image"):
            image_data = f"data:image/png;base64,{image_data}"
        try:
            resp = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_data}}, {"type": "text", "text": prompt}]}],
                max_tokens=max_tok,
                temperature=0.1,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"❌ Vision error: {e}"
