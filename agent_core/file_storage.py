"""Private ImageKit storage with a transparent local fallback and lazy migration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.request import urlopen
from uuid import uuid4


@dataclass(frozen=True)
class StoredFile:
    provider: str
    stored_name: str
    file_id: str | None = None


class FileStorageService:
    def __init__(self, directory: Path, private_key: str = "", url_endpoint: str = ""):
        self.directory = directory
        self.private_key = private_key
        self.url_endpoint = url_endpoint.rstrip("/")
        self.directory.mkdir(parents=True, exist_ok=True)
        self._client = None

    @property
    def imagekit_enabled(self) -> bool:
        return bool(self.private_key and self.url_endpoint)

    def _local_path(self, stored_name: str) -> Path:
        """Return a local storage object path, never a caller-selected path."""
        if not stored_name or "/" in stored_name or "\\" in stored_name or Path(stored_name).name != stored_name:
            raise ValueError("Tên file local không hợp lệ.")
        root = self.directory.resolve()
        path = (root / stored_name).resolve()
        if path.parent != root:
            raise ValueError("Đường dẫn file local không hợp lệ.")
        return path

    def _imagekit(self):
        if self._client is None:
            try:
                from imagekitio import ImageKit
            except ImportError as exc:
                raise RuntimeError("Thiếu thư viện imagekitio. Hãy cài lại requirements.txt.") from exc
            self._client = ImageKit(private_key=self.private_key)
        return self._client

    def upload(self, data: bytes, original_name: str, folder: str) -> StoredFile:
        suffix_match = re.search(r"\.[a-zA-Z0-9]{1,16}$", original_name)
        suffix = suffix_match.group(0).lower() if suffix_match else ".bin"
        generated_name = f"{uuid4().hex}{suffix}"
        if not self.imagekit_enabled:
            self._local_path(generated_name).write_bytes(data)
            return StoredFile("local", generated_name)
        try:
            response = self._imagekit().files.upload(
                file=data, file_name=generated_name, folder=f"/{folder.strip('/')}",
                is_private_file=True, use_unique_file_name=False,
            )
            return StoredFile("imagekit", str(response.file_path), str(response.file_id))
        except Exception as exc:  # noqa: BLE001 - SDK normalizes provider-specific errors poorly.
            raise RuntimeError("Không thể upload file lên ImageKit.") from exc

    def migrate_local(self, stored_name: str, original_name: str, folder: str) -> StoredFile | None:
        """Copy an old local object on first access; callers persist returned metadata."""
        if not self.imagekit_enabled:
            return None
        path = self._local_path(stored_name)
        if not path.is_file():
            return None
        return self.upload(path.read_bytes(), original_name, folder)

    def read(self, provider: str | None, stored_name: str, file_id: str | None) -> bytes:
        if provider != "imagekit" or not file_id:
            return self._local_path(stored_name).read_bytes()
        url = self.signed_url(provider, stored_name, file_id)
        try:
            with urlopen(url, timeout=20) as response:  # noqa: S310 - signed ImageKit URL generated locally.
                return response.read()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Không thể tải file từ ImageKit.") from exc

    def signed_url(self, provider: str | None, stored_name: str, file_id: str | None = None, expires_in: int = 300) -> str:
        if provider != "imagekit" or not file_id:
            raise RuntimeError("Local file không có CDN signed URL.")
        try:
            return self._imagekit().helper.build_url(
                url_endpoint=self.url_endpoint, src=stored_name, signed=True, expires_in=expires_in
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Không thể tạo URL bảo mật cho file ImageKit.") from exc

    def delete(self, provider: str | None, stored_name: str, file_id: str | None) -> None:
        if provider != "imagekit" or not file_id:
            path = self._local_path(stored_name)
            if path.exists():
                path.unlink()
            return
        try:
            self._imagekit().files.delete(file_id=file_id)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Không thể xóa file trên ImageKit.") from exc
