<div align="center">

<img src="https://api.iconify.design/lucide/workflow.svg?color=%236E56CF" width="64" height="64" alt="Workflow orchestration" />

# AI Agent From Zero

### Xây dựng AI Agent đa công cụ, đa nhà cung cấp LLM — từ những thành phần cơ bản nhất

Một project Python nhỏ gọn giúp bạn nhìn rõ cách một AI Agent **suy luận → gọi tool → quan sát kết quả → trả lời**, thay vì để framework che giấu toàn bộ quá trình.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.36%2B-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![LLM Providers](https://img.shields.io/badge/LLM-Gemini%20%7C%20Claude%20%7C%20OpenAI-6E56CF?style=flat-square)](#nha-cung-cap-llm)
[![Architecture](https://img.shields.io/badge/Architecture-Provider--agnostic-0EA5E9?style=flat-square)](#kien-truc-he-thong)
[![GitHub stars](https://img.shields.io/github/stars/TanMinhNgo/agent-series?style=flat-square&logo=github&color=181717)](https://github.com/TanMinhNgo/agent-series/stargazers)

**[Bắt đầu nhanh](#bat-dau-nhanh) · [Kiến trúc](#kien-truc-he-thong) · [Cách hoạt động](#agent-hoat-dong-nhu-the-nao) · [Thêm tool](#them-tool-moi) · [Xử lý lỗi](#xu-ly-loi-thuong-gap)**

</div>

---

<a id="tong-quan"></a>
## Tổng quan

Một LLM thông thường chủ yếu sinh văn bản. Project này bổ sung cho LLM một **vòng lặp Agent** và một **bộ công cụ có kiểm soát**, để model có thể tự quyết định khi nào cần hành động.

Ví dụ với yêu cầu:

> “Đọc hóa đơn PDF, cộng các khoản rồi đổi tổng tiền sang USD.”

Agent có thể tự phối hợp ba tool theo đúng thứ tự:

```mermaid
flowchart LR
    Q["Yêu cầu của người dùng"] --> PDF["search_knowledge_base<br/>Truy hồi số liệu"]
    PDF --> CALC["calculator<br/>Tính tổng"]
    CALC --> FX["convert_currency<br/>Quy đổi tiền tệ"]
    FX --> A["Câu trả lời cuối"]

    classDef input fill:#E0F2FE,stroke:#0284C7,color:#0C4A6E,stroke-width:2px;
    classDef tool fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px;
    classDef output fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px;
    class Q input;
    class PDF,CALC,FX tool;
    class A output;
```

### Vì sao project này hữu ích?

| Điểm nổi bật | Giá trị |
|---|---|
| **Minh bạch** | Xem được tool nào đã được gọi, tham số và kết quả của từng bước |
| **Phối hợp nhiều tool** | Kết quả của tool trước trở thành dữ liệu cho quyết định tiếp theo |
| **Đa nhà cung cấp** | Dùng cùng một Agent với Gemini, Claude hoặc OpenAI |
| **Dễ mở rộng** | Thêm tool mới bằng một `ToolSpec`, không cần sửa vòng lặp Agent |
| **Có lớp an toàn cơ bản** | Giới hạn số bước, bắt lỗi tool và máy tính không dùng `eval()` |
| **Hai cách sử dụng** | Giao diện web Streamlit và CLI trong terminal |
| **Hội thoại nhiều lượt** | Agent giữ lịch sử cho đến khi người dùng đặt lại cuộc trò chuyện |

> Đây là project học tập: code ưu tiên sự rõ ràng, dễ đọc và dễ thử nghiệm hơn độ phức tạp của một hệ thống production.

<a id="kien-truc-he-thong"></a>
## Kiến trúc hệ thống

Project tách phần điều phối Agent khỏi SDK của từng hãng. Mọi provider đều được chuyển về cùng một định dạng tin nhắn chuẩn hóa, nhờ đó `Agent` không cần biết model phía sau là Gemini, Claude hay OpenAI.

```mermaid
flowchart TB
    U["Người dùng"]

    subgraph I["Lớp giao diện"]
        WEB["Streamlit UI<br/>app.py"]
        CLI["Terminal CLI<br/>scripts/chat_cli.py"]
    end

    subgraph C["Agent Core"]
        AGENT["Agent Loop<br/>agent.py"]
        PROMPT["Prompt Library<br/>prompts.py"]
        CONFIG["Settings<br/>config.py"]
        ADAPTER["Provider Adapters<br/>providers.py"]
        REGISTRY["Tool Package<br/>tools/"]
    end

    subgraph L["Nhà cung cấp LLM"]
        GEMINI["Gemini"]
        CLAUDE["Claude"]
        OPENAI["OpenAI"]
    end

    subgraph T["Công cụ mặc định"]
        PDF["search_knowledge_base"]
        CALC["calculator"]
        FX["convert_currency"]
    end

    U --> WEB
    U --> CLI
    WEB --> AGENT
    CLI --> AGENT
    CONFIG -. cấu hình .-> WEB
    CONFIG -. cấu hình .-> CLI
    PROMPT -. system prompt .-> AGENT
    AGENT <--> ADAPTER
    ADAPTER <--> GEMINI
    ADAPTER <--> CLAUDE
    ADAPTER <--> OPENAI
    AGENT <--> REGISTRY
    REGISTRY --> PDF
    REGISTRY --> CALC
    REGISTRY --> FX

    classDef interface fill:#E0F2FE,stroke:#0284C7,color:#0C4A6E;
    classDef core fill:#F3E8FF,stroke:#9333EA,color:#581C87;
    classDef provider fill:#FFF7ED,stroke:#EA580C,color:#7C2D12;
    classDef tool fill:#DCFCE7,stroke:#16A34A,color:#14532D;
    class WEB,CLI interface;
    class AGENT,PROMPT,CONFIG,ADAPTER,REGISTRY core;
    class GEMINI,CLAUDE,OPENAI provider;
    class PDF,CALC,FX tool;
```

### Vai trò của từng thành phần

| Thành phần | Trách nhiệm |
|---|---|
| `app.py` | Hiển thị chat, trạng thái gọi tool, lịch sử và cấu hình đang dùng |
| `agent_core/agent.py` | Quản lý lịch sử hội thoại và vòng lặp điều phối tool |
| `agent_core/prompts.py` | Quản lý system prompt mặc định, tách khỏi logic điều phối |
| `agent_core/providers.py` | Chuyển đổi định dạng chung sang API của Gemini, Anthropic và OpenAI |
| `agent_core/tools/` | Chứa kiểu dữ liệu chung, registry và implementation riêng của từng tool |
| `agent_core/config.py` | Đọc `.env`, kiểm tra provider và API key đang hoạt động |
| `scripts/chat_cli.py` | Chạy Agent trực tiếp trong terminal để thử nghiệm nhanh |

<a id="agent-hoat-dong-nhu-the-nao"></a>
## Agent hoạt động như thế nào?

Mỗi câu hỏi đi qua chu trình **Think → Act → Observe**. Model có thể trả lời ngay, gọi một tool, hoặc gọi nhiều tool song song trong cùng một lượt. Sau khi nhận kết quả tool, model tiếp tục quyết định cho đến khi có câu trả lời cuối hoặc chạm giới hạn `AGENT_MAX_STEPS`.

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Agent as Agent Loop
    participant LLM as LLM Provider
    participant Tools as Tool Registry

    User->>Agent: Gửi câu hỏi
    loop Tối đa AGENT_MAX_STEPS vòng
        Agent->>LLM: System prompt + lịch sử + JSON Schema của tools
        LLM-->>Agent: Văn bản hoặc danh sách tool_calls
        alt Model yêu cầu gọi tool
            Agent->>Tools: run(tool_name, arguments)
            Tools-->>Agent: Kết quả dạng văn bản
            Note over Agent: Ghi kết quả vào lịch sử để model quan sát
        else Model trả lời trực tiếp
            Agent-->>User: AgentResult(text, steps)
        end
    end
```

`steps` lưu lại tên tool, tham số và kết quả của mỗi lần gọi. Streamlit dùng dữ liệu này để hiển thị mục **“Agent đã làm gì?”** dưới câu trả lời.

<a id="bat-dau-nhanh"></a>
## Bắt đầu nhanh

### Yêu cầu

- Python **3.10+**
- Một API key của **Gemini**, **Anthropic** hoặc **OpenAI**
- Git và PowerShell nếu dùng script cài đặt nhanh trên Windows

### 1. Clone repository

```bash
git clone https://github.com/TanMinhNgo/agent-series.git
cd agent-series
```

### 2. Cài đặt

<details open>
<summary><strong>Windows — cách nhanh nhất</strong></summary>

```powershell
.\run.ps1
```

Script sẽ tạo `.venv`, cài dependencies, tạo `.env` từ file mẫu nếu cần và mở Streamlit. Lần chạy đầu tiên, hãy điền API key vào `.env` rồi chạy lại script.

</details>

<details>
<summary><strong>Windows — cài đặt thủ công</strong></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

</details>

### 3. Cấu hình API key

Mở `.env`, chọn một provider và điền key tương ứng:

```dotenv
LLM_PROVIDER=gemini

GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-flash-latest
```

> **Bảo mật:** `.env` đã được thêm vào `.gitignore`. Không commit, chụp màn hình hoặc chia sẻ API key công khai.

### 4. Chạy ứng dụng

Giao diện web:

```bash
streamlit run app.py
```

CLI — hỏi một câu rồi thoát:

```bash
python scripts/chat_cli.py "15% của 2.000.000 là bao nhiêu, rồi đổi sang USD?"
```

CLI — trò chuyện liên tục:

```bash
python scripts/chat_cli.py
```

<a id="rag-postgres"></a>
## Chạy bản Agent RAG có lưu lịch sử

Phiên bản hiện tại lưu chat, metadata tài liệu và vector embedding vào **PostgreSQL + pgvector**. PDF chỉ đi vào knowledge base qua upload UI; agent không còn được đọc một đường dẫn PDF bất kỳ trên máy.

### 1. Khởi động database

Cần cài Docker Desktop. Tại thư mục gốc project:

```powershell
docker compose up -d
```

Docker tạo PostgreSQL local tại `localhost:5433`, database `agent_series`. Host port `5433` tránh xung đột với PostgreSQL thường đã chạy ở `5432`. Dữ liệu nằm trong Docker volume `agent_series_postgres`, nên vẫn còn sau khi dừng container.

### 2. Cài dependency và tạo schema

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

Nếu chưa có môi trường ảo, chạy `./run.ps1`. Script này tự tạo `.venv`/`.env`, khởi động Docker Compose và áp migration trước khi mở Streamlit.

### 3. Cấu hình provider và model

Trong `.env`, điền key cho provider bạn muốn dùng. UI chỉ hiện provider có key hợp lệ. Mỗi biến `*_MODELS` là allowlist model có thể chọn trong Streamlit:

```dotenv
GEMINI_API_KEY=...
GEMINI_MODELS=gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite

OPENAI_API_KEY=...
OPENAI_MODELS=gpt-5.6-sol,gpt-5.6-terra,gpt-5.6-luna,gpt-4o-mini
```

Model được nhóm theo vai trò để dễ chọn:

| Provider | Mạnh nhất | Cân bằng | Nhanh/tiết kiệm |
|---|---|---|---|
| Gemini | `gemini-3.1-pro-preview` | `gemini-3.6-flash`, `gemini-3.5-flash` | `gemini-3.5-flash-lite` |
| Anthropic | `claude-fable-5`, `claude-opus-4-8` | `claude-sonnet-5` | `claude-haiku-4-5` |
| OpenAI | `gpt-5.6-sol` | `gpt-5.6-terra` | `gpt-5.6-luna` |

Model phải được tài khoản API của bạn cấp quyền. Với provider nào chưa có key, UI sẽ không hiện provider đó.

- Đổi model trong **cùng provider** giữ nguyên lịch sử chat.
- Đổi sang **provider khác** yêu cầu tạo chat mới; chat cũ vẫn xuất hiện trong lịch sử.
- Không nhập API key trên UI và không commit `.env`.

### 4. Upload, index và hỏi PDF

```powershell
streamlit run app.py
```

1. Ở ô chat phía dưới, bấm nút đính kèm và chọn một hoặc nhiều PDF, tối đa 25 MB mỗi file.
2. Gửi kèm câu hỏi hoặc chỉ gửi file. App sẽ tự lưu và index. Lần đầu `sentence-transformers` tải model `intfloat/multilingual-e5-small` về máy.
3. Chờ trạng thái tài liệu là `ready`, sau đó hỏi về nội dung trong ô chat. Câu trả lời dựa trên tài liệu sẽ nêu tên file và số trang.

PDF scan không có text layer sẽ báo lỗi; cần OCR trước. Upload trùng nội dung được nhận diện bằng SHA-256 để không index lặp.

Để index PDF đã đặt thủ công trong `knowledge/`:

```powershell
python scripts/ingest.py
```

`knowledge/` và dữ liệu runtime đều nằm trong `.gitignore`; không đưa tài liệu nhạy cảm vào Git.

### 5. Kiểm tra hệ thống

```powershell
pytest -q
```

Test không gọi API LLM thật. Trước khi dùng, kiểm tra PostgreSQL đang chạy bằng `docker compose ps`.

<a id="cach-su-dung"></a>
## Cách sử dụng

Thử các prompt sau để quan sát cách Agent chọn và phối hợp công cụ:

| Prompt mẫu | Luồng dự kiến |
|---|---|
| `100 USD đổi ra bao nhiêu VND?` | `convert_currency` |
| `15% của 2.000.000 là bao nhiêu?` | `calculator` |
| `15% của 2.000.000 là bao nhiêu, rồi đổi sang USD?` | `calculator` → `convert_currency` |
| `Tóm tắt chính sách hoàn tiền trong tài liệu đã upload` | `search_knowledge_base` → trả lời kèm nguồn/trang |
| `Từ số liệu trong PDF đã upload, tính 15% tổng tiền` | `search_knowledge_base` → `calculator` |
| `Xin chào, bạn có thể làm gì?` | Trả lời trực tiếp, không cần tool |

Trong giao diện Streamlit:

1. Thanh bên dùng để tạo/chọn chat, xem các PDF đã index và đổi giao diện.
2. Thanh điều khiển ngay trên ô chat dùng để chọn provider/model. Đổi model cùng provider giữ lịch sử; đổi provider tạo chat mới.
3. Dùng nút đính kèm trong ô chat để upload PDF. App index PDF trước khi gửi câu hỏi tới Agent.
4. Trạng thái xử lý cập nhật ngay khi Agent gọi hoặc nhận kết quả từ tool. Chat được lưu trong PostgreSQL và có thể mở lại sau khi restart app.

### Giao diện Light, Dark và System

Mở mục **Appearance** ở sidebar và chọn một trong ba chế độ:

| Chế độ | Hành vi |
|---|---|
| `System` | Tự theo giao diện sáng/tối của hệ điều hành hoặc trình duyệt |
| `Light` | Luôn dùng giao diện sáng, phù hợp khi đọc tài liệu dài |
| `Dark` | Luôn dùng giao diện tối, phù hợp môi trường thiếu sáng |

Lựa chọn được lưu trong localStorage của trình duyệt hiện tại. Nó không được lưu vào PostgreSQL và không đồng bộ giữa các trình duyệt, vì project chưa có tài khoản người dùng.

<a id="nha-cung-cap-llm"></a>
## Nhà cung cấp LLM

Chỉ cần đổi `LLM_PROVIDER` trong `.env`; vòng lặp Agent và các tool không thay đổi.

| Provider | Giá trị cấu hình | Biến API key | Model mặc định trong project |
|---|---|---|---|
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-3.5-flash` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-5.6-terra` |

Ví dụ chuyển sang Anthropic:

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-haiku-4-5
```

> Tên model, quyền truy cập và chi phí phụ thuộc tài khoản của từng nhà cung cấp. Nếu model mặc định không khả dụng, hãy đổi biến `*_MODEL` sang model mà tài khoản của bạn được cấp.

<a id="cau-hinh"></a>
## Cấu hình

| Biến | Mặc định | Mô tả |
|---|---:|---|
| `LLM_PROVIDER` | `gemini` | Provider đang hoạt động: `gemini`, `anthropic` hoặc `openai` |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Model mặc định cho Gemini adapter |
| `GEMINI_MODELS` | theo `GEMINI_MODEL` | Allowlist model Gemini hiện trên UI |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Model mặc định cho Anthropic adapter |
| `ANTHROPIC_MODELS` | theo `ANTHROPIC_MODEL` | Allowlist model Anthropic hiện trên UI |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Model mặc định cho OpenAI adapter |
| `OPENAI_MODELS` | theo `OPENAI_MODEL` | Allowlist model OpenAI hiện trên UI |
| `DATABASE_URL` | PostgreSQL local | Kết nối PostgreSQL + pgvector |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Model embedding local cho RAG |
| `AGENT_TEMPERATURE` | `0.2` | Độ ngẫu nhiên thấp để quyết định gọi tool ổn định hơn |
| `AGENT_MAX_STEPS` | `5` | Số vòng suy luận tối đa cho mỗi yêu cầu |
| `AGENT_MAX_TOKENS` | `2048` | Giới hạn token đầu ra mỗi lượt ở adapter có sử dụng giá trị này |

Project chỉ hiện provider có API key hợp lệ; các key còn lại có thể để trống.

### Quản lý prompt

System prompt mặc định nằm riêng tại `agent_core/prompts.py`, giúp thay đổi chỉ dẫn cho model mà không chạm vào vòng lặp điều phối. Có thể sửa prompt mặc định cho toàn ứng dụng hoặc truyền một prompt khác khi khởi tạo Agent:

```python
from agent_core import Agent

agent = Agent(
    client=client,
    registry=registry,
    system_prompt="Bạn là trợ lý phân tích tài liệu và luôn trích dẫn nguồn.",
)
```

Với nhiều persona hoặc use case, hãy khai báo thêm các hằng prompt trong `prompts.py` và chọn prompt tại composition root (`app.py` hoặc CLI), thay vì đặt chuỗi prompt rải rác trong code.

<a id="bo-cong-cu"></a>
## Bộ công cụ mặc định

| Tool | Input chính | Công dụng | Giới hạn hiện tại |
|---|---|---|---|
| `search_knowledge_base` | `query`, `top_k` | Truy hồi PDF đã upload/index | Chỉ tìm text layer, trả nguồn/tên file/số trang |
| `calculator` | `expression` | Tính biểu thức số học bằng AST | Chỉ cho phép số và các toán tử cơ bản |
| `convert_currency` | `amount`, `from_currency`, `to_currency` | Quy đổi USD, VND, EUR, JPY, GBP, CNY | Dùng bảng tỷ giá minh họa cố định, không phải dữ liệu thời gian thực |

### Một số quyết định thiết kế

- **Máy tính dùng AST:** từ chối tên biến, gọi hàm và câu lệnh tùy ý; an toàn hơn nhiều so với chạy `eval()` trên dữ liệu do model tạo.
- **Tool luôn trả về chuỗi:** cả kết quả thành công lẫn lỗi đều có thể được LLM đọc và phản hồi ở vòng tiếp theo.
- **Giới hạn số bước:** ngăn Agent lặp vô hạn, treo ứng dụng hoặc tiêu thụ quota ngoài ý muốn.
- **Adapter chuẩn hóa provider:** một vòng lặp Agent dùng chung cho ba SDK khác nhau.
- **Tắt automatic function calling của Gemini:** project tự điều khiển vòng lặp để người học quan sát được từng bước.
- **Giữ `thought_signature` của Gemini:** chữ ký được phát lại cùng function call ở lượt sau theo yêu cầu của SDK/model tương ứng.

<a id="them-tool-moi"></a>
## Thêm tool mới

Mỗi tool nằm trong một module riêng và gồm bốn phần: tên, mô tả để model biết **khi nào nên gọi**, JSON Schema của tham số và hàm Python thực thi.

Ví dụ tạo `agent_core/tools/current_time.py`:

```python
from datetime import datetime

from .base import ToolSpec


def get_current_time() -> str:
    return datetime.now().astimezone().isoformat()


CURRENT_TIME_TOOL = ToolSpec(
    name="get_current_time",
    description="Trả về thời gian hiện tại khi người dùng hỏi ngày hoặc giờ.",
    parameters={
        "type": "object",
        "properties": {},
    },
    func=get_current_time,
)
```

Sau đó đăng ký spec tại `agent_core/tools/defaults.py`:

```python
from .current_time import CURRENT_TIME_TOOL

DEFAULT_TOOLS = (
    CALCULATOR_TOOL,
    CURRENCY_TOOL,
    CURRENT_TIME_TOOL,
)
```

Tool mới sẽ tự động được chuyển sang định dạng phù hợp với provider đang dùng. Với RAG, `search_knowledge_base` được tạo từ `KnowledgeService` tại `app.py`/CLI vì nó cần database và embedding model.

<a id="cau-truc-thu-muc"></a>
## Cấu trúc thư mục

```text
AI_AGENT_FROM_ZERO/
├── agent_core/
│   ├── tools/
│   │   ├── __init__.py      # Public API ổn định của tools package
│   │   ├── base.py          # ToolSpec trung lập với provider
│   │   ├── registry.py      # Đăng ký và thực thi tool an toàn
│   │   ├── defaults.py      # Danh sách tool bật mặc định
│   │   ├── calculator.py    # Máy tính giới hạn bằng AST
│   │   ├── currency.py      # Quy đổi tiền tệ minh họa
│   │   └── pdf_reader.py    # Tiện ích PDF mức thấp, không expose mặc định
│   ├── knowledge.py          # Upload, index và truy hồi pgvector
│   └── storage.py            # SQLAlchemy models/repository cho chat và tài liệu
│   ├── __init__.py          # Public API và phiên bản package
│   ├── agent.py             # Vòng lặp Agent và lịch sử hội thoại
│   ├── prompts.py           # System prompts dùng bởi Agent
│   ├── config.py            # Đọc và kiểm tra cấu hình môi trường
│   └── providers.py         # Adapter Gemini / Anthropic / OpenAI
├── scripts/
│   └── chat_cli.py          # Giao diện dòng lệnh
├── app.py                   # Giao diện chat Streamlit
├── run.ps1                  # Cài đặt và chạy nhanh trên Windows
├── requirements.txt         # Python dependencies
├── .env.example             # Mẫu cấu hình, không chứa secret
├── .gitignore
└── README.md
```

Để đọc code theo luồng dễ hiểu nhất: `config.py` → `prompts.py` → `tools/` → `providers.py` → `agent.py` → `app.py`.

<a id="gioi-han-va-an-toan"></a>
## Giới hạn và lưu ý an toàn

- `convert_currency` phục vụ demo luồng tool; **không dùng kết quả cho giao dịch tài chính**.
- Knowledge base chỉ index PDF có lớp văn bản. PDF ảnh scan cần OCR trước.
- Đường dẫn PDF được Agent mở trên chính máy đang chạy ứng dụng; chỉ sử dụng file bạn tin cậy.
- Nội dung PDF được gửi tới provider LLM trong lịch sử hội thoại. Không dùng tài liệu nhạy cảm nếu chưa đánh giá chính sách dữ liệu của provider.
- Project chưa có sandbox riêng cho tool tùy chỉnh. Hãy kiểm tra chặt input và quyền truy cập khi thêm tool có tác động hệ thống.
- Lịch sử nằm trong bộ nhớ tiến trình, chưa được lưu bền vững sau khi ứng dụng khởi động lại.

<a id="xu-ly-loi-thuong-gap"></a>
## Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Thiếu ..._API_KEY` | Chưa tạo `.env` hoặc chọn sai provider | Sao chép `.env.example`, điền key và kiểm tra `LLM_PROVIDER` |
| `ModuleNotFoundError` | Chưa cài dependencies hoặc chưa kích hoạt `.venv` | Kích hoạt môi trường ảo rồi chạy `pip install -r requirements.txt` |
| `Không tìm thấy file` | Đường dẫn PDF sai hoặc app không có quyền đọc | Dùng đường dẫn tuyệt đối và kiểm tra quyền truy cập |
| PDF không trích được chữ | PDF là ảnh scan | Chạy OCR trước hoặc bổ sung một OCR tool |
| Lỗi model không tồn tại | Tài khoản không có quyền với model đã cấu hình | Đổi biến `*_MODEL` trong `.env` |
| `429`, quota hoặc rate limit | Hết quota hoặc gửi quá nhiều yêu cầu | Chờ rồi thử lại, đổi model hoặc kiểm tra billing |
| Agent dừng trước khi xong | Đã chạm `AGENT_MAX_STEPS` | Viết prompt rõ hơn hoặc tăng giới hạn có kiểm soát |

<a id="bai-tap-mo-rong"></a>
## Bài tập mở rộng

- [ ] Thêm tool `get_current_time` không cần API bên ngoài.
- [ ] Thay bảng tỷ giá cố định bằng một API tỷ giá thời gian thực.
- [ ] Thêm OCR cho PDF scan.
- [ ] Kết nối `search_knowledge_base` để biến pipeline RAG thành một tool.
- [ ] Lưu lịch sử hội thoại vào SQLite.
- [ ] Thêm timeout, retry và telemetry cho mỗi lần gọi tool.
- [ ] Viết unit test cho `calculator`, `ToolRegistry` và vòng lặp Agent.
- [ ] Chạy tool trong sandbox trước khi dùng cho môi trường production.

<a id="dong-gop"></a>
## Đóng góp

Issue và pull request đều được chào đón. Một luồng đóng góp gợi ý:

```bash
git checkout -b feature/ten-tinh-nang
git commit -m "feat: mô tả thay đổi"
git push origin feature/ten-tinh-nang
```

Khi thêm provider hoặc tool mới, hãy giữ interface chuẩn hóa hiện tại và bổ sung ví dụ sử dụng vào README.

---

<div align="center">

Được xây dựng để học cách AI Agent thực sự điều phối công cụ — từng bước một.

Nếu project hữu ích, hãy star repository để ủng hộ series.

</div>
