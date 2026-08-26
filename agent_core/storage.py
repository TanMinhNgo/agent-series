"""PostgreSQL persistence for chats and the document knowledge base."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, create_engine, delete, desc, event, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker, with_loader_criteria

GLOBAL_DOCUMENT_SCOPE = "__library__"

def utc_now() -> datetime:
    return datetime.now(UTC)


def document_scope_key(project_id: str | None) -> str:
    """Return a stable uniqueness scope for a project or the global Library."""
    return project_id or GLOBAL_DOCUMENT_SCOPE


class Base(DeclarativeBase):
    pass


current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


class UserOwned:
    """Mixin automatically scoped on HTTP requests; internal workers run unscoped."""

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[str] = mapped_column(String(24), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_subject: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserProviderCredential(Base):
    __tablename__ = "user_provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    subject_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


@event.listens_for(Session, "do_orm_execute")
def _scope_user_owned_models(execute_state):
    user_id = current_user_id.get()
    if user_id and execute_state.is_select and not execute_state.execution_options.get("skip_user_scope"):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(UserOwned, lambda cls: cls.user_id == user_id, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _assign_current_user(session, _flush_context, _instances):
    user_id = current_user_id.get()
    if not user_id:
        return
    for item in session.new:
        if isinstance(item, UserOwned) and item.user_id is None:
            item.user_id = user_id


class Chat(UserOwned, Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160), default="Cuộc trò chuyện mới")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    context_source_chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True)
    branch_from_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_collections.id", ondelete="SET NULL"), nullable=True, index=True)


class ChatMemoryChunk(UserOwned, Base):
    __tablename__ = "chat_memory_chunks"
    __table_args__ = (UniqueConstraint("chat_id", "fingerprint", "chunk_index", name="uq_chat_memory_chunk"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
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
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), unique=True, index=True)
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
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_call_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResponseFeedback(UserOwned, Base):
    __tablename__ = "response_feedback"
    __table_args__ = (UniqueConstraint("user_id", "message_id", name="uq_response_feedback_user_message"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PromptTemplate(UserOwned, Base):
    __tablename__ = "prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class MediaAttachment(UserOwned, Base):
    __tablename__ = "media_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LibraryAsset(UserOwned, Base):
    __tablename__ = "library_assets"
    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_library_assets_artifact_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24), default="upload")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    artifact_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_project_source: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    index_status: Mapped[str] = mapped_column(String(16), default="pending")
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    chunks: Mapped[list["ArtifactChunk"]] = relationship(back_populates="asset", cascade="all, delete-orphan")


class ArtifactChunk(UserOwned, Base):
    __tablename__ = "artifact_chunks"
    __table_args__ = (UniqueConstraint("asset_id", "chunk_index", name="uq_artifact_chunks_asset_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset_id: Mapped[str] = mapped_column(ForeignKey("library_assets.id", ondelete="CASCADE"), index=True)
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
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
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
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("connector_connections.id", ondelete="SET NULL"), nullable=True, index=True)
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
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    scope_key: Mapped[str] = mapped_column(String(36), default=GLOBAL_DOCUMENT_SCOPE)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
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
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
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


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.session_factory()


class ModelRegistryRepository:
    def __init__(self, database: Database): self.database = database
    def seed(self, models: dict[str, tuple[str, ...]]) -> None:
        with self.database.session() as s:
            for provider, items in models.items():
                for model in items:
                    if not s.scalar(select(ProviderModel).where(ProviderModel.provider == provider, ProviderModel.model_id == model)):
                        s.add(ProviderModel(provider=provider, model_id=model, display_name=model, approved=True, is_active=True))
            s.commit()
    def list(self) -> list[ProviderModel]:
        with self.database.session() as s: return list(s.scalars(select(ProviderModel).order_by(ProviderModel.provider, ProviderModel.model_id)))
    def active(self) -> dict[str, tuple[str, ...]]:
        with self.database.session() as s:
            rows = s.scalars(select(ProviderModel).where(ProviderModel.is_active.is_(True))).all(); result: dict[str, list[str]] = {}
            for row in rows: result.setdefault(row.provider, []).append(row.model_id)
            return {key: tuple(value) for key, value in result.items()}
    def set_active(self, provider: str, model_id: str, is_active: bool) -> ProviderModel | None:
        with self.database.session() as s:
            item = s.scalar(select(ProviderModel).where(ProviderModel.provider == provider, ProviderModel.model_id == model_id))
            if item is None:
                return None
            item.is_active = is_active
            s.commit()
            s.refresh(item)
            return item
    def setting(self, key: str) -> str | None:
        with self.database.session() as s: item = s.get(SystemSetting, key); return item.value if item else None
    def set_setting(self, key: str, value: str) -> None:
        with self.database.session() as s:
            item = s.get(SystemSetting, key)
            if item: item.value = value
            else: s.add(SystemSetting(key=key, value=value))
            s.commit()


class ChatRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, provider: str, model: str, context_source_chat_id: str | None = None, project_id: str | None = None, collection_id: str | None = None) -> Chat:
        with self.database.session() as session:
            chat = Chat(provider=provider, model=model, context_source_chat_id=context_source_chat_id, project_id=project_id, collection_id=collection_id)
            session.add(chat)
            session.commit()
            return chat

    def create_branch(self, chat_id: str, assistant_message_id: str) -> Chat:
        """Copy only the selected assistant turn and the user turn immediately before it."""
        with self.database.session() as session:
            parent = session.get(Chat, chat_id)
            if parent is None:
                raise ValueError("Không tìm thấy chat.")
            assistant = session.get(ChatMessage, assistant_message_id)
            if assistant is None or assistant.chat_id != chat_id or assistant.role != "assistant":
                raise ValueError("Chỉ có thể mở nhánh từ phản hồi AI thuộc chat này.")
            user = session.scalar(
                select(ChatMessage)
                .where(
                    ChatMessage.chat_id == chat_id,
                    ChatMessage.role == "user",
                    ChatMessage.position < assistant.position,
                )
                .order_by(ChatMessage.position.desc())
                .limit(1)
            )
            if user is None:
                raise ValueError("Không tìm thấy câu hỏi đứng trước phản hồi này.")
            branch = Chat(
                title=user.content.strip()[:80] or "Nhánh hội thoại",
                provider=parent.provider,
                model=parent.model,
                project_id=parent.project_id,
                collection_id=parent.collection_id,
                parent_chat_id=parent.id,
                branch_from_position=assistant.position,
            )
            session.add(branch)
            session.flush()
            for position, source in enumerate((user, assistant)):
                session.add(
                    ChatMessage(
                        chat_id=branch.id,
                        position=position,
                        role=source.role,
                        content=source.content,
                        attachments=source.attachments if source.role == "user" else None,
                        content_blocks=source.content_blocks if source.role == "assistant" else None,
                        sources=source.sources if source.role == "assistant" else None,
                    )
                )
            session.commit()
            return branch

    def prepare_regeneration(self, chat_id: str, assistant_message_id: str) -> str:
        """Remove the latest exchange so streaming can recreate it without duplicate turns."""
        with self.database.session() as session:
            assistant = session.get(ChatMessage, assistant_message_id)
            if assistant is None or assistant.chat_id != chat_id or assistant.role != "assistant":
                raise ValueError("Không tìm thấy phản hồi AI cần tạo lại.")
            latest_position = session.scalar(
                select(func.max(ChatMessage.position)).where(ChatMessage.chat_id == chat_id)
            )
            if latest_position != assistant.position:
                raise ValueError("Chỉ có thể tạo lại phản hồi AI mới nhất.")
            user = session.scalar(
                select(ChatMessage)
                .where(
                    ChatMessage.chat_id == chat_id,
                    ChatMessage.role == "user",
                    ChatMessage.position < assistant.position,
                )
                .order_by(ChatMessage.position.desc())
                .limit(1)
            )
            if user is None:
                raise ValueError("Không tìm thấy câu hỏi đứng trước phản hồi này.")
            content = user.content
            session.execute(delete(ChatMessage).where(ChatMessage.chat_id == chat_id, ChatMessage.position >= user.position))
            session.commit()
            return content

    def set_message_pin(self, message_id: str, pinned: bool) -> ChatMessage | None:
        with self.database.session() as session:
            message = session.get(ChatMessage, message_id)
            if message is None or message.role != "user":
                return None
            message.pinned = pinned
            session.commit()
            return message

    def chat_pins(self, chat_id: str) -> list[ChatMessage]:
        with self.database.session() as session:
            return list(session.scalars(select(ChatMessage).where(
                ChatMessage.chat_id == chat_id,
                ChatMessage.role == "user",
                ChatMessage.pinned.is_(True),
            ).order_by(ChatMessage.position)).all())

    def list(self, offset: int = 0, limit: int = 40) -> tuple[list[Chat], int]:
        with self.database.session() as session:
            total = session.scalar(select(func.count()).select_from(Chat)) or 0
            chats = session.scalars(
                select(Chat)
                .order_by(desc(Chat.pinned), desc(Chat.updated_at))
                .offset(offset)
                .limit(limit)
            )
            return list(chats), total

    def get(self, chat_id: str) -> Chat | None:
        with self.database.session() as session:
            return session.get(Chat, chat_id)

    def replace_history(self, chat_id: str, history: list[dict]) -> None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                raise ValueError("Không tìm thấy chat.")
            session.execute(delete(ChatMessage).where(ChatMessage.chat_id == chat_id))
            for position, item in enumerate(history):
                raw_created_at = item.get("created_at")
                created_at = (
                    raw_created_at
                    if isinstance(raw_created_at, datetime)
                    else datetime.fromisoformat(raw_created_at)
                    if isinstance(raw_created_at, str)
                    else utc_now()
                )
                session.add(ChatMessage(
                    chat_id=chat_id, position=position, role=item["role"], content=item.get("content", ""),
                    tool_call_id=item.get("id"), tool_name=item.get("name"),
                    tool_calls=item.get("tool_calls"),
                    attachments=[{key: value for key, value in attachment.items() if key != "data"}
                                 for attachment in item.get("attachments", [])] or None,
                    content_blocks=item.get("content_blocks") or None,
                    sources=item.get("sources") or None,
                    created_at=created_at,
                ))
            user_message = next((item["content"] for item in history if item["role"] == "user"), "")
            if chat.title == "Cuộc trò chuyện mới" and user_message:
                chat.title = user_message.strip()[:80]
            chat.updated_at = utc_now()
            session.commit()

    def set_unread(self, chat_id: str, unread: bool) -> Chat | None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            chat.is_unread = unread
            session.commit()
            return chat

    def update_model(self, chat_id: str, provider: str, model: str) -> None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                raise ValueError("Không tìm thấy chat.")
            chat.provider = provider
            chat.model = model
            chat.updated_at = utc_now()
            session.commit()

    def update(self, chat_id: str, **values) -> Chat | None:
        allowed = {"title", "pinned", "archived", "provider", "model", "project_id", "collection_id"}
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            for key, value in values.items():
                # project_id must be nullable so a chat can be moved back to
                # the global workspace; all other optional values retain their
                # existing "not supplied" behavior.
                if key in allowed and (key in {"project_id", "collection_id"} or value is not None):
                    setattr(chat, key, value)
            chat.updated_at = utc_now()
            session.commit()
            return chat

    def delete(self, chat_id: str) -> bool:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return False
            session.delete(chat)
            session.commit()
            return True

    def create_or_update_share(self, chat_id: str, expires_at: datetime | None = None) -> ChatShare | None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            records = session.scalars(
                select(ChatMessage).where(ChatMessage.chat_id == chat_id).order_by(ChatMessage.position)
            ).all()
            messages = [
                {key: value for key, value in {
                    "role": item.role,
                    "content": item.content,
                    "contentBlocks": item.content_blocks or [],
                }.items() if value not in (None, [])}
                for item in records if item.role in {"user", "assistant"}
            ]
            share = session.scalar(select(ChatShare).where(ChatShare.chat_id == chat_id))
            if share is None:
                share = ChatShare(chat_id=chat.id, title=chat.title, provider=chat.provider, model=chat.model, messages=messages, expires_at=expires_at)
                session.add(share)
            else:
                share.title, share.provider, share.model, share.messages, share.expires_at = chat.title, chat.provider, chat.model, messages, expires_at
                share.token = token_urlsafe(24)
                share.updated_at = utc_now()
            session.commit()
            return share

    def get_share(self, token: str) -> ChatShare | None:
        with self.database.session() as session:
            return session.scalar(select(ChatShare).where(ChatShare.token == token))

    def revoke_share(self, chat_id: str) -> bool:
        with self.database.session() as session:
            share = session.scalar(select(ChatShare).where(ChatShare.chat_id == chat_id))
            if share is None:
                return False
            session.delete(share)
            session.commit()
            return True

    def history(self, chat_id: str) -> list[dict]:
        # Query messages directly while the Session is open.  A Chat returned by
        # ``get()`` is detached after the context manager exits, so accessing its
        # lazy ``messages`` relationship there raises DetachedInstanceError.
        with self.database.session() as session:
            messages = session.scalars(
                select(ChatMessage)
                .where(ChatMessage.chat_id == chat_id)
                .order_by(ChatMessage.position)
            ).all()
            return [
                {key: value for key, value in {
                    "message_id": message.id,
                    "position": message.position,
                    "role": message.role, "content": message.content, "id": message.tool_call_id,
                    "name": message.tool_name, "tool_calls": message.tool_calls,
                    "attachments": message.attachments,
                    "content_blocks": message.content_blocks,
                    "sources": message.sources,
                    "pinned": message.pinned,
                    "created_at": message.created_at.isoformat(),
                }.items() if value is not None}
                for message in messages
            ]


class WorkspaceRepository:
    def __init__(self, database: Database):
        self.database = database

    def list(self, entity):
        with self.database.session() as session:
            return list(session.scalars(select(entity).order_by(entity.updated_at.desc())))

    def list_plugins(self) -> list[Plugin]:
        return self.list(Plugin)

    def get(self, entity, item_id: str):
        with self.database.session() as session:
            return session.get(entity, item_id)

    def get_plugin_by_catalog_slug(self, catalog_slug: str) -> Plugin | None:
        with self.database.session() as session:
            return session.scalar(select(Plugin).where(Plugin.catalog_slug == catalog_slug))

    def catalog_plugin_ids(self) -> dict[str, str]:
        with self.database.session() as session:
            rows = session.scalars(select(Plugin).where(Plugin.catalog_slug.is_not(None))).all()
            return {item.catalog_slug: item.id for item in rows if item.catalog_slug}

    def create(self, entity, **values):
        with self.database.session() as session:
            item = entity(**values)
            session.add(item)
            session.commit()
            return item

    def update(self, entity, item_id: str, **values):
        with self.database.session() as session:
            item = session.get(entity, item_id)
            if item is None:
                return None
            for key, value in values.items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            session.commit()
            return item

    def delete(self, entity, item_id: str) -> bool:
        with self.database.session() as session:
            item = session.get(entity, item_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True


class ConnectorRepository:
    """Persistence for OAuth connections, short-lived CSRF state, and audit metadata."""

    def __init__(self, database: Database):
        self.database = database

    def get_connection(self, connector_slug: str) -> ConnectorConnection | None:
        with self.database.session() as session:
            return session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))

    def save_connection(self, connector_slug: str, encrypted_token: str, account_email: str | None, scopes: list[str], expires_at: datetime | None, status: str = "connected") -> ConnectorConnection:
        with self.database.session() as session:
            item = session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))
            if item is None:
                item = ConnectorConnection(connector_slug=connector_slug, encrypted_token=encrypted_token, account_email=account_email, scopes=scopes, expires_at=expires_at, status=status)
                session.add(item)
            else:
                item.encrypted_token = encrypted_token
                item.account_email = account_email
                item.scopes = scopes
                item.expires_at = expires_at
                item.status = status
                item.updated_at = utc_now()
            session.commit()
            return item

    def set_connection_status(self, connector_slug: str, status: str) -> ConnectorConnection | None:
        with self.database.session() as session:
            item = session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))
            if item is None:
                return None
            item.status = status
            item.updated_at = utc_now()
            session.commit()
            return item

    def delete_connection(self, connector_slug: str) -> bool:
        with self.database.session() as session:
            item = session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def create_oauth_state(self, state: str, connector_slug: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(OAuthState(state=state, connector_slug=connector_slug, expires_at=expires_at))
            session.commit()

    def consume_oauth_state(self, state: str, now: datetime) -> OAuthState | None:
        with self.database.session() as session:
            item = session.get(OAuthState, state)
            if item is None:
                return None
            session.delete(item)
            session.commit()
            return item if item.expires_at > now else None

    def audit(self, connector_slug: str, event_type: str, connection_id: str | None = None, tool_name: str | None = None, summary: str | None = None) -> ConnectorAuditLog:
        with self.database.session() as session:
            item = ConnectorAuditLog(connector_slug=connector_slug, connection_id=connection_id, event_type=event_type, tool_name=tool_name, summary=summary)
            session.add(item)
            session.commit()
            return item

    def list_audit(self, connector_slug: str, limit: int = 20) -> list[ConnectorAuditLog]:
        with self.database.session() as session:
            return list(session.scalars(select(ConnectorAuditLog).where(ConnectorAuditLog.connector_slug == connector_slug).order_by(desc(ConnectorAuditLog.created_at)).limit(limit)))

    def list_connection_metadata(
        self,
        offset: int,
        limit: int,
        query: str | None = None,
        connector_slug: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """Return admin-safe connection metadata without ever selecting token material."""
        filters = []
        if query:
            term = f"%{query.strip()}%"
            filters.append(or_(User.email.ilike(term), ConnectorConnection.connector_slug.ilike(term)))
        if connector_slug:
            filters.append(ConnectorConnection.connector_slug == connector_slug)
        if status:
            filters.append(ConnectorConnection.status == status)
        statement = (
            select(
                ConnectorConnection.id.label("id"),
                ConnectorConnection.connector_slug.label("connector_slug"),
                ConnectorConnection.status.label("status"),
                ConnectorConnection.scopes.label("scopes"),
                ConnectorConnection.expires_at.label("expires_at"),
                ConnectorConnection.created_at.label("created_at"),
                ConnectorConnection.updated_at.label("updated_at"),
                User.id.label("user_id"),
                User.email.label("user_email"),
            )
            .join(User, User.id == ConnectorConnection.user_id)
            .where(*filters)
            .order_by(desc(ConnectorConnection.updated_at))
            .offset(offset)
            .limit(limit)
            .execution_options(skip_user_scope=True)
        )
        count_statement = (
            select(func.count())
            .select_from(ConnectorConnection)
            .join(User, User.id == ConnectorConnection.user_id)
            .where(*filters)
            .execution_options(skip_user_scope=True)
        )
        with self.database.session() as session:
            rows = [dict(row._mapping) for row in session.execute(statement).all()]
            return rows, int(session.scalar(count_statement) or 0)


class AuthRepository:
    def __init__(self, database: Database):
        self.database = database

    def user_count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(User).execution_options(skip_user_scope=True)) or 0)

    def get_user(self, user_id: str) -> User | None:
        with self.database.session() as session:
            return session.get(User, user_id, execution_options={"skip_user_scope": True})

    def get_user_by_email(self, email: str) -> User | None:
        with self.database.session() as session:
            return session.scalar(select(User).where(User.email == email).execution_options(skip_user_scope=True))

    def create_user(self, email: str, display_name: str | None = None, role: str = "member") -> User:
        with self.database.session() as session:
            item = User(email=email, display_name=display_name, role=role)
            session.add(item); session.commit(); return item

    def list_users(self, query: str | None, offset: int, limit: int) -> tuple[list[tuple[User, datetime | None]], int]:
        with self.database.session() as session:
            last_sign_in = select(AuthSession.user_id.label("user_id"), func.max(AuthSession.created_at).label("last_sign_in_at")).group_by(AuthSession.user_id).subquery()
            statement = select(User, last_sign_in.c.last_sign_in_at).outerjoin(last_sign_in, last_sign_in.c.user_id == User.id).execution_options(skip_user_scope=True)
            if query:
                statement = statement.where(User.email.ilike(f"%{query.strip()}%"))
            total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = list(session.execute(statement.order_by(desc(User.created_at)).offset(offset).limit(limit)).all())
            return rows, total

    def set_user_active(self, user_id: str, active: bool) -> User | None:
        with self.database.session() as session:
            user = session.get(User, user_id, execution_options={"skip_user_scope": True})
            if user is None:
                return None
            user.is_active = active
            if not active:
                session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
            session.commit()
            return user

    def provider_credential_metadata(self, offset: int, limit: int) -> tuple[list[tuple[UserProviderCredential, User]], int]:
        with self.database.session() as session:
            statement = select(UserProviderCredential, User).join(User, User.id == UserProviderCredential.user_id).execution_options(skip_user_scope=True)
            total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = list(session.execute(statement.order_by(desc(UserProviderCredential.updated_at)).offset(offset).limit(limit)).all())
            return rows, total

    def user_provider_credentials(self, user_id: str) -> list[UserProviderCredential]:
        with self.database.session() as session:
            return list(session.scalars(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id).order_by(UserProviderCredential.provider)))

    def user_provider_credential(self, user_id: str, provider: str) -> UserProviderCredential | None:
        with self.database.session() as session:
            return session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))

    def save_user_provider_credential(self, user_id: str, provider: str, ciphertext: str, key_hint: str) -> UserProviderCredential:
        with self.database.session() as session:
            item = session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))
            if item is None:
                item = UserProviderCredential(user_id=user_id, provider=provider, ciphertext=ciphertext, key_hint=key_hint)
                session.add(item)
            else:
                item.ciphertext, item.key_hint, item.validated_at, item.updated_at = ciphertext, key_hint, utc_now(), utc_now()
            session.commit()
            return item

    def delete_user_provider_credential(self, user_id: str, provider: str) -> bool:
        with self.database.session() as session:
            item = session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def add_system_audit(self, event_type: str, actor_user_id: str | None = None, subject_user_id: str | None = None, summary: str | None = None, metadata_json: dict | None = None) -> SystemAuditLog:
        with self.database.session() as session:
            item = SystemAuditLog(actor_user_id=actor_user_id, subject_user_id=subject_user_id, event_type=event_type, summary=summary, metadata_json=metadata_json)
            session.add(item); session.commit(); return item

    def list_system_audit(self, offset: int, limit: int) -> tuple[list[SystemAuditLog], int]:
        with self.database.session() as session:
            statement = select(SystemAuditLog).execution_options(skip_user_scope=True)
            total = int(session.scalar(select(func.count()).select_from(SystemAuditLog).execution_options(skip_user_scope=True)) or 0)
            return list(session.scalars(statement.order_by(desc(SystemAuditLog.created_at)).offset(offset).limit(limit))), total

    def system_counts(self) -> dict[str, int]:
        with self.database.session() as session:
            return {
                "users": int(session.scalar(select(func.count()).select_from(User).execution_options(skip_user_scope=True)) or 0),
                "activeUsers": int(session.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)).execution_options(skip_user_scope=True)) or 0),
                "chats": int(session.scalar(select(func.count()).select_from(Chat).execution_options(skip_user_scope=True)) or 0),
                "projects": int(session.scalar(select(func.count()).select_from(Project).execution_options(skip_user_scope=True)) or 0),
                "documents": int(session.scalar(select(func.count()).select_from(Document).execution_options(skip_user_scope=True)) or 0),
            }

    def get_user_for_identity(self, provider: str, subject: str) -> User | None:
        with self.database.session() as session:
            row = session.execute(
                select(User).join(AuthIdentity, AuthIdentity.user_id == User.id).where(
                    AuthIdentity.provider == provider,
                    AuthIdentity.provider_subject == subject,
                ).execution_options(skip_user_scope=True)
            ).first()
            return row[0] if row else None

    def link_or_get_identity(self, user_id: str, provider: str, subject: str) -> User:
        with self.database.session() as session:
            identity = session.scalar(select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_subject == subject,
            ).with_for_update().execution_options(skip_user_scope=True))
            if identity is None:
                session.add(AuthIdentity(user_id=user_id, provider=provider, provider_subject=subject))
                session.commit()
                return session.get(User, user_id, execution_options={"skip_user_scope": True})
            return session.get(User, identity.user_id, execution_options={"skip_user_scope": True})

    def create_auth_oauth_state(self, state: str, purpose: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(OAuthState(state=state, connector_slug=purpose, expires_at=expires_at)); session.commit()

    def consume_auth_oauth_state(self, state: str, now: datetime) -> str | None:
        with self.database.session() as session:
            item = session.get(OAuthState, state, execution_options={"skip_user_scope": True})
            if item is None:
                return None
            session.delete(item); session.commit()
            return item.connector_slug if item.expires_at > now else None

    def create_session(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(AuthSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at)); session.commit()

    def user_for_session(self, token_hash: str, now: datetime) -> User | None:
        with self.database.session() as session:
            row = session.execute(
                select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.token_hash == token_hash, AuthSession.expires_at > now).execution_options(skip_user_scope=True)
            ).first()
            return row[1] if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self.database.session() as session:
            session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash)); session.commit()

    def claim_legacy_data(self, user_id: str) -> None:
        entities = (Chat, ChatMemoryChunk, ChatShare, ChatMessage, ResponseFeedback, UserPreference, PromptTemplate, MediaAttachment, LibraryAsset, ArtifactChunk, Project, Schedule, ScheduleRun, Plugin, ConnectorConnection, OAuthState, ConnectorAuditLog, Document, DocumentChunk, KnowledgeCollection, BackgroundJob)
        with self.database.session() as session:
            for entity in entities:
                session.execute(entity.__table__.update().where(entity.user_id.is_(None)).values(user_id=user_id))
            session.commit()


class ScheduleRepository:
    """Coordinate persisted schedule runs so multiple workers cannot run one job twice."""

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def next_run_after(schedule: Schedule, now: datetime) -> datetime | None:
        if schedule.recurrence == "once":
            return None
        interval = timedelta(days=1 if schedule.recurrence == "daily" else 7)
        candidate = schedule.next_run_at or now
        while candidate <= now:
            candidate += interval
        return candidate

    def claim_due(self, now: datetime) -> list[tuple[Schedule, ScheduleRun]]:
        claimed: list[tuple[Schedule, ScheduleRun]] = []
        with self.database.session() as session:
            schedules = session.scalars(
                select(Schedule)
                .where(Schedule.status == "active", Schedule.next_run_at.is_not(None), Schedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
            for schedule in schedules:
                scheduled_for = schedule.next_run_at
                if scheduled_for is None:
                    continue
                already_ran = session.scalar(
                    select(ScheduleRun.id)
                    .where(ScheduleRun.schedule_id == schedule.id, ScheduleRun.scheduled_for == scheduled_for)
                    .limit(1)
                )
                if already_ran is not None:
                    # This slot already has a run: editing a schedule rewinds
                    # `next_run_at` to `starts_at`, which can land on a past slot.
                    # Roll forward instead of inserting a duplicate, whose unique
                    # violation would abort the whole batch and stall the worker.
                    schedule.next_run_at = self.next_run_after(schedule, now)
                    if schedule.next_run_at is None:
                        schedule.status = "completed"
                    schedule.updated_at = now
                    continue
                run = ScheduleRun(
                    schedule_id=schedule.id,
                    scheduled_for=scheduled_for,
                    status="running",
                    started_at=now,
                    heartbeat_at=now,
                    user_id=schedule.user_id,
                )
                session.add(run)
                schedule.last_run_at = now
                schedule.next_run_at = self.next_run_after(schedule, now)
                if schedule.next_run_at is None:
                    schedule.status = "completed"
                schedule.updated_at = now
                claimed.append((schedule, run))
            session.commit()
            return claimed

    def claim_due_retries(self, now: datetime) -> list[tuple[Schedule, ScheduleRun]]:
        """Claim delayed provider retries without creating another schedule run."""
        with self.database.session() as session:
            rows = session.execute(
                select(Schedule, ScheduleRun)
                .join(ScheduleRun, ScheduleRun.schedule_id == Schedule.id)
                .where(ScheduleRun.status == "retrying", ScheduleRun.retry_at.is_not(None), ScheduleRun.retry_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[tuple[Schedule, ScheduleRun]] = []
            for schedule, run in rows:
                # `started_at` still points at the first attempt, so the heartbeat
                # must be refreshed or recovery would reclaim this retry at once.
                run.status, run.retry_at, run.heartbeat_at = "running", None, now
                claimed.append((schedule, run))
            session.commit()
            return claimed

    def claim_manual(self, schedule_id: str, now: datetime) -> tuple[Schedule, ScheduleRun] | None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id, with_for_update=True)
            if schedule is None:
                return None
            running = session.scalar(
                select(ScheduleRun.id)
                .where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.status == "running")
                .limit(1)
            )
            if running is not None:
                raise ValueError("Lịch trình đang chạy. Hãy chờ lần chạy hiện tại hoàn tất.")
            pending_retries = session.scalars(
                select(ScheduleRun)
                .where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.status == "retrying")
                .with_for_update()
            ).all()
            for pending in pending_retries:
                pending.status = "cancelled"
                pending.retry_at = None
                pending.error = "Đã thay bằng lần chạy thủ công."
                pending.finished_at = now
            run = ScheduleRun(
                schedule_id=schedule.id,
                scheduled_for=now,
                status="running",
                started_at=now,
                heartbeat_at=now,
                user_id=schedule.user_id,
            )
            session.add(run)
            schedule.last_run_at, schedule.updated_at = now, now
            session.commit()
            return schedule, run

    def schedule_retry(self, run_id: str, error: str, delays: tuple[int, ...], now: datetime | None = None) -> tuple[datetime, int] | None:
        """Queue one durable retry, returning its due time and retry number."""
        current_time = now or utc_now()
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id, with_for_update=True)
            if run is None or run.retry_count >= len(delays):
                return None
            retry_at = current_time + timedelta(minutes=delays[run.retry_count])
            run.retry_count += 1
            run.status, run.retry_at, run.error, run.finished_at = "retrying", retry_at, error, None
            session.commit()
            return retry_at, run.retry_count

    def finish(self, run_id: str, *, summary: str | None = None, error: str | None = None) -> ScheduleRun | None:
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None:
                return None
            run.status = "failed" if error else "succeeded"
            run.summary, run.error, run.retry_at, run.finished_at = summary, error, None, utc_now()
            session.commit()
            return run

    def get_run(self, schedule_id: str, run_id: str) -> ScheduleRun | None:
        with self.database.session() as session:
            return session.scalar(select(ScheduleRun).where(ScheduleRun.id == run_id, ScheduleRun.schedule_id == schedule_id))

    def record_email(self, run_id: str, *, status: str, error: str | None = None) -> ScheduleRun | None:
        """Track notification delivery without touching the AI run outcome."""
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None:
                return None
            run.email_status, run.email_error = status, error
            run.email_sent_at = utc_now() if status == "sent" else None
            session.commit()
            return run

    def recover_stale_runs(self, now: datetime, timeout: timedelta = timedelta(minutes=20)) -> int:
        with self.database.session() as session:
            stale = session.scalars(
                select(ScheduleRun).where(
                    ScheduleRun.status == "running",
                    # A slow run still reporting a heartbeat is alive, not stale.
                    # Only silence since the last beat (or the start, for runs
                    # predating heartbeats) means the worker really died.
                    func.coalesce(ScheduleRun.heartbeat_at, ScheduleRun.started_at) < now - timeout,
                )
            ).all()
            for run in stale:
                run.status, run.error, run.finished_at = "failed", "Worker timeout; hãy chạy lại thủ công.", now
            session.commit()
            return len(stale)

    def touch_run(self, run_id: str, now: datetime | None = None) -> bool:
        """Report that this run's worker is still alive; False once it is not ours."""
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None or run.status != "running":
                return False
            run.heartbeat_at = now or utc_now()
            session.commit()
            return True

    def list_runs(self, schedule_id: str, limit: int = 30) -> list[ScheduleRun]:
        with self.database.session() as session:
            return list(session.scalars(select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id).order_by(ScheduleRun.started_at.desc()).limit(limit)))

    def attach_chat(self, schedule_id: str, chat_id: str) -> None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id)
            if schedule is not None:
                schedule.chat_id, schedule.updated_at = chat_id, utc_now()
                session.commit()


class BackgroundJobRepository:
    def __init__(self, database: Database):
        self.database = database

    def enqueue(self, type: str, payload: dict, max_attempts: int = 3, dedupe_key: str | None = None) -> BackgroundJob:
        with self.database.session() as session:
            job = BackgroundJob(type=type, payload=payload, max_attempts=max_attempts, dedupe_key=dedupe_key)
            session.add(job)
            session.commit()
            return job

    def enqueue_unique(self, type: str, payload: dict, dedupe_key: str, max_attempts: int = 3) -> tuple[BackgroundJob, bool]:
        """Return an active equivalent job, or atomically create one."""
        with self.database.session() as session:
            active = session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.type == type, BackgroundJob.dedupe_key == dedupe_key, BackgroundJob.status.in_(("queued", "running")))
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )
            if active is not None:
                return active, False
            job = BackgroundJob(type=type, payload=payload, max_attempts=max_attempts, dedupe_key=dedupe_key)
            session.add(job)
            try:
                session.commit()
                return job, True
            except IntegrityError:
                session.rollback()
                active = session.scalar(
                    select(BackgroundJob)
                    .where(BackgroundJob.type == type, BackgroundJob.dedupe_key == dedupe_key, BackgroundJob.status.in_(("queued", "running")))
                    .order_by(BackgroundJob.created_at.desc())
                    .limit(1)
                )
                if active is None:
                    raise
                return active, False

    def latest_for_document(self, document_id: str) -> BackgroundJob | None:
        with self.database.session() as session:
            return session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.type == "document_index", BackgroundJob.dedupe_key == f"document:{document_id}")
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )

    def claim(self, now: datetime) -> BackgroundJob | None:
        with self.database.session() as session:
            job = session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.status == "queued", BackgroundJob.run_after <= now)
                .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
            session.commit()
            return job

    def succeed(self, job_id: str) -> None:
        with self.database.session() as session:
            job = session.get(BackgroundJob, job_id)
            if job and job.status == "running":
                job.status, job.locked_at, job.last_error = "succeeded", None, None
                session.commit()

    def fail(self, job_id: str, error: str, now: datetime) -> None:
        with self.database.session() as session:
            job = session.get(BackgroundJob, job_id)
            if job is None or job.status != "running":
                return
            job.last_error, job.locked_at = error[:10_000], None
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status, job.run_after = "queued", now + timedelta(seconds=2 ** job.attempts)
            session.commit()

    def cancel_document_jobs(self, document_ids: list[str]) -> int:
        """Stop queued/running index jobs for documents removed by a Project deletion."""
        if not document_ids:
            return 0
        keys = [f"document:{document_id}" for document_id in document_ids]
        with self.database.session() as session:
            jobs = session.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.type == "document_index",
                    BackgroundJob.dedupe_key.in_(keys),
                    BackgroundJob.status.in_(("queued", "running")),
                )
            ).all()
            for job in jobs:
                job.status, job.locked_at, job.last_error = "cancelled", None, "Tài liệu đã bị xóa."
            session.commit()
            return len(jobs)

    def recover_stale(self, now: datetime, timeout: timedelta = timedelta(minutes=20)) -> int:
        with self.database.session() as session:
            jobs = session.scalars(
                select(BackgroundJob).where(BackgroundJob.status == "running", BackgroundJob.locked_at < now - timeout)
            ).all()
            for job in jobs:
                job.status, job.locked_at, job.run_after = "queued", None, now
                job.last_error = "Worker stopped before finishing; queued again."
            session.commit()
            return len(jobs)

    def heartbeat(self, now: datetime, current_job_type: str | None = None, last_error: str | None = None) -> None:
        with self.database.session() as session:
            state = session.get(WorkerStatus, "default")
            if state is None:
                state = WorkerStatus(worker_id="default")
                session.add(state)
            state.last_heartbeat_at = now
            state.current_job_type = current_job_type
            if last_error:
                state.last_error = last_error[:10_000]
            session.commit()

    def worker_status(self, now: datetime) -> dict:
        with self.database.session() as session:
            state = session.get(WorkerStatus, "default")
            counts = dict(session.execute(select(BackgroundJob.status, func.count()).group_by(BackgroundJob.status)).all())
            last_failed = session.scalar(
                select(BackgroundJob).where(BackgroundJob.status == "failed").order_by(BackgroundJob.updated_at.desc()).limit(1)
            )
            heartbeat = state.last_heartbeat_at if state else None
            if heartbeat is not None and heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=now.tzinfo)
            return {
                "online": bool(heartbeat and heartbeat >= now - timedelta(seconds=15)),
                "lastHeartbeatAt": heartbeat.isoformat() if heartbeat else None,
                "currentJobType": state.current_job_type if state else None,
                "queued": counts.get("queued", 0),
                "running": counts.get("running", 0),
                "failed": counts.get("failed", 0),
                "lastError": (state.last_error if state and state.last_error else (last_failed.last_error if last_failed else None)),
            }


class MediaRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, **values) -> MediaAttachment:
        with self.database.session() as session:
            item = MediaAttachment(**values)
            session.add(item)
            session.commit()
            return item

    def get_many(self, ids: list[str]) -> list[MediaAttachment]:
        with self.database.session() as session:
            return list(session.scalars(select(MediaAttachment).where(MediaAttachment.id.in_(ids))))
