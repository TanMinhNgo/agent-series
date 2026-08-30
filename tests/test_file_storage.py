from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_core.file_storage import FileStorageService


def test_local_storage_upload_read_and_delete(tmp_path: Path) -> None:
    storage = FileStorageService(tmp_path)
    saved = storage.upload(b"hello", "note.txt", "library")

    assert saved.provider == "local"
    assert storage.read(saved.provider, saved.stored_name, saved.file_id) == b"hello"
    storage.delete(saved.provider, saved.stored_name, saved.file_id)
    assert not (tmp_path / saved.stored_name).exists()


def test_imagekit_storage_uses_private_upload_and_signed_url(tmp_path: Path) -> None:
    calls = []

    class Files:
        def upload(self, **values):
            calls.append(("upload", values))
            return SimpleNamespace(file_path="/users/a/chat/photo.png", file_id="ik-file-1")

        def delete(self, **values):
            calls.append(("delete", values))

    class Helper:
        def build_url(self, **values):
            calls.append(("url", values))
            return "https://ik.example/private-signed"

    storage = FileStorageService(tmp_path, "private-key", "https://ik.example")
    storage._client = SimpleNamespace(files=Files(), helper=Helper())
    saved = storage.upload(b"png", "photo.png", "chat")

    assert saved.provider == "imagekit"
    assert calls[0][1]["is_private_file"] is True
    assert storage.signed_url(saved.provider, saved.stored_name, saved.file_id) == "https://ik.example/private-signed"
    storage.delete(saved.provider, saved.stored_name, saved.file_id)
    assert calls[-1] == ("delete", {"file_id": "ik-file-1"})


def test_local_file_is_migrated_only_after_imagekit_is_enabled(tmp_path: Path) -> None:
    (tmp_path / "old.pdf").write_bytes(b"old")
    storage = FileStorageService(tmp_path)
    assert storage.migrate_local("old.pdf", "document.pdf", "knowledge") is None


@pytest.mark.parametrize("stored_name", ("../secret.txt", "nested/file.txt", "nested\\file.txt", ""))
def test_local_storage_rejects_user_controlled_paths(tmp_path: Path, stored_name: str) -> None:
    storage = FileStorageService(tmp_path)

    with pytest.raises(ValueError):
        storage.read("local", stored_name, None)
