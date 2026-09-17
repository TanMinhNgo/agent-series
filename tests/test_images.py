import base64
import sys
from types import SimpleNamespace

from agent_core.ai.images import OpenAIImageService


def test_openai_image_service_stores_generated_png_bytes(monkeypatch) -> None:
    expected = b"png-bytes"

    class FakeImages:
        def generate(self, **_kwargs):
            return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(expected).decode())])

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **_kwargs: SimpleNamespace(images=FakeImages())))

    assert OpenAIImageService("key", "gpt-image-1.5").generate("a lamp") == expected
