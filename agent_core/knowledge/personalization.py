"""User feedback and lightweight, local response-personalization signals."""

from __future__ import annotations

from sqlalchemy import select

from ..persistence.store import ChatMessage, Database, ResponseFeedback, UserPreference, current_user_id

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
        user_id = self._validate_feedback_request(kind)
        with self.database.session() as session:
            self._require_assistant_message(session, message_id)
            feedback, previous_kind = self._save_feedback(session, user_id, message_id, kind, note)
            profile = self._preference_profile(session, user_id)
            self._update_style_scores(profile, previous_kind, kind)
            session.commit()
            return feedback

    @staticmethod
    def _validate_feedback_request(kind: str) -> str:
        if kind not in {"helpful", "incorrect", *FEEDBACK_STYLES}:
            raise ValueError("Loại đánh giá không hợp lệ.")
        user_id = current_user_id.get()
        if not user_id:
            raise ValueError("Cần đăng nhập để đánh giá phản hồi.")
        return user_id

    @staticmethod
    def _require_assistant_message(session, message_id: str) -> None:
        message = session.get(ChatMessage, message_id)
        if message is None or message.role != "assistant":
            raise ValueError("Chỉ có thể đánh giá phản hồi AI của bạn.")

    @staticmethod
    def _save_feedback(session, user_id: str, message_id: str, kind: str, note: str | None) -> tuple[ResponseFeedback, str | None]:
        feedback = session.scalar(select(ResponseFeedback).where(ResponseFeedback.user_id == user_id, ResponseFeedback.message_id == message_id))
        previous_kind = feedback.kind if feedback is not None else None
        cleaned_note = (note or "").strip()[:2000] or None
        if feedback is None:
            feedback = ResponseFeedback(user_id=user_id, message_id=message_id, kind=kind, note=cleaned_note)
            session.add(feedback)
        else:
            feedback.kind, feedback.note = kind, cleaned_note
        return feedback, previous_kind

    @staticmethod
    def _preference_profile(session, user_id: str) -> UserPreference:
        profile = session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
        if profile is None:
            profile = UserPreference(user_id=user_id, style_scores={}, topic_counts={})
            session.add(profile)
        return profile

    @staticmethod
    def _update_style_scores(profile: UserPreference, previous_kind: str | None, kind: str) -> None:
        scores = dict(profile.style_scores or {})
        previous_style = FEEDBACK_STYLES.get(previous_kind or "")
        if previous_style:
            scores[previous_style] = max(0, int(scores.get(previous_style, 0)) - 1)
        style = FEEDBACK_STYLES.get(kind)
        if style:
            scores[style] = int(scores.get(style, 0)) + 1
        profile.style_scores = scores

    def feedback_by_message_ids(self, message_ids: list[str]) -> dict[str, str]:
        """Return the current user's saved feedback for a batch of assistant turns."""
        if not message_ids or not current_user_id.get():
            return {}
        with self.database.session() as session:
            feedback = session.scalars(
                select(ResponseFeedback).where(ResponseFeedback.message_id.in_(message_ids))
            ).all()
        return {item.message_id: item.kind for item in feedback}

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
