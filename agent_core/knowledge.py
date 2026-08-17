"""PDF ingestion and pgvector retrieval for the local knowledge base."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy import select

from .storage import Database, Document, DocumentChunk
from .tools.base import ToolSpec

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


def _chunks(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    result, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary
        result.append(text[start:end].strip())
        start = max(end - CHUNK_OVERLAP, start + 1)
    return result


class KnowledgeService:
    def __init__(self, database: Database, knowledge_dir: Path, embedding_model: str):
        self.database = database
        self.knowledge_dir = knowledge_dir
        self.embedding_model_name = embedding_model
        self._embedder = None

    def _embedder_instance(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.embedding_model_name)
        return self._embedder

    def _embed(self, values: list[str], prefix: str) -> list[list[float]]:
        vectors = self._embedder_instance().encode(
            [f"{prefix}: {value}" for value in values], normalize_embeddings=True
        )
        return vectors.tolist()

    def list_documents(self, project_id: str | None = None) -> list[Document]:
        with self.database.session() as session:
            statement = select(Document).order_by(Document.created_at.desc())
            if project_id is not None:
                statement = statement.where(Document.project_id == project_id)
            return list(session.scalars(statement))

    def upload(self, original_name: str, data: bytes, project_id: str | None = None) -> tuple[Document, bool]:
        if not original_name.lower().endswith(".pdf"):
            raise ValueError("Chỉ nhận file PDF.")
        if not data:
            raise ValueError("File PDF đang trống.")
        if len(data) > 25 * 1024 * 1024:
            raise ValueError("PDF vượt giới hạn 25 MB.")
        digest = hashlib.sha256(data).hexdigest()
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        with self.database.session() as session:
            existing = session.scalar(select(Document).where(Document.sha256 == digest, Document.project_id == project_id))
            if existing:
                return existing, False
            stored_name = f"{uuid4()}_{Path(original_name).name}"
            (self.knowledge_dir / stored_name).write_bytes(data)
            document = Document(original_name=Path(original_name).name, stored_name=stored_name, sha256=digest, project_id=project_id)
            session.add(document)
            session.commit()
            return document, True

    def index(self, document_id: str) -> Document:
        with self.database.session() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise ValueError("Không tìm thấy tài liệu.")
            document.status, document.error = "indexing", None
            session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
            session.commit()
            file_path = self.knowledge_dir / document.stored_name
            try:
                reader = PdfReader(str(file_path))
                parts: list[tuple[int, str]] = []
                for page_number, page in enumerate(reader.pages, start=1):
                    parts.extend((page_number, item) for item in _chunks(page.extract_text() or ""))
                if not parts:
                    document.status, document.error = "needs_ocr", "PDF không có text layer. Hãy OCR trước rồi thử index lại."
                    session.commit()
                    return document
                embeddings = self._embed([content for _, content in parts], "passage")
                for index, ((page_number, content), embedding) in enumerate(zip(parts, embeddings)):
                    session.add(DocumentChunk(document_id=document.id, chunk_index=index, page_number=page_number, content=content, embedding=embedding))
                document.status, document.page_count = "ready", len(reader.pages)
            except Exception as exc:  # noqa: BLE001
                document.status, document.error = "failed", str(exc)
            session.commit()
            if document.status == "failed":
                raise RuntimeError(document.error or "Không thể index tài liệu.")
            return document

    def delete(self, document_id: str) -> bool:
        with self.database.session() as session:
            document = session.get(Document, document_id)
            if document is None:
                return False
            path = self.knowledge_dir / document.stored_name
            if path.exists():
                path.unlink()
            session.delete(document)
            session.commit()
            return True

    def search(self, query: str, top_k: int = 4, project_id: str | None = None) -> str:
        if not query.strip():
            return "[Lỗi] Câu hỏi truy vấn đang trống."
        top_k = max(1, min(int(top_k), 8))
        vector = self._embed([query], "query")[0]
        with self.database.session() as session:
            distance = DocumentChunk.embedding.cosine_distance(vector)
            rows = session.execute(
                select(DocumentChunk, Document.original_name, distance.label("distance"))
                .join(Document)
                .where(Document.status == "ready", Document.project_id == project_id)
                .order_by(distance)
                .limit(top_k)
            ).all()
        if not rows:
            return "Không có tài liệu nào đã index để trả lời câu hỏi này."
        return "\n\n".join(
            f"[Nguồn {number}: {name}, trang {chunk.page_number}]\n{chunk.content}"
            for number, (chunk, name, _) in enumerate(rows, start=1)
        )


def build_knowledge_tool(service: KnowledgeService, project_id: str | None = None) -> ToolSpec:
    return ToolSpec(
        name="search_knowledge_base",
        description="Tìm thông tin trong các PDF người dùng đã upload và index. Dùng khi câu hỏi liên quan đến tài liệu; câu trả lời phải nêu nguồn và số trang.",
        parameters={"type": "object", "properties": {"query": {"type": "string", "description": "Câu truy vấn rõ ràng bằng ngôn ngữ tự nhiên."}, "top_k": {"type": "integer", "description": "Số đoạn cần lấy, từ 1 đến 8; mặc định 4."}}, "required": ["query"]},
        func=lambda query, top_k=4: service.search(query, top_k, project_id),
    )
