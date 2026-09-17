"""Small OpenAI Images API boundary for persisted chat image output."""

from __future__ import annotations

import base64


class ImageGenerationError(RuntimeError):
    pass


class OpenAIImageService:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    def generate(self, prompt: str) -> bytes:
        return self._request(prompt)

    def edit(self, prompt: str, image: dict) -> bytes:
        return self._request(prompt, image)

    def _request(self, prompt: str, image: dict | None = None) -> bytes:
        if not self.api_key:
            raise ImageGenerationError("Cần cấu hình OPENAI_API_KEY để dùng chế độ tạo ảnh.")
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            if image is None:
                response = client.images.generate(model=self.model, prompt=prompt, size="1024x1024", n=1, output_format="png")
            else:
                response = client.images.edit(
                    model=self.model,
                    prompt=prompt,
                    image=(image["name"], base64.b64decode(image["data"]), image["mimeType"]),
                    size="1024x1024",
                    n=1,
                    output_format="png",
                )
            encoded = response.data[0].b64_json
            if not encoded:
                raise ImageGenerationError("OpenAI không trả dữ liệu ảnh.")
            return base64.b64decode(encoded)
        except ImageGenerationError:
            raise
        except Exception as exc:  # OpenAI SDK normalizes provider errors differently by version.
            raise ImageGenerationError(f"Không thể tạo ảnh: {exc}") from exc
