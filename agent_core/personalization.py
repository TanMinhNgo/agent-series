"""User feedback and lightweight, local response-personalization signals."""

from __future__ import annotations

from sqlalchemy import select

from .storage import ChatMessage, Database, ResponseFeedback, UserPreference, current_user_id

FEEDBACK_STYLES = {
    "too_long": "concise",
    "too_short": "detailed",
    "unclear": "structured",
    "wrong_style": "practical",
}
TOPIC_KEYWORDS = {
    "software_engineering": ("code", "lập trình", "react", "typescript", "api", "backend", "frontend", "database", "docker", "framework", "bug", "codebase"),
    "systems_architecture": ("kiến trúc", "hệ thống", "system design", "microservice", "redis", "queue", "deploy", "cloud"),
    "ai_rag_data": ("ai", "rag", "embedding", "llm", "model", "vector", "machine learning", "dữ liệu"),
    "product_business": ("sản phẩm", "product", "khách hàng", "business", "doanh thu", "marketing"),
}


class PersonalizationService:
    def __init__(self, database: Database):
        self.database = database

    def observe_user_message(self, content: str) -> None:
        user_id = current_user_id.get()
        if not user_id or not content.strip():
            return
        lowered = content.lower()
        matched = [topic for topic, words in TOPIC_KEYWORDS.items() if any(word in lowered for word in words)]
        if not matched:
            return
        with self.database.session() as session:
            profile = session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
            if profile is None:
                profile = UserPreference(user_id=user_id, style_scores={}, topic_counts={})
                session.add(profile)
            counts = dict(profile.topic_counts or {})
            for topic in matched:
                counts[topic] = int(counts.get(topic, 0)) + 1
            profile.topic_counts = counts
            session.commit()

    def record_feedback(self, message_id: str, kind: str, note: str | None = None) -> ResponseFeedback:
        if kind not in {"helpful", "incorrect", *FEEDBACK_STYLES}:
            raise ValueError("Loại đánh giá không hợp lệ.")
        user_id = current_user_id.get()
        if not user_id:
            raise ValueError("Cần đăng nhập để đánh giá phản hồi.")
        with self.database.session() as session:
            message = session.get(ChatMessage, message_id)
            if message is None or message.role != "assistant":
                raise ValueError("Chỉ có thể đánh giá phản hồi AI của bạn.")
            feedback = session.scalar(
                select(ResponseFeedback).where(
                    ResponseFeedback.user_id == user_id,
                    ResponseFeedback.message_id == message_id,
                )
            )
            previous_kind = feedback.kind if feedback is not None else None
            if feedback is None:
                feedback = ResponseFeedback(user_id=user_id, message_id=message_id, kind=kind, note=(note or "").strip()[:2000] or None)
                session.add(feedback)
            else:
                feedback.kind, feedback.note = kind, (note or "").strip()[:2000] or None
            profile = session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
            if profile is None:
                profile = UserPreference(user_id=user_id, style_scores={}, topic_counts={})
                session.add(profile)
            scores = dict(profile.style_scores or {})
            previous_style = FEEDBACK_STYLES.get(previous_kind or "")
            if previous_style:
                scores[previous_style] = max(0, int(scores.get(previous_style, 0)) - 1)
            style = FEEDBACK_STYLES.get(kind)
            if style:
                scores[style] = int(scores.get(style, 0)) + 1
            profile.style_scores = scores
            session.commit()
            return feedback

    def context(self) -> str:
        user_id = current_user_id.get()
        if not user_id:
            return ""
        with self.database.session() as session:
            profile = session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
        if profile is None:
            return ""
        styles = [name for name, count in (profile.style_scores or {}).items() if int(count) > 0]
        topics = [name.replace("_", " ") for name, count in (profile.topic_counts or {}).items() if int(count) >= 3]
        if not styles and not topics:
            return ""
        parts = ["Cá nhân hóa từ hành vi và đánh giá trước đây (chỉ áp dụng khi phù hợp):"]
        if styles:
            parts.append("Phong cách ưu tiên: " + ", ".join(styles) + ".")
        if topics:
            parts.append("Người dùng thường hỏi về: " + ", ".join(topics) + ". Hãy ưu tiên trả lời thực chiến theo lĩnh vực này.")
        return "\n".join(parts)
