"""Exercise persistence paths that API tests replace with service stubs."""

from datetime import UTC, datetime, timedelta

import pytest

from agent_core.persistence.store import (
    AuthRepository, BackgroundJobRepository, Base, ChatRepository, Database,
    ConnectorRepository, LibraryAsset, MediaRepository, ModelRegistryRepository, Plugin, Project,
    Schedule, ScheduleRepository, User, WorkspaceRepository, current_user_id,
)


@pytest.fixture
def database(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(db.engine)
    return db


def test_job_deduplication_retry_and_worker_status(database):
    jobs = BackgroundJobRepository(database)
    now = datetime.now(UTC)
    first, created = jobs.enqueue_unique("document_index", {"id": "one"}, "document:one")
    assert created
    same, created = jobs.enqueue_unique("document_index", {"id": "one"}, "document:one")
    assert not created and same.id == first.id
    assert jobs.latest_for_document("one").id == first.id
    assert jobs.claim(now + timedelta(seconds=1)).id == first.id
    jobs.fail(first.id, "temporary", now)
    assert jobs.claim(now + timedelta(seconds=1)) is None
    assert jobs.claim(now + timedelta(seconds=3)).id == first.id
    jobs.fail(first.id, "permanent", now)
    assert jobs.claim(now + timedelta(seconds=20)).id == first.id
    jobs.fail(first.id, "permanent", now)
    assert jobs.worker_status(now)["lastError"] == "permanent"
    jobs.heartbeat(now, "document_index", "worker error")
    status = jobs.worker_status(now)
    assert status["online"] and status["lastError"] == "worker error"
    assert status["currentJobType"] == "document_index"
    replacement, created = jobs.enqueue_unique("document_index", {"id": "one"}, "document:one")
    assert created and replacement.id != first.id
    assert jobs.cancel_document_jobs(["one"]) == 1
    assert jobs.claim(now + timedelta(minutes=1)) is None


def test_chat_branch_regeneration_and_history(database):
    chats = ChatRepository(database)
    chat = chats.create("openai", "initial")
    history = [
        {"role": "user", "content": "First question", "attachments": [{"name": "a", "data": "private"}]},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Second question"},
        {"role": "assistant", "content": "Second answer"},
    ]
    chats.replace_history(chat.id, history)
    assert chats.get(chat.id).title == "First question"
    assert chats.list()[1] == 1
    branch = chats.create_branch(chat.id, history[3]["message_id"])
    assert branch.parent_chat_id == chat.id
    assert chats.prepare_regeneration(chat.id, history[3]["message_id"]) == "Second question"
    with pytest.raises(ValueError, match="phản hồi AI"):
        chats.prepare_regeneration(chat.id, history[3]["message_id"])
    assert chats.set_message_pin(history[0]["message_id"], True).pinned
    assert [item.id for item in chats.chat_pins(chat.id)] == [history[0]["message_id"]]
    assert chats.set_unread(chat.id, True).is_unread
    chats.update_model(chat.id, "anthropic", "new-model")
    assert chats.update(chat.id, title="Updated", project_id=None).model == "new-model"
    assert chats.delete(chat.id)
    assert chats.get(chat.id) is None


def test_user_credentials_session_and_workspace_invitation(database):
    auth = AuthRepository(database)
    workspaces = WorkspaceRepository(database)
    now = datetime.now(UTC)
    owner = auth.create_user("owner@example.com")
    invitee = auth.create_user("invitee@example.com")
    assert auth.user_count() == 2
    assert auth.get_user_by_email(owner.email).id == owner.id
    assert auth.link_or_get_identity(owner.id, "google", "subject").id == owner.id
    assert auth.get_user_for_identity("google", "subject").id == owner.id
    auth.create_session(owner.id, "token", now + timedelta(hours=1))
    assert auth.user_for_session("token", now).id == owner.id
    auth.revoke_session("token")
    assert auth.user_for_session("token", now) is None
    auth.save_user_provider_credential(owner.id, "openai", "cipher-one", "one")
    assert auth.save_user_provider_credential(owner.id, "openai", "cipher-two", "two").ciphertext == "cipher-two"
    assert len(auth.user_provider_credentials(owner.id)) == 1
    assert auth.delete_user_provider_credential(owner.id, "openai")

    workspace = workspaces.create_workspace(owner.id, "Team")
    assert len(workspaces.list_for_user(owner.id)) == 1
    assert workspaces.membership(workspace.id, owner.id).role == "owner"
    assert workspaces.default_for_user(owner.id).workspace_id == workspace.id
    invitation = workspaces.invite(workspace.id, invitee.email, "editor", owner.id, now + timedelta(days=1))
    assert workspaces.invitations(workspace.id)[0].id == invitation.id
    assert workspaces.accept_invitation(invitation.id, invitee.id, invitee.email, now.replace(tzinfo=None)).role == "editor"
    assert workspaces.update_member_role(workspace.id, invitee.id, "viewer").role == "viewer"
    assert workspaces.remove_member(workspace.id, invitee.id)
    assert workspaces.membership(workspace.id, invitee.id) is None
    personal = workspaces.ensure_personal_workspace(owner.id)
    assert workspaces.ensure_personal_workspace(owner.id).id == personal.id
    assert auth.set_user_active(invitee.id, False).is_active is False


def test_schedule_retries_keep_one_run_and_heartbeat_prevents_recovery(database):
    workspace = WorkspaceRepository(database)
    schedules = ScheduleRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    schedule = workspace.create(Schedule, title="Daily", starts_at=now, next_run_at=now, recurrence="daily")
    claimed = schedules.claim_due(now)
    assert len(claimed) == 1
    _, run = claimed[0]
    assert schedules.claim_due(now) == []
    assert schedules.get_run(schedule.id, run.id).status == "running"
    due, attempt = schedules.schedule_retry(run.id, "rate limited", (1,), now)
    assert attempt == 1 and due == now + timedelta(minutes=1)
    assert schedules.claim_due_retries(now) == []
    assert schedules.claim_due_retries(due)[0][1].id == run.id
    assert schedules.schedule_retry(run.id, "again", (1,), due) is None
    assert schedules.touch_run(run.id, due)
    assert schedules.recover_stale_runs(due + timedelta(minutes=10)) == 0
    assert schedules.record_email(run.id, status="sent").email_status == "sent"
    assert schedules.finish(run.id, summary="Done").status == "succeeded"
    assert not schedules.touch_run(run.id, due)
    assert [item.id for item in schedules.list_runs(schedule.id)] == [run.id]
    manual = schedules.claim_manual(schedule.id, due + timedelta(minutes=2))
    assert manual[1].id != run.id
    with pytest.raises(ValueError, match="đang chạy"):
        schedules.claim_manual(schedule.id, due + timedelta(minutes=3))
    assert schedules.recover_stale_runs(due + timedelta(hours=1)) == 1


def test_connector_metadata_never_exposes_secret_and_oauth_state_is_one_time(database):
    auth = AuthRepository(database)
    owner = auth.create_user("connector@example.com")
    connectors = ConnectorRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    token = current_user_id.set(owner.id)
    try:
        connection = connectors.save_connection("github", "secret", owner.email, ["read"], None)
        assert connectors.get_connection("github").id == connection.id
        assert connectors.save_connection("github", "new-secret", owner.email, ["read"], None).id == connection.id
    finally:
        current_user_id.reset(token)
    rows, total = connectors.list_connection_metadata(0, 10, query="connector@", connector_slug="github", status="connected")
    assert total == 1 and rows[0]["user_email"] == owner.email
    assert "encrypted_token" not in rows[0]
    connectors.audit("github", "connected", connection.id)
    assert connectors.list_audit("github")[0].event_type == "connected"
    connectors.create_oauth_state("state", "github", now + timedelta(minutes=1))
    assert connectors.consume_oauth_state("state", now).connector_slug == "github"
    assert connectors.consume_oauth_state("state", now) is None
    assert connectors.set_connection_status("github", "expired").status == "expired"
    assert connectors.delete_connection("github")
    assert connectors.get_connection("github") is None


def test_registry_and_media_storage_changes_are_persisted(database):
    registry = ModelRegistryRepository(database)
    registry.seed({"openai": ("model-a", "model-b")})
    registry.seed({"openai": ("model-a",)})
    assert len(registry.list()) == 2
    assert registry.active()["openai"] == ("model-a", "model-b")
    assert registry.set_active("openai", "model-b", False).is_active is False
    assert registry.active()["openai"] == ("model-a",)
    registry.set_setting("default_model", "model-a")
    registry.set_setting("default_model", "model-b")
    assert registry.setting("default_model") == "model-b"
    media = MediaRepository(database)
    attachment = media.create(original_name="photo.jpg", stored_name="local-photo", mime_type="image/jpeg", size_bytes=12)
    assert media.get_many([attachment.id])[0].stored_name == "local-photo"
    assert media.replace_storage(attachment.id, "imagekit", "remote-photo", "file-id").storage_file_id == "file-id"
    assert media.replace_storage("missing", "imagekit", "missing", None) is None


def test_workspace_proposal_is_claimed_once_and_plugin_changes_persist(database, monkeypatch):
    workspaces = WorkspaceRepository(database)
    plugin = workspaces.create(Plugin, slug="github", name="GitHub", catalog_slug="github")
    assert workspaces.get_plugin_by_catalog_slug("github").id == plugin.id
    assert workspaces.catalog_plugin_ids()["github"] == plugin.id
    assert workspaces.update(Plugin, plugin.id, enabled=True).enabled
    assert workspaces.list_plugins()[0].id == plugin.id
    assert workspaces.delete(Plugin, plugin.id)
    project = workspaces.create(Project, name="Project")
    scope = workspaces.save_connector_scope(project.id, "github", {"repos": ["team/repo"]})
    assert workspaces.connector_scopes(project.id)[0].id == scope.id
    assert workspaces.save_connector_scope(project.id, "github", {"repos": []}).config == {"repos": []}
    assert workspaces.delete_connector_scope(project.id, "github")
    monkeypatch.setattr("agent_core.persistence.repositories.workspace.utc_now", lambda: datetime.now(UTC).replace(tzinfo=None))
    proposal = workspaces.create_external_proposal("create_issue", {"title": "Review"}, project.id)
    assert workspaces.claim_external_proposal(proposal.id).status == "running"
    assert workspaces.claim_external_proposal(proposal.id) is None
    assert workspaces.finish_external_proposal(proposal.id, "denied").status == "failed"
    assert workspaces.finish_external_proposal(proposal.id) is None


def test_chat_share_rotation_and_artifact_provenance(database):
    chats = ChatRepository(database)
    chat = chats.create("openai", "model-a")
    history = [
        {"role": "user", "content": "Make a file"},
        {"role": "tool", "name": "create_file", "content": "invalid json"},
        {"role": "assistant", "content": "Done"},
    ]
    chats.replace_history(chat.id, history)
    assert chats.history(chat.id)[0]["content"] == "Make a file"
    share = chats.create_or_update_share(chat.id)
    assert [item["role"] for item in share.messages] == ["user", "assistant"]
    assert chats.get_share(share.token).id == share.id
    rotated = chats.create_or_update_share(chat.id)
    assert rotated.id == share.id and rotated.token != share.token
    assert chats.get_share(share.token) is None
    asset = LibraryAsset(name="output.txt", stored_name="output-one", mime_type="text/plain", size_bytes=4)
    with database.session() as session:
        session.add(asset)
        session.commit()
    linked = chats.link_artifacts_to_turn(chat.id, history[0]["message_id"], history[2]["message_id"], [asset.id])
    assert linked[0].id == asset.id
    assert chats.artifacts_by_assistant_message(chat.id, [history[2]["message_id"]])[history[2]["message_id"]][0].id == asset.id
    assert chats.link_artifacts_to_turn(chat.id, history[0]["message_id"], history[2]["message_id"], [asset.id])
    assert chats.revoke_share(chat.id)
    assert chats.get_share(rotated.token) is None
    assert chats.revoke_share(chat.id) is False
    assert chats.create_or_update_share("missing") is None
    assert chats.link_artifacts_to_turn(chat.id, history[0]["message_id"], history[2]["message_id"], []) == []
    assert chats.artifacts_by_assistant_message(chat.id, []) == {}

    legacy = chats.create("openai", "model-a")
    legacy_history = [
        {"role": "user", "content": "Legacy file"},
        {"role": "tool", "name": "create_file", "content": f'{{"id": "{asset.id}"}}'},
        {"role": "assistant", "content": "Done"},
    ]
    chats.replace_history(legacy.id, legacy_history)
    chats.backfill_artifact_links(legacy.id)
    chats.backfill_artifact_links(legacy.id)
    assert len(chats.artifacts_by_assistant_message(legacy.id, [legacy_history[2]["message_id"]])[legacy_history[2]["message_id"]]) == 1


def test_auth_admin_lists_and_oauth_state_expiration(database):
    auth = AuthRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    user = auth.create_user("admin@example.com")
    assert auth.get_user(user.id).email == user.email
    assert auth.list_users("admin", 0, 10)[1] == 1
    auth.save_user_provider_credential(user.id, "openai", "ciphertext", "hint")
    assert auth.provider_credential_metadata(0, 10)[1] == 1
    assert auth.user_provider_credential(user.id, "openai").key_hint == "hint"
    auth.add_system_audit("user-created", actor_user_id=user.id)
    assert auth.list_system_audit(0, 10)[1] == 1
    assert auth.system_counts()["users"] == 1
    auth.create_auth_oauth_state("state", "login", now + timedelta(minutes=1))
    assert auth.consume_auth_oauth_state("state", now) == "login"
    assert auth.consume_auth_oauth_state("state", now) is None
    auth.create_auth_oauth_state("expired", "login", now - timedelta(minutes=1))
    assert auth.consume_auth_oauth_state("expired", now) is None
    assert auth.set_user_active("missing", False) is None


def test_legacy_chat_ownership_and_retrieval_traces(database):
    auth = AuthRepository(database)
    user = auth.create_user("legacy@example.com")
    chats = ChatRepository(database)
    workspaces = WorkspaceRepository(database)
    chat = chats.create("openai", "model-a")
    history = chats.replace_history(chat.id, [{"role": "user", "content": "Find source"}])
    message_id = history[0]["message_id"]
    assert workspaces.retrieval_traces([]) == {}
    workspaces.save_retrieval_traces(message_id, None, [{"source_kind": "web", "source_id": "source-1", "source_name": "Example", "url": "https://example.com"}])
    assert workspaces.retrieval_traces([message_id])[message_id][0].source_name == "Example"
    auth.claim_legacy_data(user.id)
    assert chats.get(chat.id).user_id == user.id
    workspace = auth.ensure_personal_workspace(user.id)
    auth.claim_legacy_workspace_data(user.id, workspace.id)
    assert chats.get(chat.id).workspace_id == workspace.id


def test_chat_rejects_missing_or_foreign_messages(database):
    chats = ChatRepository(database)
    chat = chats.create("openai", "model-a")
    with pytest.raises(ValueError, match="Không tìm thấy chat"):
        chats.create_branch("missing", "missing")
    with pytest.raises(ValueError, match="phản hồi AI"):
        chats.create_branch(chat.id, "missing")
    with pytest.raises(ValueError, match="Không tìm thấy chat"):
        chats.replace_history("missing", [])
    with pytest.raises(ValueError, match="phản hồi AI"):
        chats.prepare_regeneration(chat.id, "missing")
    assert chats.set_message_pin("missing", True) is None
    assert chats.set_unread("missing", True) is None
    assert chats.update("missing", title="No") is None
    assert chats.delete("missing") is False


def test_stale_jobs_recover_and_removed_documents_cancel_only_matching_work(database):
    jobs = BackgroundJobRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    assert jobs.claim(now) is None
    old = jobs.enqueue("document_index", {"id": "old"}, dedupe_key="document:old")
    other = jobs.enqueue("document_index", {"id": "other"}, dedupe_key="document:other")
    assert jobs.claim(now + timedelta(seconds=1)).id == old.id
    assert jobs.recover_stale(now + timedelta(minutes=30)) == 1
    assert jobs.claim(now + timedelta(minutes=31)).id == other.id
    assert jobs.cancel_document_jobs(["old"]) == 1
    jobs.succeed(other.id)
    assert jobs.worker_status(now + timedelta(minutes=31))["running"] == 0
    assert jobs.worker_status(now + timedelta(minutes=31))["queued"] == 0
    assert jobs.cancel_document_jobs([]) == 0
    assert jobs.latest_for_document("missing") is None


def test_workspace_invitation_and_activity_are_scoped_to_project(database):
    auth = AuthRepository(database)
    owner = auth.create_user("scope@example.com")
    workspaces = WorkspaceRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    workspace = workspaces.create_workspace(owner.id, "Team")
    invitation = workspaces.invite(workspace.id, "new@example.com", "viewer", owner.id, now + timedelta(days=1))
    changed = workspaces.invite(workspace.id, "new@example.com", "editor", owner.id, now + timedelta(days=2))
    assert changed.id == invitation.id and changed.role == "editor"
    assert workspaces.cancel_invitation(workspace.id, invitation.id)
    assert workspaces.invitations(workspace.id) == []
    assert workspaces.accept_invitation(invitation.id, owner.id, "new@example.com", now) is None
    project = workspaces.create(Project, name="Scoped")
    event = workspaces.add_project_activity(project.id, "created", "project", project.id, "Created")
    assert workspaces.project_activity(project.id)[0].id == event.id
    assert workspaces.project_activity("another-project") == []
    assert workspaces.delete_connector_scope(project.id, "missing") is False
    assert workspaces.get(Plugin, "missing") is None
    assert workspaces.update(Plugin, "missing", enabled=True) is None
    assert workspaces.delete(Plugin, "missing") is False


def test_manual_run_cancels_pending_retry_and_links_chat(database):
    workspace = WorkspaceRepository(database)
    schedules = ScheduleRepository(database)
    chats = ChatRepository(database)
    now = datetime.now(UTC).replace(tzinfo=None)
    schedule = workspace.create(Schedule, title="One-off", starts_at=now, next_run_at=now, recurrence="once")
    assert schedules.claim_manual("missing", now) is None
    _, first = schedules.claim_manual(schedule.id, now)
    schedules.schedule_retry(first.id, "provider offline", (1,), now)
    _, second = schedules.claim_manual(schedule.id, now + timedelta(minutes=2))
    assert schedules.get_run(schedule.id, first.id).status == "cancelled"
    assert second.id != first.id
    chat = chats.create("openai", "model-a")
    schedules.attach_chat(schedule.id, chat.id)
    assert workspace.get(Schedule, schedule.id).chat_id == chat.id
    assert schedules.finish(second.id, error="failed").status == "failed"
