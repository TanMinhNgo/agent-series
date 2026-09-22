import json
from types import SimpleNamespace

from agent_core.integrations.web_search import WebSearchService, sources_from_web_steps


def test_sources_from_web_steps_keeps_only_unique_https_results() -> None:
    result = json.dumps(
        {
            "sources": [
                {"name": "Official docs", "url": "https://example.com/docs"},
                {"name": "Duplicate", "url": "https://example.com/docs"},
                {"name": "Unsafe", "url": "http://example.com"},
            ]
        }
    )

    sources = sources_from_web_steps([SimpleNamespace(tool="search_web", result=result)])

    assert sources == [{"name": "Official docs", "url": "https://example.com/docs", "kind": "external"}]


def test_web_search_preserves_content_per_source(monkeypatch) -> None:
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self):
            return json.dumps({"results": [
                {"title": "One", "url": "https://example.com/1", "content": "first"},
                {"title": "Two", "url": "https://example.com/2", "content": "second"},
            ]}).encode()
    monkeypatch.setattr("agent_core.integrations.web_search.urlopen", lambda *_args, **_kwargs: Response())
    result = WebSearchService("test-key").require_sources("AI")
    assert [source["content"] for source in result["sources"]] == ["first", "second"]
