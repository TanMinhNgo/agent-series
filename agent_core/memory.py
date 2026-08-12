"""Long-term, local chat memory backed by the project's pgvector database."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select

from .knowledge import _chunks
from .storage import Chat, ChatMemoryChunk, Database


class MemoryService:
    def __init__(self, database: Database, embedding_model: str):
        self.database = database
        self.embedding_model = embedding_model
        self._embedder = None

    def _embed(self, values: list[str], prefix: str) -> list[list[float]]:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.embedding_model)
        return self._embedder.encode([f"{prefix}: {value}" for value in values], normalize_embeddings=True).tolist()

    def index_history(self, chat_id: str, history: list[dict[str, Any]]) -> None:
        candidates = [(index, item) for index, item in enumerate(history) if item.get("role") in {"user", "assistant"} and item.get("content", "").strip()]
        if not candidates:
            return
        with self.database.session() as session:
            existing = {(item.fingerprint, item.chunk_index) for item in session.scalars(select(ChatMemoryChunk).where(ChatMemoryChunk.chat_id == chat_id))}
            pending: list[tuple[str, str, str, int]] = []
            for position, item in candidates:
                fingerprint = hashlib.sha256(f"{position}:{item['role']}:{item['content']}".encode()).hexdigest()
                for chunk_index, content in enumerate(_chunks(item["content"])):
                    if (fingerprint, chunk_index) not in existing:
                        pending.append((item["role"], fingerprint, content, chunk_index))
            if not pending:
                return
            embeddings = self._embed([item[2] for item in pending], "memory")
            for (role, fingerprint, content, chunk_index), embedding in zip(pending, embeddings):
                session.add(ChatMemoryChunk(chat_id=chat_id, role=role, fingerprint=fingerprint, content=content, chunk_index=chunk_index, embedding=embedding))
            session.commit()

    def recall(self, query: str, limit: int = 6) -> str:
        if not query.strip():
            return ""
        vector = self._embed([query], "query")[0]
        with self.database.session() as session:
            distance = ChatMemoryChunk.embedding.cosine_distance(vector)
            rows = session.execute(select(ChatMemoryChunk, Chat.title, distance.label("distance")).join(Chat).where(ChatMemoryChunk.forgotten.is_(False)).order_by(distance).limit(limit)).all()
        if not rows:
            return ""
        facts = "\n\n".join(f"[Trí nhớ từ chat: {title}; {chunk.role}]\n{chunk.content}" for chunk, title, _ in rows)
        return "Dưới đây là thông tin cũ có thể liên quan. Chỉ dùng khi phù hợp; nếu mâu thuẫn, hỏi lại người dùng:\n\n" + facts

    def list(self, query: str = "") -> list[dict[str, Any]]:
        with self.database.session() as session:
            statement = select(ChatMemoryChunk, Chat.title).join(Chat).where(ChatMemoryChunk.forgotten.is_(False)).order_by(ChatMemoryChunk.created_at.desc()).limit(200)
            rows = session.execute(statement).all()
        if query.strip():
            needle = query.lower()
            rows = [row for row in rows if needle in row[0].content.lower() or needle in row[1].lower()]
        return [{"id": chunk.id, "chatId": chunk.chat_id, "chatTitle": title, "role": chunk.role, "content": chunk.content, "createdAt": chunk.created_at.isoformat()} for chunk, title in rows]

    def forget(self, memory_id: str) -> bool:
        with self.database.session() as session:
            chunk = session.get(ChatMemoryChunk, memory_id)
            if chunk is None:
                return False
            chunk.forgotten = True
            session.commit()
            return True

    def forget_all(self) -> int:
        with self.database.session() as session:
            rows = session.scalars(select(ChatMemoryChunk).where(ChatMemoryChunk.forgotten.is_(False))).all()
            for row in rows:
                row.forgotten = True
            session.commit()
            return len(rows)
