from queue import Queue
from types import SimpleNamespace

import api.modules.chats.image_service as image_service
from api.modules.chats.image_service import compose_image_prompt, run_image_turn

HISTORY = [
    {"role": "user", "content": "tạo file json n8n nhận báo cáo issue"},
    {"role": "assistant", "content": "Đã tạo file workflow n8n."},
]


def _chat(provider="openai"):
    return SimpleNamespace(provider=provider, model="m", user_id="u")


def _patch_text_model(monkeypatch, reply=None, fail=False):
    seen = {}

    class Client:
        def complete(self, system, history, tools):
            if fail:
                raise RuntimeError("no key")
            seen["prompt"] = history[0]["content"]
            return SimpleNamespace(text=reply)

    monkeypatch.setattr(image_service, "selected_settings", lambda *_: object())
    monkeypatch.setattr(image_service, "build_client", lambda _settings: Client())
    return seen


def test_prompt_is_composed_from_chat_context(monkeypatch) -> None:
    seen = _patch_text_model(monkeypatch, reply="Sơ đồ luồng n8n nhận báo cáo issue")
    assert compose_image_prompt(None, _chat(), "tạo ảnh minh họa", HISTORY) == "Sơ đồ luồng n8n nhận báo cáo issue"
    assert "n8n" in seen["prompt"]
    assert "tạo ảnh minh họa" in seen["prompt"]


def test_prompt_falls_back_without_context_or_on_error(monkeypatch) -> None:
    _patch_text_model(monkeypatch, fail=True)
    assert compose_image_prompt(None, _chat(), "vẽ mèo", HISTORY) == "vẽ mèo"
    assert compose_image_prompt(None, _chat(), "vẽ mèo", []) == "vẽ mèo"
    assert compose_image_prompt(None, _chat("ollama"), "vẽ mèo", HISTORY) == "vẽ mèo"


def test_image_turn_saves_the_prompt_in_history(monkeypatch) -> None:
    _patch_text_model(monkeypatch, reply="Sơ đồ luồng n8n")
    generated = {}

    class Images:
        def __init__(self, *_):
            pass

        def generate(self, prompt):
            generated["prompt"] = prompt
            return b"png"

    monkeypatch.setattr(image_service, "OpenAIImageService", Images)
    stored = {}
    services = SimpleNamespace(
        settings=SimpleNamespace(openai_api_key="k", openai_image_model="m"),
        library=SimpleNamespace(upload=lambda name, mime, data, source: SimpleNamespace(id="a1", name=name)),
        chats=SimpleNamespace(replace_history=lambda _id, history: stored.update(history=history)),
    )
    run_image_turn(services, _chat(), "c1", "tạo ảnh minh họa", [], HISTORY, Queue(), lambda m: m)

    assert generated["prompt"] == "Sơ đồ luồng n8n"
    assistant = stored["history"][-1]
    assert assistant["generated_asset_ids"] == ["a1"]
    assert "Sơ đồ luồng n8n" in assistant["content"]
    assert "ảnh" in assistant["content"]
