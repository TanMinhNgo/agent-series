from agent_core.ai.agent import Agent
from agent_core.ai.providers import NormalizedReply
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

    assert result.status == "completed"
    assert result.text == "Đã xử lý."
    assert result.steps[0].result == "XIN CHAO"
    assert agent.history[-2]["role"] == "tool"


def test_agent_stops_at_step_limit():
    reply = NormalizedReply(tool_calls=[{"id": "1", "name": "echo", "args": {"text": "x"}}])
    agent = Agent(FakeClient([reply, reply]), ToolRegistry([ToolSpec("echo", "", {}, lambda text: text)]), max_steps=2)
    result = agent.run("x")
    assert result.status == "exhausted"
    assert "giới hạn số bước" in result.text
    assert agent.history[-1] == {"role": "assistant", "content": result.text}
    assert agent.history[-2]["role"] == "tool"
    assert agent.history[-2]["content"] == "x"


def test_agent_can_answer_an_already_persisted_user_message():
    agent = Agent(FakeClient([NormalizedReply(text="Đã chạy lịch.")]), ToolRegistry([]))
    agent.history = [{"role": "user", "content": "Chạy lịch"}]

    result = agent.run("Chạy lịch", append_user_message=False)

    assert result.text == "Đã chạy lịch."
    assert [item["role"] for item in agent.history] == ["user", "assistant"]


def test_agent_preserves_cancellation_and_provider_errors():
    from threading import Event
    import pytest
    from agent_core.ai.agent import AgentCancelled

    cancelled = Event()
    cancelled.set()
    agent = Agent(FakeClient([]), ToolRegistry([]))
    with pytest.raises(AgentCancelled):
        agent.run("stop", cancel_event=cancelled)

    failure = RuntimeError("provider timeout")
    class FailingClient:
        def complete(self, *_args):
            raise failure
    agent = Agent(FailingClient(), ToolRegistry([]))
    with pytest.raises(RuntimeError) as captured:
        agent.run("fail")
    assert captured.value is failure
