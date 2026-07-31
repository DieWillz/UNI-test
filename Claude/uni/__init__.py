"""
uni — локальная модульная AI-платформа UNI.

Публичный API пакета: Config/load_config (Build 1), WorkingMemory (Build 3).
Остальные экспорты (Brain, EventLoop, CapabilityRegistry, Agent) будут
добавлены соответствующими билдами без изменения существующих строк — только
дополнение импортов и __all__.
"""

__version__ = "0.1.0"

from uni.config import Config, load_config
from uni.working_memory import WorkingMemory

__all__ = ["Config", "load_config", "WorkingMemory", "__version__"]
