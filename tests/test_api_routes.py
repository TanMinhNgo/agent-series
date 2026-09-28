"""HTTP routes: chats, messages, projects, workspaces, settings and catalog."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import api.main as main_module
from fastapi.testclient import TestClient
from pydantic import ValidationError
from api.contracts.requests import (
    BranchChatRequest, CollectionDocumentsRequest, FeedbackRequest, KnowledgeCollectionRequest, ProjectRequest,
    ShareRequest, UpdateArtifactRequest, UpdateChatRequest, WorkspaceInvitationRequest,
)
from api.main import app
from api.modules.common.serializers import chat_json, project_activity_json
from agent_core.integrations.plugin_catalog import CATALOG, find_catalog_plugin
from agent_core.runtime.credentials import CredentialError, UserCredentialService
from api_support import route, use_services


def test_project_activity_json_includes_an_actor_without_exposing_email() -> None:
    activity = SimpleNamespace(
        id="activity-1",
        event_type="artifact.deleted",
        subject_type="artifact",
        subject_id="asset-1",
        summary="Đã xóa file brief.md.",
        metadata_json=None,
        actor_user_id="user-1",
        created_at=datetime(2026, 9, 9, 9, 30, tzinfo=UTC),
    )
    actor = SimpleNamespace(display_name="Minh")

    assert project_activity_json(activity, actor) == {
        "id": "activity-1",
        "eventType": "artifact.deleted",
        "subjectType": "artifact",
        "subjectId": "asset-1",
        "summary": "Đã xóa file brief.md.",
        "metadata": {},
        "actorUserId": "user-1",
        "actorDisplayName": "Minh",
        "createdAt": "2026-09-09T09:30:00+00:00",
    }


def test_project_activity_endpoint_mutations_are_recorded(monkeypatch) -> None:
    activities: list[tuple] = []
    timestamp = datetime(2026, 9, 9, tzinfo=UTC)
    asset = SimpleNamespace(id="asset-1", artifact_id="artifact-1", name="brief.md", version=1, mime_type="text/markdown", size_bytes=10, source="upload", project_id="project-1", is_project_source=True, index_status="ready", index_error=None, created_at=timestamp)
    chat = SimpleNamespace(
        id="chat-1", title="Kế hoạch", provider="openai", model="gpt-test", project_id=None,
        created_at=timestamp, updated_at=timestamp, pinned=False, archived=False, is_unread=False,
        context_source_chat_id=None, parent_chat_id=None, branch_from_position=None, collection_id=None,
    )
    share = SimpleNamespace(token="token-1", title=chat.title, provider=chat.provider, model=chat.model, messages=[], created_at=timestamp, updated_at=timestamp, expires_at=None)

    class Workspace:
        def get(self, _entity, _id): return SimpleNamespace(id="project-1")
        def add_project_activity(self, *args): activities.append(args)

    class Library:
        def update(self, *_args, **_kwargs): return asset

    class Chats:
        def get(self, _id): return chat
        def update(self, _id, **values):
            for key, value in values.items(): setattr(chat, key, value)
            return chat
        def create_or_update_share(self, *_args): return share
        def revoke_share(self, _id): return True

    use_services(monkeypatch, SimpleNamespace(workspace=Workspace(), library=Library(), chats=Chats()))
    monkeypatch.setattr(main_module, "_enqueue_artifact_index", lambda *_args: None)
    monkeypatch.setattr(main_module, "_selected_settings", lambda *_args: None)

    route("update_library_asset")("asset-1", UpdateArtifactRequest(isProjectSource=True))
    updated = route("update_chat")("chat-1", UpdateChatRequest(projectId="project-1"))
    route("share_chat")("chat-1")
    route("revoke_share")("chat-1")
    main_module.record_workspace_activity("workspace.invitation_created", "workspace_invitation", "invite-1", "Đã mời thành viên.")

    assert updated["projectId"] == "project-1"
    assert [item[1] for item in activities] == [
        "project_source.pinned", "chat.added", "chat.shared", "chat.share_revoked", "workspace.invitation_created",
    ]


def test_project_collections_and_overview_record_and_return_project_data(monkeypatch) -> None:
    activities: list[tuple] = []
    timestamp = datetime(2026, 9, 9, tzinfo=UTC)
    project = SimpleNamespace(id="project-1", name="Roadmap", description=None, status="active", instructions=None, memory_mode="default", created_at=timestamp, updated_at=timestamp)
    collection = SimpleNamespace(id="collection-1", project_id="project-1", name="Nguồn", description=None, created_at=timestamp, updated_at=timestamp)

    activity = SimpleNamespace(
        id="activity-1", event_type="project.updated", subject_type="project", subject_id="project-1",
        summary="Đã cập nhật Project.", metadata_json=None, actor_user_id="user-1", created_at=timestamp,
    )

    class Result(list):
        def all(self): return list(self)

    class Session:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def scalars(self, _statement):
            return Result([SimpleNamespace(id="user-1", display_name="Minh")]) if "users" in str(_statement) else Result()

    class Workspace:
        def get(self, _entity, _id): return project
        def add_project_activity(self, *args): activities.append(args)
        def project_activity(self, _id): return [activity]
        def connector_scopes(self, _id): return []

    class Knowledge:
        def create_collection(self, *_args): return collection
        def get_collection(self, _id): return collection
        def update_collection(self, *_args): return collection
        def collection_documents(self, _id): return []
        def set_collection_documents(self, *_args): return []
        def delete_collection(self, _id): return True

    database = SimpleNamespace(session=lambda: Session())
    service = SimpleNamespace(workspace=Workspace(), knowledge=Knowledge(), chats=SimpleNamespace(database=database))
    use_services(monkeypatch, service)

    payload = KnowledgeCollectionRequest(name="Nguồn")
    assert route("create_collection")("project-1", payload)["id"] == "collection-1"
    assert route("update_collection")("collection-1", payload)["id"] == "collection-1"
    assert route("set_collection_documents")("collection-1", CollectionDocumentsRequest(documentIds=[]))["documentIds"] == []
    route("delete_collection")("collection-1")
    detail = route("get_project")("project-1")

    assert detail["project"]["id"] == "project-1"
    assert detail["activity"][0]["actorDisplayName"] == "Minh"
    assert [item[1] for item in activities] == ["collection.created", "collection.updated", "collection.documents_updated", "collection.deleted"]


def test_workspace_invitation_activity_is_recorded(monkeypatch) -> None:
    activities: list[tuple] = []
    invitation = SimpleNamespace(id="invite-1", email="member@example.com", role="viewer", expires_at=datetime(2026, 9, 16, tzinfo=UTC), created_at=datetime(2026, 9, 9, tzinfo=UTC))

    class Workspace:
        def invite(self, *_args): return invitation
        def cancel_invitation(self, *_args): return True
        def add_project_activity(self, *args): activities.append(args)

    service = SimpleNamespace(
        workspace=Workspace(),
        settings=SimpleNamespace(app_web_url="http://localhost:5173"),
        email=SimpleNamespace(enabled=False),
    )
    use_services(monkeypatch, service)
    token = main_module.current_workspace_id.set("workspace-1")
    try:
        owner = SimpleNamespace(user_id="owner-1", role="owner")
        request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id="owner-1"), workspace_membership=owner))
        result = route("create_workspace_invitation")(WorkspaceInvitationRequest(email="member@example.com"), request)
        route("cancel_workspace_invitation")("invite-1", request)
    finally:
        main_module.current_workspace_id.reset(token)

    assert result["id"] == "invite-1"
    assert [item[1] for item in activities] == ["workspace.invitation_created", "workspace.invitation_revoked"]


def test_restore_library_asset_version_copies_the_selected_version(monkeypatch) -> None:
    restored = SimpleNamespace(
        id="asset-v3", artifact_id="artifact-1", name="ke-hoach.md", version=3, mime_type="text/markdown", size_bytes=20,
        source="generated", project_id=None, is_project_source=False, index_status="pending", index_error=None,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    observed: list[str] = []
    service = SimpleNamespace(library=SimpleNamespace(restore_version=lambda asset_id: observed.append(asset_id) or restored))
    use_services(monkeypatch, service)
    monkeypatch.setattr(main_module, "_enqueue_artifact_index", lambda asset, _services: observed.append(asset.id))

    result = route("restore_library_asset_version")("asset-v1")

    assert (result["id"], result["version"]) == ("asset-v3", 3)
    assert observed == ["asset-v1", "asset-v3"]


def test_chat_json_exposes_unread_state() -> None:
    chat = SimpleNamespace(
        id="chat-1",
        title="Lịch: học frontend",
        provider="openai",
        model="gpt-test",
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
        updated_at=datetime(2026, 8, 24, tzinfo=UTC),
        pinned=False,
        archived=False,
        is_unread=True,
        context_source_chat_id=None,
        project_id=None,
        parent_chat_id=None,
        branch_from_position=None,
        collection_id=None,
    )

    assert chat_json(chat)["isUnread"] is True


def test_health_and_public_config_do_not_expose_provider_keys(monkeypatch) -> None:
    # The registry deliberately preserves models disabled by an administrator.
    # Stub the available set here so this public-response contract never depends
    # on the shared local PostgreSQL state used by other tests.
    monkeypatch.setattr(main_module, "available_provider_models", lambda _user_id, _ollama_models=None: {"gemini": ["gemini-test"]})
    fake_services = SimpleNamespace(
        settings=SimpleNamespace(provider="gemini", active_model="gemini-test", gemini_api_key="test-secret"),
        auth=SimpleNamespace(session_user=lambda _cookie: None),
        ollama=SimpleNamespace(models=lambda: []),
    )
    monkeypatch.setattr(app.state, "services", fake_services, raising=False)
    monkeypatch.setattr(main_module, "build_services", lambda: fake_services)
    monkeypatch.setattr(main_module, "queue_pending_artifacts", lambda _services: 0)

    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        payload = client.get("/api/config").json()

    assert payload["providers"] == {"gemini": ["gemini-test"]}
    assert "ollama" in payload["providerStatus"]
    assert "key" not in str(payload).lower()


def test_messages_include_only_current_users_feedback(monkeypatch) -> None:
    class Chats:
        def get(self, _chat_id): return SimpleNamespace(id="chat-1")
        def history(self, _chat_id):
            return [
                {"message_id": "user-1", "role": "user", "content": "Câu hỏi"},
                {"message_id": "assistant-1", "role": "assistant", "content": "Trả lời"},
            ]

    class Personalization:
        def feedback_by_message_ids(self, message_ids):
            assert message_ids == ["assistant-1"]
            return {"assistant-1": "helpful"}

    use_services(monkeypatch, SimpleNamespace(chats=Chats(), personalization=Personalization(), workspace=SimpleNamespace()))

    result = route("messages")("chat-1")

    assert result[0].get("feedbackKind") is None
    assert result[1]["feedbackKind"] == "helpful"


def test_messages_attach_artifacts_to_the_creating_assistant_response(monkeypatch) -> None:
    asset = SimpleNamespace(
        id="asset-1",
        artifact_id="artifact-1",
        name="ke-hoach.md",
        version=1,
        mime_type="text/markdown",
        size_bytes=20,
        source="generated",
        project_id=None,
        is_project_source=False,
        index_status="pending",
        index_error=None,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )

    class Chats:
        def get(self, _chat_id): return SimpleNamespace(id="chat-1")
        def backfill_artifact_links(self, chat_id): assert chat_id == "chat-1"
        def history(self, _chat_id):
            return [
                {"message_id": "user-1", "role": "user", "content": "Tạo kế hoạch"},
                {"message_id": "assistant-1", "role": "assistant", "content": "Đã tạo."},
            ]
        def artifacts_by_assistant_message(self, chat_id, message_ids):
            assert (chat_id, message_ids) == ("chat-1", ["assistant-1"])
            return {"assistant-1": [asset]}

    use_services(monkeypatch, SimpleNamespace(chats=Chats(), personalization=SimpleNamespace(feedback_by_message_ids=lambda _ids: {}), workspace=SimpleNamespace()))

    result = route("messages")("chat-1")

    assert result[1]["artifacts"] == [{
        "id": "asset-1", "artifactId": "artifact-1", "name": "ke-hoach.md", "version": 1,
        "mimeType": "text/markdown", "sizeBytes": 20, "source": "generated", "projectId": None,
        "isProjectSource": False, "indexStatus": "pending", "indexError": None,
        "createdAt": "2026-09-02T00:00:00+00:00", "url": "/api/library/assets/asset-1/file",
    }]


def test_feedback_branch_and_regenerate_endpoints_delegate_the_selected_message(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []
    timestamp = datetime(2026, 8, 24, tzinfo=UTC)
    branch = SimpleNamespace(
        id="branch-1",
        title="Nhánh hội thoại",
        provider="openai",
        model="gpt-5.6-terra",
        created_at=timestamp,
        updated_at=timestamp,
        pinned=False,
        archived=False,
        context_source_chat_id=None,
        project_id=None,
        parent_chat_id="chat-1",
        branch_from_position=1,
        collection_id=None,
    )

    class Personalization:
        def record_feedback(self, message_id, kind, note):
            calls.append(("feedback", message_id, kind))
            return SimpleNamespace(id="feedback-1", message_id=message_id, kind=kind, note=note)

    class Chats:
        def create_branch(self, chat_id, message_id):
            calls.append(("branch", chat_id, message_id))
            return branch

        def prepare_regeneration(self, chat_id, message_id):
            calls.append(("regenerate", chat_id, message_id))
            return "Câu hỏi gốc"

    use_services(monkeypatch, SimpleNamespace(personalization=Personalization(), chats=Chats()))

    feedback = route("create_response_feedback")("assistant-1", FeedbackRequest(kind="helpful"))
    created_branch = route("create_chat_branch")("chat-1", BranchChatRequest(assistantMessageId="assistant-1"))
    regeneration = route("prepare_chat_regeneration")("chat-1", BranchChatRequest(assistantMessageId="assistant-1"))

    assert feedback == {"id": "feedback-1", "messageId": "assistant-1", "kind": "helpful", "note": None}
    assert created_branch["id"] == "branch-1"
    assert regeneration == {"content": "Câu hỏi gốc"}
    assert calls == [
        ("feedback", "assistant-1", "helpful"),
        ("branch", "chat-1", "assistant-1"),
        ("regenerate", "chat-1", "assistant-1"),
    ]


def test_user_credential_service_encrypts_and_hides_plaintext(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    saved = {}
    class Repository:
        def save_user_provider_credential(self, user_id, provider, ciphertext, key_hint):
            saved.update(user_id=user_id, provider=provider, ciphertext=ciphertext, key_hint=key_hint)
            return SimpleNamespace(provider=provider, ciphertext=ciphertext, key_hint=key_hint)
        def user_provider_credential(self, user_id, provider):
            return SimpleNamespace(ciphertext=saved["ciphertext"]) if saved else None
        def user_provider_credentials(self, _user_id): return []

    service = UserCredentialService(Repository(), SimpleNamespace(user_credential_encryption_key=Fernet.generate_key().decode(), provider_models={"anthropic": ("claude-test",)}))
    monkeypatch.setattr(service, "validate", lambda _provider, _key: None)
    service.save("user-1", "openai", "sk-secret-value")

    assert saved["key_hint"] == "••••alue"
    assert "sk-secret-value" not in saved["ciphertext"]
    assert service.api_key("user-1", "openai") == "sk-secret-value"
    with pytest.raises(CredentialError):
        service.save("user-1", "unknown", "sk-secret-value")


def test_chat_history_list_is_paginated(monkeypatch) -> None:
    records = [
        SimpleNamespace(
            id=f"chat-{index}", title="Cuộc trò chuyện mới", provider="openai", model="gpt-5.6-terra",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            pinned=False, archived=False, context_source_chat_id=None,
        )
        for index in range(3)
    ]

    class Chats:
        def list(self, offset: int, limit: int):
            return records[offset:offset + limit], len(records)

    class Services:
        chats = Chats()

    use_services(monkeypatch, Services())
    page = route("list_chats")(offset=0, limit=2)

    assert [item["id"] for item in page["items"]] == ["chat-0", "chat-1"]
    assert page["total"] == 3
    assert page["nextOffset"] == 2


def test_share_request_accepts_an_optional_expiry() -> None:
    assert ShareRequest.model_validate({"expiresAt": "2026-08-20T09:00:00+07:00"}).expires_at is not None
    assert ShareRequest().expires_at is None


def test_project_status_is_limited_to_workspace_statuses() -> None:
    assert ProjectRequest(name="Agent Series").status == "active"
    assert ProjectRequest(name="Agent Series", status="completed").status == "completed"
    with pytest.raises(ValidationError):
        ProjectRequest(name="Agent Series", status="planning")


def test_plugin_catalog_has_unique_slugs_and_expected_core_apps() -> None:
    slugs = [item.slug for item in CATALOG]
    expected_categories = {
        "productivity", "creative", "developer", "business", "education", "analytics", "communication",
        "security", "finance", "health", "travel", "entertainment", "other",
    }
    assert len(slugs) == len(set(slugs)) == 65
    assert {item.category for item in CATALOG} == expected_categories
    assert all(sum(item.category == category for item in CATALOG) == 5 for category in expected_categories)
    assert [item.slug for item in CATALOG if item.featured] == ["google-workspace", "notion", "figma", "github", "slack"]
    assert find_catalog_plugin("github").name == "GitHub"
    assert find_catalog_plugin("missing") is None
