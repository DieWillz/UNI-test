from enum import Enum, auto

class AgentState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    EXECUTING = auto()
    VERIFYING = auto()
    PAUSED = auto()
    ERROR = auto()
