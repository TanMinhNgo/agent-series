"""ORM models, shared constants, and request-scoped ownership filters."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime
from secrets import token_urlsafe
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, event, ForeignKey, Index, Integer, JSON, String, Text, text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, with_loader_criteria


GLOBAL_DOCUMENT_SCOPE = "__library__"
WORKSPACE_ID_FOREIGN_KEY = "workspaces.id"
CHAT_ID_FOREIGN_KEY = "chats.id"
USER_ID_FOREIGN_KEY = "users.id"
PROJECT_ID_FOREIGN_KEY = "projects.id"
CHAT_MESSAGE_ID_FOREIGN_KEY = "chat_messages.id"
CHAT_NOT_FOUND_ERROR = "Không tìm thấy chat."
SET_NULL = "SET NULL"
LIBRARY_ASSET_ID_FOREIGN_KEY = "library_assets.id"

def utc_now() -> datetime:
    return datetime.now(UTC)


def document_scope_key(project_id: str | None) -> str:
    """Return a stable uniqueness scope for a project or the global Library."""
    return project_id or GLOBAL_DOCUMENT_SCOPE


class Base(DeclarativeBase):
    pass


current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)
current_workspace_id: ContextVar[str | None] = ContextVar("current_workspace_id", default=None)


class UserOwned:
    """Mixin automatically scoped on HTTP requests; internal workers run unscoped."""

    user_id: Mapped[str | None] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    # Data remains attributable to its creator, but visibility is controlled by
    # workspace membership.  Keeping both columns also preserves per-user
    # credentials and scheduled-job ownership.
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey(WORKSPACE_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    role: Mapped[str] = mapped_column(String(24), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey(WORKSPACE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"
    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_workspace_invitation_email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(ForeignKey(WORKSPACE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    invited_by_user_id: Mapped[str] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_subject: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserProviderCredential(Base):
    __tablename__ = "user_provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    ciphertext: Mapped[str] = mapped_column(Text)
    key_version: Mapped[str] = mapped_column(String(32), default="v1")
    key_hint: Mapped[str] = mapped_column(String(8))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ProviderModel(Base):
    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider", "model_id", name="uq_provider_model"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(255))
    lifecycle: Mapped[str] = mapped_column(String(32), default="unknown")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True, index=True)
    subject_user_id: Mapped[str | None] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


@event.listens_for(Session, "do_orm_execute")
def _scope_user_owned_models(execute_state):
    workspace_id = current_workspace_id.get()
    user_id = current_user_id.get()
    if (workspace_id or user_id) and execute_state.is_select and not execute_state.execution_options.get("skip_user_scope"):
        # During the legacy sign-in/claim path there is no workspace yet; retain
        # the former user filter until the personal workspace is provisioned.
        criterion = (lambda cls: cls.workspace_id == workspace_id) if workspace_id else (lambda cls: cls.user_id == user_id)
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(UserOwned, criterion, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _assign_current_user(session, _flush_context, _instances):
    user_id = current_user_id.get()
    workspace_id = current_workspace_id.get()
    if not user_id and not workspace_id:
        return
    for item in session.new:
        if isinstance(item, UserOwned) and item.user_id is None:
            item.user_id = user_id
        if isinstance(item, UserOwned) and item.workspace_id is None:
            item.workspace_id = workspace_id


class Chat(UserOwned, Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160), default="Cuộc trò chuyện mới")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(16), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    context_source_chat_id: Mapped[str | None] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    parent_chat_id: Mapped[str | None] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True, index=True)
    branch_from_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_collections.id", ondelete=SET_NULL), nullable=True, index=True)


class ChatMemoryChunk(UserOwned, Base):
    __tablename__ = "chat_memory_chunks"
    __table_args__ = (UniqueConstraint("chat_id", "fingerprint", "chunk_index", name="uq_chat_memory_chunk"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    forgotten: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChatShare(UserOwned, Base):
    __tablename__ = "chat_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete="CASCADE"), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: token_urlsafe(24))
    title: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(160))
    messages: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMessage(UserOwned, Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_call_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    generated_asset_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResponseFeedback(UserOwned, Base):
    __tablename__ = "response_feedback"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_response_feedback_user_message"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey(CHAT_MESSAGE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class UserPreference(UserOwned, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    style_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    topic_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    theme: Mapped[str] = mapped_column(String(16), default="system")
    custom_instructions: Mapped[str] = mapped_column(Text, default="")
    auto_learn: Mapped[bool] = mapped_column(Boolean, default=True)
    default_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PromptTemplate(UserOwned, Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class MediaAttachment(UserOwned, Base):
    __tablename__ = "media_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    storage_provider: Mapped[str] = mapped_column(String(32), default="local")
    storage_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LibraryAsset(UserOwned, Base):
    __tablename__ = "library_assets"
    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_library_assets_artifact_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    storage_provider: Mapped[str] = mapped_column(String(32), default="local")
    storage_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24), default="upload")
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    artifact_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_project_source: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    index_status: Mapped[str] = mapped_column(String(16), default="pending")
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chunks: Mapped[list["ArtifactChunk"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class ArtifactMessageLink(UserOwned, Base):
    """Connect one immutable artifact version to the chat turn that produced it."""

    __tablename__ = "artifact_message_links"
    __table_args__ = (UniqueConstraint("asset_id", "assistant_message_id", name="uq_artifact_message_link"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset_id: Mapped[str] = mapped_column(ForeignKey(LIBRARY_ASSET_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    chat_id: Mapped[str] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    user_message_id: Mapped[str] = mapped_column(ForeignKey(CHAT_MESSAGE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    assistant_message_id: Mapped[str] = mapped_column(ForeignKey(CHAT_MESSAGE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProjectActivity(UserOwned, Base):
    """An append-only, workspace-visible record of work performed in a Project."""

    __tablename__ = "project_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey(USER_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(500))
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ProjectConnectorScope(UserOwned, Base):
    """Explicit external sources that chats and schedules in a Project may use."""

    __tablename__ = "project_connector_scopes"
    __table_args__ = (UniqueConstraint("project_id", "connector_slug", name="uq_project_connector_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    connector_slug: Mapped[str] = mapped_column(String(80), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ExternalActionProposal(UserOwned, Base):
    """A short-lived confirmation record for a write to an external service."""

    __tablename__ = "external_action_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageRetrievalTrace(UserOwned, Base):
    """The exact retrieval evidence supplied to an assistant response."""

    __tablename__ = "message_retrieval_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey(CHAT_MESSAGE_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ArtifactChunk(UserOwned, Base):
    __tablename__ = "artifact_chunks"
    __table_args__ = (UniqueConstraint("asset_id", "chunk_index", name="uq_artifact_chunks_asset_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset_id: Mapped[str] = mapped_column(ForeignKey(LIBRARY_ASSET_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    asset: Mapped[LibraryAsset] = relationship(back_populates="chunks")


class Project(UserOwned, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_mode: Mapped[str] = mapped_column(String(24), default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Schedule(UserOwned, Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id", ondelete=SET_NULL), nullable=True, index=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey(CHAT_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    require_web_source: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence: Mapped[str] = mapped_column(String(16), default="once")
    status: Mapped[str] = mapped_column(String(16), default="active")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ScheduleRun(UserOwned, Base):
    __tablename__ = "schedule_runs"
    __table_args__ = (UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_runs_schedule_time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    email_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Workflow(UserOwned, Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class WorkflowRun(UserOwned, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("workflow_id", "user_id", "idempotency_key", name="uq_workflow_trigger"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey(LIBRARY_ASSET_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class WorkflowStepRun(UserOwned, Base):
    __tablename__ = "workflow_step_runs"
    __table_args__ = (UniqueConstraint("run_id", "step_id", name="uq_workflow_run_step"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Plugin(UserOwned, Base):
    __tablename__ = "plugins"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_plugins_user_slug"),
        UniqueConstraint("user_id", "catalog_slug", name="uq_plugins_user_catalog_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    catalog_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    connection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ConnectorConnection(UserOwned, Base):
    __tablename__ = "connector_connections"
    __table_args__ = (UniqueConstraint("user_id", "connector_slug", name="uq_connector_connections_user_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connector_slug: Mapped[str] = mapped_column(String(80), index=True)
    encrypted_token: Mapped[str] = mapped_column(Text)
    account_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="connected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class OAuthState(UserOwned, Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    connector_slug: Mapped[str] = mapped_column(String(80), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConnectorAuditLog(UserOwned, Base):
    __tablename__ = "connector_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connector_slug: Mapped[str] = mapped_column(String(80), index=True)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("connector_connections.id", ondelete=SET_NULL), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Document(UserOwned, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("scope_key", "sha256", name="uq_documents_scope_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    storage_provider: Mapped[str] = mapped_column(String(32), default="local")
    storage_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    scope_key: Mapped[str] = mapped_column(String(36), default=GLOBAL_DOCUMENT_SCOPE)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(UserOwned, Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    document: Mapped[Document] = relationship(back_populates="chunks")


class KnowledgeCollection(UserOwned, Base):
    __tablename__ = "knowledge_collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey(PROJECT_ID_FOREIGN_KEY, ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeCollectionDocument(Base):
    __tablename__ = "knowledge_collection_documents"
    __table_args__ = (UniqueConstraint("collection_id", "document_id", name="uq_knowledge_collection_document"),)

    collection_id: Mapped[str] = mapped_column(ForeignKey("knowledge_collections.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)


class BackgroundJob(UserOwned, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index(
            "uq_background_jobs_active_dedupe",
            "type",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
            sqlite_where=text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    type: Mapped[str] = mapped_column(String(48), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class WorkerStatus(Base):
    __tablename__ = "worker_status"

    worker_id: Mapped[str] = mapped_column(String(48), primary_key=True, default="default")
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    current_job_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
