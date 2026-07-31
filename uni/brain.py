"""Brain client - LM Studio via OpenAI-compatible API"""

import json
from dataclasses import dataclass
from typing import Any
from openai import AsyncOpenAI

from .config import Config


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str


@dataclass
class BrainResponse:
    text: str | None
    tool_calls: list[ToolCall]
    raw: Any


class Brain:
    def __init__(self, config: Config):
        self.client = AsyncOpenAI(
            base_url=config.brain.base_url,
            api_key="lm-studio",
        )
        self.model = config.brain.model
        self.temperature = config.brain.temperature
        self.max_tokens = config.brain.max_tokens

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> BrainResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or [],
            tool_choice="auto" if tools else "none",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        choice = response.choices[0]
        text = choice.message.content
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if tc.function.arguments else {},
                    id=tc.id,
                ))

        return BrainResponse(text=text, tool_calls=tool_calls, raw=response)

    async def simple_chat(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content or ""