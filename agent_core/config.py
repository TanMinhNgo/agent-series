"""Cấu hình tập trung cho AI Agent — đọc mọi thứ từ file .env về một đối tượng.

Ý tưởng giống hệt bài RAG: gom hết cấu hình (API key, tên model, tham số) vào MỘT
chỗ duy nhất, các module khác chỉ nhận `Settings` mà không cần biết biến môi trường
nằm ở đâu. Nhờ vậy đổi provider / đổi model chỉ cần sửa .env, không đụng vào code.

Điểm mới so với bài RAG: agent này hỗ trợ NHIỀU nhà cung cấp LLM (provider). Bạn chỉ
cần điền key của provider mình có (Gemini / Claude / OpenAI) rồi đặt LLM_PROVIDER cho
đúng. Mặc định dùng Gemini vì nó tái sử dụng luôn API key của project RAG.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

# Thư mục gốc của project agent = lùi 1 cấp từ file này: agent_core/config.py -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Nạp biến môi trường từ .env ở gốc project agent (nếu có).
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Toàn bộ cấu hình của agent, gom về một chỗ (immutable cho an toàn)."""

    # --- Chọn nhà cung cấp LLM đang dùng: cloud hoặc Ollama local ---
    provider: str

    # --- API key + tên model cho TỪNG provider (chỉ cái đang chọn mới bắt buộc) ---
    gemini_api_key: str
    gemini_model: str
    anthropic_api_key: str
    anthropic_model: str
    openai_api_key: str
    openai_model: str
    ollama_base_url: str
    ollama_model: str

    # --- Tham số điều khiển "bộ não" của agent ---
    # temperature: độ "sáng tạo/ngẫu nhiên" của model. Với AGENT ta để THẤP (0.0–0.3)
    #   vì mục tiêu là ra quyết định gọi tool ỔN ĐỊNH, ít bịa; không cần văn hoa.
    temperature: float
    # max_steps: số vòng "suy nghĩ -> gọi tool -> quan sát" tối đa cho mỗi câu hỏi.
    #   Đây là "phanh an toàn": nếu model lỡ lặp vô hạn (gọi tool mãi không dừng) thì
    #   vẫn thoát ra được, tránh treo và tránh đốt quota. 5 là đủ cho demo nhiều tool.
    max_steps: int
    # max_tokens: giới hạn độ dài câu trả lời model sinh ra mỗi lượt. Đặt vừa phải để
    #   không tốn quota vô ích; Anthropic BẮT BUỘC tham số này nên ta luôn khai báo.
    max_tokens: int
    database_url: str
    embedding_model: str
    hf_token: str
    tavily_api_key: str
    knowledge_dir: Path
    media_dir: Path
    imagekit_private_key: str
    imagekit_url_endpoint: str
    provider_models: dict[str, tuple[str, ...]]
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_redirect_uri: str
    google_auth_client_id: str
    google_auth_client_secret: str
    google_auth_redirect_uri: str
    connector_encryption_key: str
    github_app_id: str
    github_app_slug: str
    github_app_private_key: str
    github_app_install_url: str
    user_credential_encryption_key: str
    app_web_url: str
    system_admin_email: str
    auth_session_days: int
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool

    # ---- Vài tiện ích đọc nhanh cấu hình của provider đang chọn ----
    @property
    def active_api_key(self) -> str:
        return {
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "ollama": "",
        }[self.provider]

    @property
    def active_model(self) -> str:
        return {
            "gemini": self.gemini_model,
            "anthropic": self.anthropic_model,
            "openai": self.openai_model,
            "ollama": self.ollama_model,
        }[self.provider]

    def configured_provider_models(self) -> dict[str, tuple[str, ...]]:
        """Return only providers that have a usable key and model allowlist."""
        return {
            provider: models
            for provider, models in self.provider_models.items()
            if models and {
                "gemini": self.gemini_api_key,
                "anthropic": self.anthropic_api_key,
                "openai": self.openai_api_key,
            }[provider]
        }

    def with_provider_model(self, provider: str, model: str, api_key: str | None = None) -> "Settings":
        """Create settings for a model selected in the UI without exposing keys."""
        if provider == "ollama":
            if not model.strip():
                raise ValueError("Bạn chưa chọn model Ollama.")
            return replace(self, provider=provider, ollama_model=model)
        if provider not in self.provider_models or model not in self.provider_models[provider]:
            raise ValueError("Provider hoặc model chưa được hệ thống cho phép.")
        resolved_key = api_key or {"gemini": self.gemini_api_key, "anthropic": self.anthropic_api_key, "openai": self.openai_api_key}[provider]
        if not resolved_key:
            raise ValueError("Bạn chưa thêm API key cho provider này.")
        field_name = f"{provider}_model"
        key_field = f"{provider}_api_key"
        return replace(self, provider=provider, **{field_name: model, key_field: resolved_key})


def _model_list(env_name: str, fallback: str) -> tuple[str, ...]:
    values = [item.strip() for item in os.getenv(env_name, fallback).split(",")]
    return tuple(dict.fromkeys(item for item in values if item))


def _env_or_fallback(env_name: str, fallback_env_name: str) -> str:
    """Use the primary value only when it is actually configured."""
    return os.getenv(env_name, "").strip() or os.getenv(fallback_env_name, "").strip()


def load_settings() -> Settings:
    """Đọc cấu hình từ môi trường và trả về đối tượng Settings.

    Ném lỗi RÕ RÀNG nếu thiếu key của provider đang chọn — để bạn biết ngay phải làm gì.
    """
    # .strip().lower() để tránh lỗi vặt do gõ dư dấu cách hoặc viết HOA trong .env
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    if provider not in {"gemini", "anthropic", "openai", "ollama"}:
        raise RuntimeError(
            f"LLM_PROVIDER='{provider}' không hợp lệ. "
            "Chỉ nhận: gemini | anthropic | openai | ollama (sửa trong .env)."
        )

    settings = Settings(
        provider=provider,
        # Gemini 3.5 Flash cân bằng tốt cho chat/tool calling ở bản mới.
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip(),
        # Anthropic (Claude): mặc định model mạnh nhất; muốn rẻ hơn đổi sang
        # 'claude-haiku-4-5' trong .env. Xem chú thích ở .env.example.
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip(),
        # OpenAI (Codex/GPT): mặc định model gọn nhẹ; bạn tự đổi theo model mình có.
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "").strip(),
        temperature=float(os.getenv("AGENT_TEMPERATURE", "0.2")),
        max_steps=int(os.getenv("AGENT_MAX_STEPS", "5")),
        max_tokens=int(os.getenv("AGENT_MAX_TOKENS", "2048")),
        database_url=os.getenv(
            "DATABASE_URL", "postgresql+psycopg://agent:agent@localhost:5433/agent_series"
        ).strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small").strip(),
        # sentence-transformers / huggingface_hub reads HF_TOKEN directly from
        # the environment; retain it here too so all runtime configuration has
        # one explicit, discoverable contract.
        hf_token=os.getenv("HF_TOKEN", "").strip(),
        tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        knowledge_dir=(PROJECT_ROOT / os.getenv("KNOWLEDGE_DIR", "knowledge").strip()).resolve(),
        media_dir=(PROJECT_ROOT / os.getenv("MEDIA_DIR", "uploads").strip()).resolve(),
        imagekit_private_key=os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip(),
        imagekit_url_endpoint=os.getenv("IMAGEKIT_URL_ENDPOINT", "").strip().rstrip("/"),
        provider_models={
            "gemini": _model_list("GEMINI_MODELS", os.getenv("GEMINI_MODEL", "gemini-3.5-flash")),
            "anthropic": _model_list("ANTHROPIC_MODELS", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")),
            "openai": _model_list("OPENAI_MODELS", os.getenv("OPENAI_MODEL", "gpt-5.6-terra")),
        },
        google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        google_oauth_redirect_uri=os.getenv(
            "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/connectors/google/callback"
        ).strip(),
        # Google Sign-In can reuse the same Google Cloud OAuth client as the
        # Workspace connector, but must have its own callback and narrow scopes.
        google_auth_client_id=_env_or_fallback("GOOGLE_AUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
        google_auth_client_secret=_env_or_fallback("GOOGLE_AUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
        google_auth_redirect_uri=os.getenv(
            "GOOGLE_AUTH_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
        ).strip(),
        connector_encryption_key=os.getenv("CONNECTOR_ENCRYPTION_KEY", "").strip(),
        github_app_id=os.getenv("GITHUB_APP_ID", "").strip(),
        github_app_slug=os.getenv("GITHUB_APP_SLUG", "").strip(),
        github_app_private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip(),
        github_app_install_url=os.getenv("GITHUB_APP_INSTALL_URL", "").strip(),
        user_credential_encryption_key=os.getenv("USER_CREDENTIAL_ENCRYPTION_KEY", "").strip(),
        app_web_url=os.getenv("APP_WEB_URL", "http://localhost:5173").strip().rstrip("/"),
        system_admin_email=os.getenv("SYSTEM_ADMIN_EMAIL", "").strip().lower(),
        auth_session_days=int(os.getenv("AUTH_SESSION_DAYS", "14")),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        smtp_from=os.getenv("SMTP_FROM", "").strip(),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false",
    )

    return settings
