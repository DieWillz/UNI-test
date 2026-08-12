from abc import ABC, abstractmethod
from typing import Any, Dict, List
from uni.contracts import ToolResult

class Capability(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> ToolResult:
        pass

    def get_tools(self) -> List[Dict[str, Any]]:
        return []
