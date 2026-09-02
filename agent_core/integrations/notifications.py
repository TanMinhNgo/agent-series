"""SMTP notifications for finished schedule runs."""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urlparse

from ..runtime.config import Settings

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
SMTP_TIMEOUT_SECONDS = 15


class EmailDeliveryError(RuntimeError):
    """Raised when an email could not be delivered, with credentials stripped."""


def public_chat_url(app_web_url: str, chat_id: str) -> str | None:
    """Build a chat link only when the app is reachable outside this machine."""
    hostname = urlparse(app_web_url).hostname
    if not hostname or hostname.lower() in LOCAL_HOSTS:
        return None
    return f"{app_web_url}/chat/{chat_id}"


class EmailNotificationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_from)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.enabled:
            raise EmailDeliveryError("SMTP chưa được cấu hình.")
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as client:
                if self.settings.smtp_use_tls:
                    client.starttls()
                if self.settings.smtp_username:
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # SMTPAuthenticationError can echo the submitted credentials, so the
            # class name is the only detail safe to surface or persist.
            raise EmailDeliveryError(f"Không gửi được email ({type(exc).__name__}).") from exc


def schedule_run_email(title: str, ran_at: datetime, summary: str | None, chat_url: str | None) -> tuple[str, str]:
    """Compose the short completion notice for one finished schedule run."""
    lines = [
        f"Lịch trình \"{title}\" đã chạy xong lúc {ran_at.strftime('%H:%M %d/%m/%Y')} (UTC).",
        "",
        summary.strip() if summary and summary.strip() else "(Không có tóm tắt.)",
    ]
    if chat_url:
        lines += ["", f"Mở chat: {chat_url}"]
    return f"[Lịch trình] {title}", "\n".join(lines)
