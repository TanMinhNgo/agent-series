# Deploy production: Vercel + OCI Always Free

Frontend React/Vite chạy trên Vercel. OCI chỉ chạy FastAPI, worker và PostgreSQL; Caddy cấp HTTPS cho `api-*.duckdns.org`. Không kết nối Vercel trực tiếp với API: Vercel rewrite `/api/*`, nên session cookie, SSE và các link file tương đối vẫn cùng origin.

## Provision một lần

1. Tạo OCI Always Free Ubuntu ARM VM, gán public IP tĩnh, mở ingress TCP `80`, `443` và `22`; cài Docker Engine cùng Compose plugin.
2. Tạo DuckDNS subdomain trỏ tới IP VM, ví dụ `api-agent-series-minh.duckdns.org`.
3. Trên VM, tạo `~/agent-series`, copy `deploy/.env.oci.example` thành `~/agent-series/.env`, điền Docker Hub image, mật khẩu database và toàn bộ secret từ `.env.example`. Đặt `APP_WEB_URL` là URL production Vercel. SSH user cần thuộc nhóm `docker`.
4. Trong Google Cloud/GitHub App, dùng callback qua Vercel: `https://<project>.vercel.app/api/auth/google/callback`, `https://<project>.vercel.app/api/connectors/google/callback`, và callback GitHub tương ứng. Đây là bắt buộc để cookie session thuộc Vercel origin.
5. Tạo Vercel project với Root Directory `frontend`; tắt Git auto-deploy để Jenkins là release authority duy nhất.

## Jenkins credentials

| Credential ID | Kiểu | Giá trị |
| --- | --- | --- |
| `dockerhub-credentials` | Username/password | Docker Hub hiện có |
| `oci-deploy-key` | SSH Username with private key | user SSH của VM và private key |
| `oci-deploy-host` | Secret text | public IP hoặc hostname OCI |
| `oci-known-hosts` | Secret file | host key OCI từ `ssh-keyscan` đã được kiểm tra fingerprint |
| `vercel-token` | Secret text | Vercel access token |
| `vercel-org-id` | Secret text | Vercel team/user ID |
| `vercel-project-id` | Secret text | Vercel project ID |
| `vercel-backend-origin` | Secret text | `https://api-agent-series-<handle>.duckdns.org` |

Sau đó, push một commit vào `main`. Jenkins scan image ARM, push tag `sha-<full-sha>`, backup PostgreSQL trước Alembic migration, deploy OCI, kiểm tra `/api/health`, rồi deploy frontend Vercel. File `.env` không rời VM; backup trước migration nằm ở `~/agent-series/backups`.

## Rollback

Lấy SHA trước trong `~/agent-series/.deployed-sha`, đổi `IMAGE_TAG` sang `sha-<previous-sha>` rồi chạy `docker compose --env-file .env -f docker-compose.oci.yml up -d`. Không tự động hạ migration; nếu migration đã thay đổi schema, khôi phục backup `pre-<sha>.sql.gz` có kiểm soát.
