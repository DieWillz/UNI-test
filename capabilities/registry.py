from typing import List, Optional
from .base import Capability

class CapabilityRegistry:
    def __init__(self):
        self._capabilities = {}

    def register(self, cap: Capability):
        self._capabilities[cap.name] = cap

    def get(self, name: str) -> Optional[Capability]:
        return self._capabilities.get(name)

    def list(self) -> List[Capability]:
        return list(self._capabilities.values())

    def get_names(self) -> List[str]:
        return list(self._capabilities.keys())

    def has(self, name: str) -> bool:
        return name in self._capabilities
