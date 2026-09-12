from __future__ import annotations

from uni.agent import Agent
from uni.config import Config
from uni.operator.runtime import OperatorRuntime


def test_agent_owns_single_operator_runtime() -> None:
    config = Config()
    config.logging.enabled = False

    agent = Agent(config)

    assert isinstance(agent.operator, OperatorRuntime)
    assert agent.operator.browser.session is agent.browser_session
    assert agent.operator.executor.tool_executor is agent.tool_executor
    assert agent.operator.input_broker is agent.operator.executor.input_broker


def test_agent_operator_stop_uses_runtime_broker() -> None:
    config = Config()
    config.logging.enabled = False
    agent = Agent(config)

    agent.stop_operator()
    assert agent.operator.input_broker.stopped is True
    agent.resume_operator()
    assert agent.operator.input_broker.stopped is False
