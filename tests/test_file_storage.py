from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_core.content.file_storage import FileStorageService


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


def test_workflow_upload_reconciles_lost_imagekit_response(tmp_path, monkeypatch):
    objects, uploads = [], []
    storage = FileStorageService(tmp_path, "key", "https://ik.example")
    def upload(**values):
        uploads.append(values)
        objects.append(SimpleNamespace(file_path=f"/library/{values['file_name']}", file_id="one-file"))
        raise TimeoutError("response lost after upload")
    storage._client = SimpleNamespace(files=SimpleNamespace(upload=upload), assets=SimpleNamespace(list=lambda **_: objects))
    monkeypatch.setattr(storage, "read", lambda *_: b"report")
    first = storage.upload_once(b"report", "asset", "imagekit")
    assert storage.upload_once(b"report", "asset", "imagekit") == first
    assert len(uploads) == 1 and not uploads[0]["overwrite_file"]
    assert uploads[0]["is_private_file"] and not uploads[0]["use_unique_file_name"]


def test_workflow_upload_never_reuses_corrupted_local_content(tmp_path):
    storage = FileStorageService(tmp_path)
    saved = storage.upload_once(b"report", "asset", "local")
    (tmp_path / saved.stored_name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checkpoint"):
        storage.upload_once(b"report", "asset", "local")
