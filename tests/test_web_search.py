import json
from types import SimpleNamespace

from agent_core.web_search import sources_from_web_steps


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
