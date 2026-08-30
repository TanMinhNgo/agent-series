# Agent Series

Ứng dụng AI agent đa nhà cung cấp với giao diện chat hiện đại, lưu hội thoại, RAG cục bộ cho PDF/DOCX/Markdown và bộ nhớ dài hạn có thể kiểm soát. Dự án dùng **React + Vite + TypeScript** ở frontend, **FastAPI** ở backend và **PostgreSQL + pgvector** cho dữ liệu/embedding.

> Trạng thái hiện tại: ứng dụng local đăng nhập Google Sign-In và ownership theo user. BYOK và model catalog sync là các mốc tiếp theo.

## Điểm nổi bật

- Chat với Gemini, Claude hoặc OpenAI; model được cấu hình qua allowlist trong `.env`.
- Lưu toàn bộ lịch sử chat vào PostgreSQL; AI nhận 10 lượt gần nhất và truy hồi semantic các đoạn cũ liên quan bằng pgvector trong đúng chat đang mở.
- Hiển thị Markdown/GFM, bảng, công thức KaTeX, code block có nút sao chép, chữ **đậm**, *nghiêng* và liên kết an toàn.
- Upload PDF, DOCX hoặc Markdown; xử lý/index nền qua PostgreSQL job queue, chia đoạn, tạo embedding local và tìm kiếm ngữ nghĩa bằng pgvector.
- Thư viện memory dài hạn: tự index hội thoại, tự tìm phần liên quan cho câu hỏi mới, tìm kiếm/forget từng mục hoặc xoá toàn bộ trong UI.
- Stream trạng thái agent/tool qua SSE, hỗ trợ file/ảnh đính kèm, giao diện sáng/tối/system.
- Lên lịch tác vụ AI một lần, hằng ngày hoặc hằng tuần; mỗi lịch có chat kết quả, run log và timeout recovery riêng.
- Chia sẻ bản snapshot chat công khai bằng token, có thể đặt hạn dùng hoặc thu hồi.
- Google Workspace connector read-only: tìm/đọc nội dung Drive, Gmail và Calendar sau OAuth; token được mã hóa cục bộ và có audit log.

## Kiến trúc

```text
Browser (React/Vite)
        │  REST + SSE
        ▼
FastAPI API ── Agent core ── LLM provider (Gemini / Claude / OpenAI / Ollama local)
        │
        ├── PostgreSQL + pgvector (chat, memory, RAG)
        └── ImageKit private storage (hoặc local fallback khi chưa cấu hình)

Worker ── PostgreSQL (job queue, lịch đến hạn, run log) ── Agent core
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

Lần đầu script sẽ tạo `.venv`, cài Python/Node dependencies, chạy PostgreSQL + pgvector tại cổng `5433`, áp Alembic migration, khởi động scheduler worker nền, rồi mở:

- App: `http://localhost:5173`

### Worker bền vững trên Windows

Worker dùng queue PostgreSQL và có heartbeat trong Admin. Để nó tự chạy lại khi đăng nhập Windows, cài Scheduled Task theo user hiện tại:

```powershell
.\scripts\install-worker-task.ps1
```

`run.ps1` sẽ tự dùng task này ở các lần chạy sau; dùng `-StartNow` nếu không có worker local nào đang chạy. Kiểm tra bằng `.\scripts\worker-task-status.ps1`, hoặc gỡ bằng `.\scripts\uninstall-worker-task.ps1`. Log được xoay tại `logs\worker-YYYY-MM-DD.log` và giữ 14 ngày.
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

Nhấn `Ctrl+C` trong terminal chạy script để dừng API và Vite. Database Docker vẫn được giữ lại để không mất chat/memory.

## Cấu hình

Các biến quan trọng trong `.env`:

| Biến | Ý nghĩa |
| --- | --- |
| `LLM_PROVIDER` | `gemini`, `anthropic`, `openai` hoặc `ollama` |
| `*_API_KEY` | API key tương ứng; không commit file `.env` |
| `*_MODEL` / `*_MODELS` | Model mặc định và danh sách model cho UI |
| `OLLAMA_BASE_URL` | Ollama local, mặc định `http://127.0.0.1:11434`; model được tự phát hiện từ máy |
| `DATABASE_URL` | PostgreSQL mặc định của Docker Compose |
| `EMBEDDING_MODEL` | Embedding multilingual chạy local, dùng cho PDF và memory |
| `KNOWLEDGE_DIR` | Thư mục lưu PDF gốc |
| `MEDIA_DIR` | Thư mục lưu media người dùng upload |
| `IMAGEKIT_PRIVATE_KEY`, `IMAGEKIT_URL_ENDPOINT` | ImageKit private storage và signed URL (tuỳ chọn) |
| `GOOGLE_OAUTH_*` | OAuth Web Client cho Google Workspace connector (tuỳ chọn) |
| `CONNECTOR_ENCRYPTION_KEY` | Fernet key mã hóa token connector trong PostgreSQL |

Lần đầu dùng RAG/memory, `sentence-transformers` có thể tải embedding model từ Hugging Face. Nếu bước này lỗi, chat thường vẫn hoạt động nhưng chưa đọc/lưu được memory ở lượt đó.

PDF scan không có text layer sẽ được đánh dấu **Cần OCR** thay vì index lỗi; OCR engine chưa được cài trong bản local này.

## Ollama local

Khi Ollama chạy cùng máy, khởi động Ollama rồi pull model bạn muốn dùng. Agent Series tự đọc model đã cài và hiện chúng trong selector provider; không cần API key hoặc danh sách model cố định trong `.env`.

Ollama ở bản hiện tại nhận chat văn bản và chỉ được gọi `search_knowledge_base` cho RAG local. Web search, plugin, tạo file và attachment vẫn thuộc provider cloud để tránh mở rộng quyền tool cho model local. LangChain chỉ được dùng ở `langchain-text-splitters` để chia chunk khi index tài liệu mới; pgvector, embedding và retrieval hiện có không bị thay thế.

## Đăng nhập bằng Google

Sau migration `0018`, API private yêu cầu session Google. Trong Google Cloud Console, thêm `http://localhost:8000/api/auth/google/callback` vào **Authorized redirect URIs** của OAuth Web application. Có thể dùng cùng Client ID/Secret với Google Workspace connector; backend tự fallback về `GOOGLE_OAUTH_CLIENT_ID` và `GOOGLE_OAUTH_CLIENT_SECRET` nếu các biến `GOOGLE_AUTH_*` để trống. User Google đầu tiên sẽ claim dữ liệu local đã có và nhận role owner.

SMTP không dùng để đăng nhập. Nó phục vụ email thông báo khi một lịch trình chạy xong: bật `SMTP_HOST` và `SMTP_FROM` rồi tick "Gửi email khi hoàn tất" trong lịch trình, email sẽ tới địa chỉ của tài khoản sở hữu lịch. Liên kết mở chat chỉ được chèn khi `APP_WEB_URL` trỏ tới địa chỉ công khai.

Không dùng phiên ChatGPT, Gemini web hay Claude.ai làm API credential: Gemini API dùng API key; OpenAI/Anthropic API dùng credential platform riêng. API key không được đặt ở frontend.

## Lưu ảnh và file bằng ImageKit

Thêm `IMAGEKIT_PRIVATE_KEY` và `IMAGEKIT_URL_ENDPOINT` từ ImageKit Developer Options vào `.env`, rồi chạy migration `\.venv\Scripts\python.exe -m alembic upgrade head` và restart API/worker. File mới được upload private vào folder theo từng user; API trả URL ký có hạn 5 phút. Ảnh chat, Library/artifact và PDF/DOCX/Markdown RAG đều dùng chung cơ chế này. Nếu hai biến để trống, hệ thống tiếp tục dùng local filesystem. File local cũ được chuyển sang ImageKit ở lần đọc đầu tiên sau khi cấu hình.

## Kết nối Google Workspace (chỉ đọc)

1. Trong Google Cloud Console, tạo **OAuth client type: Web application** và thêm `http://localhost:8000/api/connectors/google/callback` vào Authorized redirect URIs.
2. Chép Client ID, Client Secret vào `.env`; tạo key mã hóa bằng lệnh đã ghi trong `.env.example` và đặt vào `CONNECTOR_ENCRYPTION_KEY`.
3. Restart backend, mở **Plugin**, thêm Google Workspace rồi bấm **Kết nối Google**. Sau khi cấp quyền, chỉ bấm **Bật cho chat** nếu muốn agent dùng Drive/Calendar.

Connector xin quyền đọc Drive (Google Docs/Sheets/Slides, PDF và file text phù hợp), Gmail và Calendar. Nó không upload, import vào RAG, gửi email, tạo hoặc sửa sự kiện. **Ngắt kết nối** sẽ xóa token đã lưu cục bộ; audit log chỉ ghi hành động/tóm tắt, không ghi token hay nội dung file/email/sự kiện.

## Kết nối GitHub App (chỉ đọc)

1. Tạo GitHub App, đặt **Setup URL** là `http://localhost:8000/api/connectors/github/callback`, rồi chỉ cấp quyền repository cần dùng ở mức Read-only (Contents, Issues, Pull requests, Actions).
2. Đặt `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_PRIVATE_KEY` và `CONNECTOR_ENCRYPTION_KEY` trong `.env`; private key PEM có thể dùng `\\n` thay cho xuống dòng.
3. Trong **Plugin**, thêm GitHub, bấm **Kết nối GitHub**, chọn account/tổ chức và repository khi GitHub hỏi, rồi bật cho chat.

Liên kết chỉ lưu installation ID đã mã hóa theo user. Private key của GitHub App chỉ ở server, installation token được tạo ngắn hạn khi chat cần đọc repository. Plugin không có tool tạo issue/PR hay sửa source code.

Plugin catalog được quản lý theo từng user. Hiện Google Workspace là connector OAuth thực; các plugin còn lại hiển thị rõ là đang chờ adapter riêng, không giả lập trạng thái đã kết nối. System admin chỉ xem metadata kết nối (user, plugin, trạng thái, số quyền và thời điểm), không xem token hoặc thao tác trên kết nối của user.

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
knowledge/              Tài liệu RAG đã upload (gitignored)
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

## CI: GitHub Actions → Jenkins → security → Docker

Mỗi pull request và push đều chạy migration + pytest/coverage với PostgreSQL pgvector, format/lint/build frontend trên GitHub Actions. Sau một **push** đã pass, workflow gọi Jenkins với đúng commit SHA; PR không gọi Jenkins để không cấp secrets cho code chưa tin cậy.

Jenkins chạy lần lượt: test/coverage, OWASP Dependency-Check, SonarQube Quality Gate, Trivy source/config, build ba Docker image (`api`, `worker`, `frontend`), Trivy image scan, rồi mới đẩy image đã được xác minh lên Docker Hub. Mọi report được archive tại Jenkins; pipeline dừng ở CVSS 7+ hoặc Trivy `HIGH`/`CRITICAL` và sẽ không push image nếu một gate thất bại.

GitHub repository secrets bắt buộc: `JENKINS_TRIGGER_URL` (endpoint `buildWithParameters`), `JENKINS_USER`, `JENKINS_API_TOKEN`, `JENKINS_JOB_TOKEN`.

Jenkins cần Docker daemon, Git credential ID `github-read-token`, secret text `nvd-api-key`, username/password credential `dockerhub-credentials`, SonarQube server name `SonarQube`, và scanner tool name `SonarScanner`. Sonar token/URL được quản lý trong Jenkins SonarQube configuration, không commit vào repo.

Tạo ba Docker Hub repository `<dockerhub-user>/agent-series-api`, `<dockerhub-user>/agent-series-worker`, `<dockerhub-user>/agent-series-frontend`. Chỉ build Jenkins được trigger từ nhánh `main` mới push image: mỗi image có tag bất biến `sha-<full-git-sha>` và `latest`. CD sau này phải pin vào tag `sha-...`, không deploy theo `latest`.

Production compose dùng `docker-compose.prod.yml`. Tạo `.env` từ `.env.example`, đặt `POSTGRES_PASSWORD` mạnh và chạy `docker compose -f docker-compose.prod.yml up -d --build`. Frontend phục vụ ở `APP_PORT` (mặc định `8080`) và proxy `/api` vào API container.

Backend CI dùng `requirements-ci.lock` có version và hash cố định, bao gồm PyTorch CPU-only để chạy được trên GitHub-hosted runner không có CUDA. Sau khi thay đổi `requirements.txt`, chạy `python -m pip install uv` (một lần) rồi `uv pip compile requirements-ci.in -o requirements-ci.lock --generate-hashes --emit-index-url --index-strategy unsafe-best-match`; commit cả hai file.

## Lưu ý bảo mật

- Không commit `.env`, `knowledge/`, `uploads/`, `.venv/` hoặc dữ liệu Docker.
- API key chỉ được dùng ở FastAPI; frontend không nhận key provider.
- Link chia sẻ chat là snapshot qua token: chỉ tạo khi bạn chủ động bấm chia sẻ, và cần coi token như một URL có quyền xem.

## Phát triển tiếp

- Thêm đăng nhập và `user_id` trước khi mở cho nhiều người dùng.
- Bổ sung phân quyền và xoá/khôi phục snapshot chia sẻ.
- Đưa embedding/indexing sang worker queue nếu dữ liệu lớn.
- Viết integration test với PostgreSQL/pgvector thực cho RAG và memory.
