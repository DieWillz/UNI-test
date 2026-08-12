from __future__ import annotations

import json
from typing import Any, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from uni.config import BrainConfig


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class BrainResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error: str | None = None


class Brain:
    def __init__(self, config: BrainConfig, *, vision_model: str | None = None):
        self.config = config
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )
        self.vision_client = self.client
        if config.vision_base_url and config.vision_base_url != config.base_url:
            self.vision_client = AsyncOpenAI(
                base_url=config.vision_base_url,
                api_key=config.vision_api_key or config.api_key,
                timeout=config.timeout_seconds,
            )
        self.model = config.model
        self._model_is_automatic = config.model.strip().lower() in {"", "auto"}
        self._model_resolved = False
        # Vision has its own explicit selection. If it is omitted, it follows the
        # resolved text model instead of preserving the literal value "auto".
        self.vision_model = vision_model or config.vision_model

    async def _resolve_loaded_model(self) -> tuple[str, list[str], bool]:
        """Resolve the active LM Studio text model.

        LM Studio's OpenAI-compatible ``/v1/models`` endpoint exposes models
        that are currently loaded, unlike its native catalogue endpoint which
        also includes downloaded but unloaded models. An explicit configured
        model wins while it is loaded; otherwise UNI follows the first loaded
        model so changing models in LM Studio needs no config edit.
        """
        models = await self.client.models.list()
        names = [str(item.id).strip() for item in models.data if str(item.id).strip()]
        if not names:
            raise RuntimeError(
                "В LM Studio нет загруженной модели. Загрузите текстовую модель "
                "и оставьте Local Server включённым."
            )

        configured = self.config.model.strip()
        used_fallback = bool(configured and configured.lower() != "auto" and configured not in names)
        if configured and configured.lower() != "auto" and configured in names:
            selected = configured
        else:
            selected = names[0]

        self.model = selected
        self._model_resolved = True
        if self.vision_model is None:
            self.vision_model = selected
        return selected, names, used_fallback

    async def _ensure_model(self) -> None:
        if not self._model_resolved:
            await self._resolve_loaded_model()

    async def healthcheck(self) -> tuple[bool, str]:
        try:
            selected, names, used_fallback = await self._resolve_loaded_model()
            suffix = " (выбрана автоматически вместо значения из config)" if used_fallback else ""
            return True, f"{selected}{suffix}; загружено моделей: {len(names)}"
        except Exception as exc:
            return False, str(exc)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> BrainResponse:
        try:
            await self._ensure_model()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or [],
                temperature=self.config.temperature if temperature is None else temperature,
                max_tokens=max_tokens or self.config.max_tokens,
            )
            message = response.choices[0].message
            calls: list[ToolCall] = []
            for call in message.tool_calls or []:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                except (json.JSONDecodeError, ValueError):
                    arguments = {}
                calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
            return BrainResponse(text=message.content or "", tool_calls=calls)
        except Exception as exc:
            return BrainResponse(error=str(exc))

    async def simple_chat(self, prompt: str) -> str:
        response = await self.chat([{"role": "user", "content": prompt}], tools=None)
        if response.error:
            raise RuntimeError(response.error)
        return response.text

    async def vision(self, image_data: str, prompt: str, max_tokens: Optional[int] = None) -> str:
        if not image_data.startswith("data:image"):
            image_data = f"data:image/png;base64,{image_data}"
        try:
            if self.vision_model is None:
                await self._ensure_model()
            response = await self.vision_client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens or self.config.max_tokens,
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"VLM API недоступен: {exc}") from exc
