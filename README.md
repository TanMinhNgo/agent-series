# Agent Series

Ứng dụng AI agent đa nhà cung cấp với giao diện chat hiện đại, lưu hội thoại, RAG PDF cục bộ và bộ nhớ dài hạn có thể kiểm soát. Dự án dùng **React + Vite + TypeScript** ở frontend, **FastAPI** ở backend và **PostgreSQL + pgvector** cho dữ liệu/embedding.

> Trạng thái hiện tại: ứng dụng local cho **một người dùng**, chưa có đăng nhập. Thư viện memory là của người đang dùng instance database đó.

## Điểm nổi bật

- Chat với Gemini, Claude hoặc OpenAI; model được cấu hình qua allowlist trong `.env`.
- Lưu lịch sử chat vào PostgreSQL: đổi model sẽ tạo chat mới nhưng giữ ngữ cảnh 10 lượt gần nhất của chat đang mở.
- Hiển thị Markdown/GFM, bảng, công thức KaTeX, code block có nút sao chép, chữ **đậm**, *nghiêng* và liên kết an toàn.
- Upload PDF, trích xuất nội dung, chia đoạn, tạo embedding local và tìm kiếm ngữ nghĩa bằng pgvector.
- Thư viện memory dài hạn: tự index hội thoại, tự tìm phần liên quan cho câu hỏi mới, tìm kiếm/forget từng mục hoặc xoá toàn bộ trong UI.
- Stream trạng thái agent/tool qua SSE, hỗ trợ file/ảnh đính kèm, giao diện sáng/tối/system.
- Chia sẻ bản snapshot chat công khai bằng token khi cần.

## Kiến trúc

```text
Browser (React/Vite)
        │  REST + SSE
        ▼
FastAPI API ── Agent core ── LLM provider (Gemini / Claude / OpenAI)
        │
        ├── PostgreSQL + pgvector (chat, memory, RAG)
        └── Local storage (PDF knowledge base, media uploads)
```

## Yêu cầu

- Python 3.10+
- Node.js 20+
- Docker Desktop đang chạy
- API key của ít nhất một LLM provider

## Chạy nhanh trên Windows

1. Tạo file cấu hình và điền API key:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

2. Khởi động toàn bộ stack:

   ```powershell
   .\run.ps1
   ```

Lần đầu script sẽ tạo `.venv`, cài Python/Node dependencies, chạy PostgreSQL + pgvector tại cổng `5433`, áp Alembic migration, rồi mở:

- App: `http://localhost:5173`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

Nhấn `Ctrl+C` trong terminal chạy script để dừng API và Vite. Database Docker vẫn được giữ lại để không mất chat/memory.

## Cấu hình

Các biến quan trọng trong `.env`:

| Biến | Ý nghĩa |
| --- | --- |
| `LLM_PROVIDER` | `gemini`, `anthropic` hoặc `openai` |
| `*_API_KEY` | API key tương ứng; không commit file `.env` |
| `*_MODEL` / `*_MODELS` | Model mặc định và danh sách model cho UI |
| `DATABASE_URL` | PostgreSQL mặc định của Docker Compose |
| `EMBEDDING_MODEL` | Embedding multilingual chạy local, dùng cho PDF và memory |
| `KNOWLEDGE_DIR` | Thư mục lưu PDF gốc |
| `MEDIA_DIR` | Thư mục lưu media người dùng upload |

Lần đầu dùng RAG/memory, `sentence-transformers` có thể tải embedding model từ Hugging Face. Nếu bước này lỗi, chat thường vẫn hoạt động nhưng chưa đọc/lưu được memory ở lượt đó.

## Thư viện memory cá nhân

Mỗi lượt user/assistant được chia đoạn và index vào pgvector. Khi gửi câu hỏi mới, hệ thống chỉ đưa các đoạn cũ có ý nghĩa gần nhất vào prompt, không chép toàn bộ lịch sử database vào model.

Mở **Thư viện** ở sidebar để:

- tìm memory theo nội dung hoặc tên chat;
- **Quên** một đoạn: đoạn đó không còn được model truy xuất;
- xoá toàn bộ memory đã lưu.

Xoá một chat cũng xoá các memory thuộc chat đó. Khi triển khai đăng nhập trong tương lai, cần thêm `user_id` vào chat/memory và lọc mọi truy vấn theo người dùng.

## Cấu trúc thư mục

```text
agent_core/             Agent loop, provider adapters, persistence, RAG, memory
api/                    FastAPI routes và SSE streaming
frontend/               React/Vite UI
migrations/             Alembic schema migrations
knowledge/              PDF đã upload (gitignored)
uploads/                Media người dùng upload (gitignored)
docker-compose.yml      PostgreSQL + pgvector local
run.ps1                 Khởi động backend, database và frontend trên Windows
```

## Kiểm tra chất lượng

Backend:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend:

```powershell
Set-Location frontend
npm run lint
npm run build
```

## Lưu ý bảo mật

- Không commit `.env`, `knowledge/`, `uploads/`, `.venv/` hoặc dữ liệu Docker.
- API key chỉ được dùng ở FastAPI; frontend không nhận key provider.
- Link chia sẻ chat là snapshot qua token: chỉ tạo khi bạn chủ động bấm chia sẻ, và cần coi token như một URL có quyền xem.

## Phát triển tiếp

- Thêm đăng nhập và `user_id` trước khi mở cho nhiều người dùng.
- Bổ sung phân quyền và xoá/khôi phục snapshot chia sẻ.
- Đưa embedding/indexing sang worker queue nếu dữ liệu lớn.
- Viết integration test với PostgreSQL/pgvector thực cho RAG và memory.
