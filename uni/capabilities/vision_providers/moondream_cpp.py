"""CPU-first VLM provider: Moondream через llama.cpp (P-02, 2026-08-17).

Торч-free зрение для упаковки. Запускается отдельным llama-server на порту
1236 (см. scripts/launcher.js — launchVLM). Это тот же OpenAI-compatible
API, что и у основного LLM, но с --mmproj для визуального понимания.

Использование:
  from uni.capabilities.vision_providers.moondream_cpp import MoondreamCppProvider
  provider = MoondreamCppProvider(base_url="http://127.0.0.1:1236/v1")
  result = await provider.describe(image_base64, prompt="Опиши сцену")

Альтернатива: SmolVLM-ONNX через onnxruntime (P-02-ALT). Реализация
отложена до следующей итерации — требует скачивания модели ~500MB.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class MoondreamCppProvider:
    """OpenAI-compatible VLM через llama.cpp с --mmproj.

    Преимущества перед Gradio-Moondream:
      - Торч-free (llama.cpp — чистый C++)
      - Работает на CPU без GPU
      - Использует существующую абстракцию OpenAI-compatible endpoints
      - Локально, без интернета

    Минусы:
      - Требует распаковки GGUF модели в downloads/
      - ~1.7GB RAM на CPU
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1236/v1",
        api_key: str = "uni-local",
        model: str = "moondream2",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def describe(self, image_base64: str, prompt: str) -> dict[str, Any]:
        if "," in image_base64 and image_base64.startswith("data:"):
            image_url = image_base64
        else:
            image_url = f"data:image/png;base64,{image_base64}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Опиши, что видишь на изображении."},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "max_tokens": 500,
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {"ok": True, "text": text.strip(), "provider": "moondream-cpp"}
        except urllib.error.URLError as e:
            return {"ok": False, "error": f"VLM недоступен: {e.reason}", "provider": "moondream-cpp"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "provider": "moondream-cpp"}

    def health_check(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=2) as r:
                data = json.loads(r.read().decode("utf-8"))
                models = [m.get("id") for m in (data.get("data") or [])]
                return {"ok": True, "models": models}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
