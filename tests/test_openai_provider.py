from types import SimpleNamespace

from agent_core.providers import OpenAIClient


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))])


def _client(model: str):
    completions = FakeCompletions()
    client = object.__new__(OpenAIClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client._model = model
    client._temperature = 0.2
    client._max_tokens = 99
    return client, completions


def test_gpt_56_uses_current_completion_token_parameter():
    client, completions = _client("gpt-5.6-terra")
    assert client.complete("system", [], []).text == "ok"
    assert completions.kwargs["max_completion_tokens"] == 99
    assert "max_tokens" not in completions.kwargs


def test_legacy_openai_model_keeps_max_tokens():
    client, completions = _client("gpt-4o-mini")
    client.complete("system", [], [])
    assert completions.kwargs["max_tokens"] == 99
