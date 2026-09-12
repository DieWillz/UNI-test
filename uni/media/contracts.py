"""Provider-neutral media generation contracts.

Telegram adapter only needs to send/receive files. Concrete generators
(ComfyUI, Flux, SDXL, external APIs) plug into this contract later.

This module is the INTEGRATION POINT — do NOT attach real generators here.
It describes what a provider must implement, not how to call one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence
from pathlib import Path


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    width: int = 1024
    height: int = 1024
    negative_prompt: str | None = None
    reference_image: Path | None = None
    metadata: dict[str, Any] = None


@dataclass(frozen=True)
class ImageGenerationResult:
    path: Path
    width: int
    height: int
    provider_name: str
    metadata: dict[str, Any] = None


@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    duration_seconds: float = 5.0
    reference_image: Path | None = None
    metadata: dict[str, Any] = None


@dataclass(frozen=True)
class VideoGenerationResult:
    path: Path
    duration_seconds: float
    provider_name: str
    metadata: dict[str, Any] = None


class MediaGenerator(ABC):
    """Protocol for image/video generation backends.

    Telegram transport never imports a concrete generator — it only receives a
    ready Path from UNI and delivers the file.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate an image from a text prompt, optionally editing a reference image."""
        ...

    @abstractmethod
    async def edit_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Edit an existing image according to the request."""
        ...

    @abstractmethod
    async def generate_video(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Generate a short video clip from a text prompt."""
        ...

    @abstractmethod
    async def status(self) -> dict[str, Any]:
        """Return provider health / capabilities metadata."""
        ...
