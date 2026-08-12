from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from uni.devcoord.models import ProviderConfig


class DevelopmentCoordinatorConfig(BaseModel):
    state_path: str = ".uni-dev/coordination/state.json"
    allow_paid_api: bool = False
    providers: list[ProviderConfig] = Field(default_factory=list)


def load_development_config(path: str | Path) -> DevelopmentCoordinatorConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return DevelopmentCoordinatorConfig.model_validate(data)
