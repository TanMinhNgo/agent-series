"""PostgreSQL persistence for chats and the document knowledge base."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, create_engine, delete, select
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

    def create(self, provider: str, model: str) -> Chat:
        with self.database.session() as session:
            chat = Chat(provider=provider, model=model)
            session.add(chat)
            session.commit()
            return chat

    def list(self) -> list[Chat]:
        with self.database.session() as session:
            return list(session.scalars(select(Chat).order_by(Chat.updated_at.desc())))

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
                    "role": message.role, "content": message.content, "id": message.tool_call_id,
                    "name": message.tool_name, "tool_calls": message.tool_calls,
                }.items() if value is not None}
                for message in messages
            ]
