from agent_core.agent import Agent
from agent_core.providers import NormalizedReply
from agent_core.tools.base import ToolSpec
from agent_core.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)

    def complete(self, system, history, tools):
        return next(self.replies)


def test_agent_observes_tool_result_before_final_answer():
    registry = ToolRegistry([ToolSpec("echo", "", {}, lambda text: text.upper())])
    agent = Agent(FakeClient([
        NormalizedReply(tool_calls=[{"id": "1", "name": "echo", "args": {"text": "xin chao"}}]),
        NormalizedReply(text="Đã xử lý."),
    ]), registry)

    result = agent.run("Hãy xử lý")

    assert result.text == "Đã xử lý."
    assert result.steps[0].result == "XIN CHAO"
    assert agent.history[-2]["role"] == "tool"


def test_agent_stops_at_step_limit():
    reply = NormalizedReply(tool_calls=[{"id": "1", "name": "echo", "args": {"text": "x"}}])
    agent = Agent(FakeClient([reply, reply]), ToolRegistry([ToolSpec("echo", "", {}, lambda text: text)]), max_steps=2)
    assert "giới hạn số bước" in agent.run("x").text
