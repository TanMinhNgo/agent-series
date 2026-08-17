"""PostgreSQL persistence for chats and the document knowledge base."""

from __future__ import annotations

from datetime import datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, create_engine, delete, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160), default="Cuộc trò chuyện mới")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    context_source_chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)


class ChatMemoryChunk(Base):
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ChatShare(Base):
    __tablename__ = "chat_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=lambda: token_urlsafe(24))
    title: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(160))
    messages: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
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


class MediaAttachment(Base):
    __tablename__ = "media_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class LibraryAsset(Base):
    __tablename__ = "library_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24), default="upload")
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_mode: Mapped[str] = mapped_column(String(24), default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(160))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence: Mapped[str] = mapped_column(String(16), default="once")
    status: Mapped[str] = mapped_column(String(16), default="active")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduleRun(Base):
    __tablename__ = "schedule_runs"
    __table_args__ = (UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_runs_schedule_time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    catalog_slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    connection_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    document: Mapped[Document] = relationship(back_populates="chunks")


class BackgroundJob(Base):
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
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkerStatus(Base):
    __tablename__ = "worker_status"

    worker_id: Mapped[str] = mapped_column(String(48), primary_key=True, default="default")
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    current_job_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.session_factory()


class ChatRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, provider: str, model: str, context_source_chat_id: str | None = None, project_id: str | None = None) -> Chat:
        with self.database.session() as session:
            chat = Chat(provider=provider, model=model, context_source_chat_id=context_source_chat_id, project_id=project_id)
            session.add(chat)
            session.commit()
            return chat

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
                session.add(ChatMessage(
                    chat_id=chat_id, position=position, role=item["role"], content=item.get("content", ""),
                    tool_call_id=item.get("id"), tool_name=item.get("name"),
                    tool_calls=item.get("tool_calls"),
                    attachments=[{key: value for key, value in attachment.items() if key != "data"}
                                 for attachment in item.get("attachments", [])] or None,
                    content_blocks=item.get("content_blocks") or None,
                ))
            user_message = next((item["content"] for item in history if item["role"] == "user"), "")
            if chat.title == "Cuộc trò chuyện mới" and user_message:
                chat.title = user_message.strip()[:80]
            chat.updated_at = datetime.utcnow()
            session.commit()

    def update_model(self, chat_id: str, provider: str, model: str) -> None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                raise ValueError("Không tìm thấy chat.")
            chat.provider = provider
            chat.model = model
            chat.updated_at = datetime.utcnow()
            session.commit()

    def update(self, chat_id: str, **values) -> Chat | None:
        allowed = {"title", "pinned", "archived", "provider", "model"}
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            for key, value in values.items():
                if key in allowed and value is not None:
                    setattr(chat, key, value)
            chat.updated_at = datetime.utcnow()
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
                share.updated_at = datetime.utcnow()
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
                    "position": message.position,
                    "role": message.role, "content": message.content, "id": message.tool_call_id,
                    "name": message.tool_name, "tool_calls": message.tool_calls,
                    "attachments": message.attachments,
                    "content_blocks": message.content_blocks,
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
            item.updated_at = datetime.utcnow()
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
                run = ScheduleRun(schedule_id=schedule.id, scheduled_for=scheduled_for, status="running", started_at=now)
                session.add(run)
                schedule.last_run_at = now
                schedule.next_run_at = self.next_run_after(schedule, now)
                if schedule.next_run_at is None:
                    schedule.status = "completed"
                schedule.updated_at = now
                claimed.append((schedule, run))
            session.commit()
            return claimed

    def claim_manual(self, schedule_id: str, now: datetime) -> tuple[Schedule, ScheduleRun] | None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id, with_for_update=True)
            if schedule is None:
                return None
            run = ScheduleRun(schedule_id=schedule.id, scheduled_for=now, status="running", started_at=now)
            session.add(run)
            schedule.last_run_at, schedule.updated_at = now, now
            session.commit()
            return schedule, run

    def finish(self, run_id: str, *, summary: str | None = None, error: str | None = None) -> ScheduleRun | None:
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None:
                return None
            run.status = "failed" if error else "succeeded"
            run.summary, run.error, run.finished_at = summary, error, datetime.utcnow()
            session.commit()
            return run

    def recover_stale_runs(self, now: datetime, timeout: timedelta = timedelta(minutes=20)) -> int:
        with self.database.session() as session:
            stale = session.scalars(
                select(ScheduleRun).where(ScheduleRun.status == "running", ScheduleRun.started_at < now - timeout)
            ).all()
            for run in stale:
                run.status, run.error, run.finished_at = "failed", "Worker timeout; hãy chạy lại thủ công.", now
            session.commit()
            return len(stale)

    def list_runs(self, schedule_id: str, limit: int = 30) -> list[ScheduleRun]:
        with self.database.session() as session:
            return list(session.scalars(select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id).order_by(ScheduleRun.started_at.desc()).limit(limit)))

    def attach_chat(self, schedule_id: str, chat_id: str) -> None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id)
            if schedule is not None:
                schedule.chat_id, schedule.updated_at = chat_id, datetime.utcnow()
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
            if job:
                job.status, job.locked_at, job.last_error = "succeeded", None, None
                session.commit()

    def fail(self, job_id: str, error: str, now: datetime) -> None:
        with self.database.session() as session:
            job = session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.last_error, job.locked_at = error[:10_000], None
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status, job.run_after = "queued", now + timedelta(seconds=2 ** job.attempts)
            session.commit()

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
