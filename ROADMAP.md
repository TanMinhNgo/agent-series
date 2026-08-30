# Agent Series Roadmap

> Cập nhật: 31/08/2026  
> Định hướng: xây Agent Series thành AI workspace tạo ra kết quả có thể xem lại, chỉnh sửa và cộng tác; không chỉ là chatbot trả lời.

## Trạng thái hiện tại

- Chat React/FastAPI có lịch sử lưu DB, SSE, chọn provider/model và RAG với PostgreSQL/pgvector.
- Workspace có thành viên, lời mời và các quyền owner/editor/viewer.
- Library lưu file upload và file AI tạo (`LibraryAsset`), có version, preview text/PDF/ảnh, file storage private và download.
- Google Workspace và GitHub App hoạt động theo nguyên tắc read-only.
- Scheduler, worker retry và CI gồm GitHub Actions, Jenkins, OWASP, SonarQube, Trivy, Docker image đã có nền tảng.
- Đã hoàn thành Artifact Panel Bước 1: panel bên phải chat liệt kê file AI tạo, mở lại file cũ theo `assetId`, preview file hỗ trợ và tự chọn file mới khi tool `create_file` chạy.

## Ưu tiên tiếp theo

### 1. Artifact theo từng request và chỉnh sửa có version

Mục tiêu: một file luôn biết nó được tạo từ yêu cầu/chat nào; người dùng có thể quay lại đúng bản cũ và yêu cầu AI cập nhật file đó.

- Thêm liên kết giữa message/request trong chat và `LibraryAsset`.
- Hiển thị file tạo ra ngay dưới phản hồi assistant tương ứng.
- Trong Artifact Panel, nhóm file theo chat/request và giữ mốc thời gian tạo.
- Thêm hành động **Sửa file này**: gửi `artifactId` + version đang xem vào AI context.
- AI tạo version mới dưới cùng `artifactId`, không tạo artifact độc lập.
- Hiển thị version history, thay đổi gần nhất, download từng version và quay lại version cũ.
- Hỗ trợ code/text (`.py`, `.ts`, `.tsx`, `.json`, `.md`) có preview và diff trước/sau.

**Hoàn thành khi:** tạo file từ một chat, mở lại chat cũ vẫn thấy chính file đó; sửa file tạo version mới và version cũ vẫn preview/download đúng nội dung cũ.

### 2. Project workspace AI

Mục tiêu: Project là nơi gom mục tiêu, dữ liệu, chat và kết quả AI của một công việc.

- Project overview: mô tả, chat gần đây, file/artifact mới, lịch chạy và hoạt động gần đây.
- Ghim file/version vào Project Source để AI dùng đúng context.
- Hiển thị nguồn và version đã dùng trong mỗi câu trả lời.
- Áp quyền workspace cho Project, chat và artifact; owner/editor/viewer có hành vi rõ ràng.
- Activity log cho tạo/sửa/xóa/chia sẻ artifact và lời mời thành viên.

**Hoàn thành khi:** một nhóm có thể cùng làm trong Project, biết file/chat nào mới thay đổi và AI trích đúng nguồn đã ghim.

### 3. RAG đáng tin cậy

Mục tiêu: câu trả lời dựa trên tài liệu phải có nguồn kiểm tra được.

- Chọn collection/file/version làm nguồn trước khi hỏi.
- Citation dẫn đến đúng artifact, trang/đoạn và version.
- Hiển thị trạng thái index, lỗi và retry của từng tài liệu.
- Xây bộ câu hỏi đánh giá RAG: độ đúng citation, độ bao phủ và trường hợp không có dữ liệu.
- Kiểm thử runtime thực với PDF đã index và provider đang dùng, không chỉ mock HTTP.

**Hoàn thành khi:** người dùng mở được nguồn của mỗi câu trả lời RAG và hệ thống không tự bịa nguồn khi không tìm thấy dữ liệu.

### 4. Workflow và automation

Mục tiêu: biến scheduled chat thành luồng làm việc tạo ra kết quả hữu ích.

- Workflow: lấy nguồn → AI tổng hợp → tạo artifact → thông báo.
- Template sẵn có: daily digest, tổng hợp GitHub tuần, báo cáo Project, tóm tắt tài liệu mới.
- Mỗi lần chạy lưu chat, artifact, trạng thái và lỗi để xem lại/chạy lại an toàn.
- Giữ nguyên provider/model người dùng chọn; không tự đổi model khi lỗi.

**Hoàn thành khi:** một workflow có thể chạy định kỳ, sinh file/report đúng owner và không tạo trùng khi retry.

### 5. Connectors và trải nghiệm nguồn dữ liệu

Mục tiêu: dùng nguồn ngoài một cách rõ quyền, an toàn và dễ truy vết.

- Cải thiện chọn repository/folder/source khi dùng Google Workspace và GitHub.
- Hiển thị scope, trạng thái kết nối và audit log dễ đọc.
- Chỉ cân nhắc Notion, Slack hoặc OneDrive sau khi có nhu cầu sử dụng thực tế.
- Giữ read-only mặc định; mọi thao tác ghi dữ liệu cần flow xác nhận riêng.

## Nền tảng production cần củng cố song song

- Tách cấu hình local/staging/production bằng Docker Compose profile và secrets.
- Backup PostgreSQL, lifecycle file storage và quy trình khôi phục.
- Monitoring API/worker, alert cho failed schedule/index job và audit cho hành động nhạy cảm.
- Duy trì quality gate CI: test, format/lint/build, OWASP, SonarQube, Trivy và Docker image versioning; CD chỉ triển khai sau khi gate pass.

## Thứ tự thực hiện đề xuất

1. Liên kết chat/request với artifact.
2. Sửa artifact bằng AI và tạo version mới.
3. Project overview + activity log.
4. Citation/RAG evaluation.
5. Workflow scheduler tạo artifact.
6. Củng cố production/monitoring và mở rộng connector theo nhu cầu.

## Nguyên tắc triển khai

- Làm theo milestone nhỏ, có test và checkpoint; không dồn thành một đợt rewrite lớn.
- Tôn trọng ownership, quyền workspace và version cũ của artifact.
- Không tự đổi provider/model đã chọn trong chat hoặc scheduler.
- Mọi chỉnh sửa frontend phải chạy `cd frontend; npm run format`, sau đó lint/build trước khi push.
