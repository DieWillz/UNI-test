"""Agent state machine"""

from enum import Enum


class AgentState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    PAUSED = "paused"
    ERROR = "error"


VALID_TRANSITIONS = {
    AgentState.IDLE: {AgentState.LISTENING, AgentState.THINKING, AgentState.PAUSED, AgentState.ERROR},
    AgentState.LISTENING: {AgentState.THINKING, AgentState.ERROR, AgentState.IDLE},
    AgentState.THINKING: {AgentState.EXECUTING, AgentState.SPEAKING, AgentState.IDLE, AgentState.ERROR},
    AgentState.EXECUTING: {AgentState.THINKING, AgentState.SPEAKING, AgentState.IDLE, AgentState.ERROR},
    AgentState.SPEAKING: {AgentState.IDLE, AgentState.LISTENING, AgentState.ERROR},
    AgentState.PAUSED: {AgentState.IDLE, AgentState.ERROR},
    AgentState.ERROR: {AgentState.IDLE, AgentState.LISTENING},
}


def can_transition(from_state: AgentState, to_state: AgentState) -> bool:
    return to_state in VALID_TRANSITIONS.get(from_state, set())