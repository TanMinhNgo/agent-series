"""PostgreSQL persistence for chats and the document knowledge base."""

from __future__ import annotations

from datetime import datetime
from secrets import token_urlsafe
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, delete, desc, select
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


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.session_factory()


class ChatRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, provider: str, model: str, context_source_chat_id: str | None = None) -> Chat:
        with self.database.session() as session:
            chat = Chat(provider=provider, model=model, context_source_chat_id=context_source_chat_id)
            session.add(chat)
            session.commit()
            return chat

    def list(self) -> list[Chat]:
        with self.database.session() as session:
            return list(session.scalars(select(Chat).order_by(desc(Chat.pinned), desc(Chat.updated_at))))

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

    def create_or_update_share(self, chat_id: str) -> ChatShare | None:
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
                share = ChatShare(chat_id=chat.id, title=chat.title, provider=chat.provider, model=chat.model, messages=messages)
                session.add(share)
            else:
                share.title, share.provider, share.model, share.messages = chat.title, chat.provider, chat.model, messages
                share.updated_at = datetime.utcnow()
            session.commit()
            return share

    def get_share(self, token: str) -> ChatShare | None:
        with self.database.session() as session:
            return session.scalar(select(ChatShare).where(ChatShare.token == token))

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
                if value is not None:
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
