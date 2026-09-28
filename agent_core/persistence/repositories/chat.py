from __future__ import annotations

import json
from datetime import datetime
from secrets import token_urlsafe
from uuid import uuid4

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from agent_core.persistence.database import Database
from agent_core.persistence.models import (
    ArtifactMessageLink,
    CHAT_NOT_FOUND_ERROR,
    Chat,
    ChatMessage,
    ChatShare,
    LibraryAsset,
    utc_now,
)


class ChatRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, provider: str, model: str, context_source_chat_id: str | None = None, project_id: str | None = None, collection_id: str | None = None, mode: str = "standard") -> Chat:
        with self.database.session() as session:
            chat = Chat(provider=provider, model=model, context_source_chat_id=context_source_chat_id, project_id=project_id, collection_id=collection_id, mode=mode)
            session.add(chat)
            session.commit()
            return chat

    def create_branch(self, chat_id: str, assistant_message_id: str) -> Chat:
        """Copy only the selected assistant turn and the user turn immediately before it."""
        with self.database.session() as session:
            parent = session.get(Chat, chat_id)
            if parent is None:
                raise ValueError(CHAT_NOT_FOUND_ERROR)
            assistant = session.get(ChatMessage, assistant_message_id)
            if assistant is None or assistant.chat_id != chat_id or assistant.role != "assistant":
                raise ValueError("Chỉ có thể mở nhánh từ phản hồi AI thuộc chat này.")
            user = session.scalar(
                select(ChatMessage)
                .where(
                    ChatMessage.chat_id == chat_id,
                    ChatMessage.role == "user",
                    ChatMessage.position < assistant.position,
                )
                .order_by(ChatMessage.position.desc())
                .limit(1)
            )
            if user is None:
                raise ValueError("Không tìm thấy câu hỏi đứng trước phản hồi này.")
            branch = Chat(
                title=user.content.strip()[:80] or "Nhánh hội thoại",
                provider=parent.provider,
                model=parent.model,
                mode=parent.mode,
                project_id=parent.project_id,
                collection_id=parent.collection_id,
                parent_chat_id=parent.id,
                branch_from_position=assistant.position,
            )
            session.add(branch)
            session.flush()
            for position, source in enumerate((user, assistant)):
                session.add(
                    ChatMessage(
                        chat_id=branch.id,
                        position=position,
                        role=source.role,
                        content=source.content,
                        attachments=source.attachments if source.role == "user" else None,
                        content_blocks=source.content_blocks if source.role == "assistant" else None,
                        sources=source.sources if source.role == "assistant" else None,
                        generated_asset_ids=source.generated_asset_ids if source.role == "assistant" else None,
                    )
                )
            session.commit()
            return branch

    def prepare_regeneration(self, chat_id: str, assistant_message_id: str) -> str:
        """Remove the latest exchange so streaming can recreate it without duplicate turns."""
        with self.database.session() as session:
            assistant = session.get(ChatMessage, assistant_message_id)
            if assistant is None or assistant.chat_id != chat_id or assistant.role != "assistant":
                raise ValueError("Không tìm thấy phản hồi AI cần tạo lại.")
            latest_position = session.scalar(
                select(func.max(ChatMessage.position)).where(ChatMessage.chat_id == chat_id)
            )
            if latest_position != assistant.position:
                raise ValueError("Chỉ có thể tạo lại phản hồi AI mới nhất.")
            user = session.scalar(
                select(ChatMessage)
                .where(
                    ChatMessage.chat_id == chat_id,
                    ChatMessage.role == "user",
                    ChatMessage.position < assistant.position,
                )
                .order_by(ChatMessage.position.desc())
                .limit(1)
            )
            if user is None:
                raise ValueError("Không tìm thấy câu hỏi đứng trước phản hồi này.")
            content = user.content
            session.execute(delete(ChatMessage).where(ChatMessage.chat_id == chat_id, ChatMessage.position >= user.position))
            session.commit()
            return content

    def set_message_pin(self, message_id: str, pinned: bool) -> ChatMessage | None:
        with self.database.session() as session:
            message = session.get(ChatMessage, message_id)
            if message is None or message.role != "user":
                return None
            message.pinned = pinned
            session.commit()
            return message

    def chat_pins(self, chat_id: str) -> list[ChatMessage]:
        with self.database.session() as session:
            return list(session.scalars(select(ChatMessage).where(
                ChatMessage.chat_id == chat_id,
                ChatMessage.role == "user",
                ChatMessage.pinned.is_(True),
            ).order_by(ChatMessage.position)).all())

    def list(self, offset: int = 0, limit: int = 40) -> tuple[list[Chat], int]:
        with self.database.session() as session:
            total = session.scalar(select(func.count()).select_from(Chat)) or 0
            chats = session.scalars(
                select(Chat)
                .order_by(desc(Chat.pinned), desc(Chat.updated_at))
                .offset(offset)
                .limit(limit)
            )
            return list(chats), total

    def get(self, chat_id: str) -> Chat | None:
        with self.database.session() as session:
            return session.get(Chat, chat_id)

    def replace_history(self, chat_id: str, history: list[dict]) -> list[dict]:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                raise ValueError(CHAT_NOT_FOUND_ERROR)
            existing = {
                item.id: item
                for item in session.scalars(select(ChatMessage).where(ChatMessage.chat_id == chat_id))
            }
            retained_ids = self._persist_history_messages(session, chat_id, history, existing)
            self._delete_removed_messages(session, existing, retained_ids)
            self._set_initial_chat_title(chat, history)
            chat.updated_at = utc_now()
            session.commit()
            return history

    def _persist_history_messages(self, session: Session, chat_id: str, history: list[dict], existing: dict[str, ChatMessage]) -> set[str]:
        retained_ids: set[str] = set()
        for position, item in enumerate(history):
            message_id = item.get("message_id") or str(uuid4())
            item["message_id"] = message_id
            retained_ids.add(message_id)
            self._persist_history_message(session, chat_id, existing.get(message_id), message_id, position, item)
        return retained_ids

    @staticmethod
    def _history_message_values(position: int, item: dict) -> dict:
        return {
            "position": position, "role": item["role"], "content": item.get("content", ""),
            "tool_call_id": item.get("id"), "tool_name": item.get("name"), "tool_calls": item.get("tool_calls"),
            "attachments": [{key: value for key, value in attachment.items() if key != "data"} for attachment in item.get("attachments", [])] or None,
            "content_blocks": item.get("content_blocks") or None, "sources": item.get("sources") or None,
            "generated_asset_ids": item.get("generated_asset_ids") or None,
        }

    def _persist_history_message(self, session: Session, chat_id: str, message: ChatMessage | None, message_id: str, position: int, item: dict) -> None:
        values = self._history_message_values(position, item)
        if message is None:
            values["created_at"] = self._created_at(item.get("created_at"))
            session.add(ChatMessage(id=message_id, chat_id=chat_id, **values))
            return
        for key, value in values.items():
            setattr(message, key, value)

    @staticmethod
    def _created_at(value: object) -> datetime:
        if isinstance(value, datetime): return value
        if isinstance(value, str): return datetime.fromisoformat(value)
        return utc_now()

    @staticmethod
    def _delete_removed_messages(session: Session, existing: dict[str, ChatMessage], retained_ids: set[str]) -> None:
        for message_id, message in existing.items():
            if message_id not in retained_ids: session.delete(message)

    @staticmethod
    def _set_initial_chat_title(chat: Chat, history: list[dict]) -> None:
        user_message = next((item["content"] for item in history if item["role"] == "user"), "")
        if chat.title == "Cuộc trò chuyện mới" and user_message:
            chat.title = user_message.strip()[:80]

    def link_artifacts_to_turn(
        self,
        chat_id: str,
        user_message_id: str,
        assistant_message_id: str,
        asset_ids: list[str],
    ) -> list[LibraryAsset]:
        if not asset_ids:
            return []
        with self.database.session() as session:
            assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.id.in_(asset_ids))))
            for asset in assets:
                exists = session.scalar(select(ArtifactMessageLink).where(
                    ArtifactMessageLink.asset_id == asset.id,
                    ArtifactMessageLink.assistant_message_id == assistant_message_id,
                ))
                if exists is None:
                    session.add(ArtifactMessageLink(
                        asset_id=asset.id,
                        chat_id=chat_id,
                        user_message_id=user_message_id,
                        assistant_message_id=assistant_message_id,
                        user_id=asset.user_id,
                        workspace_id=asset.workspace_id,
                    ))
            session.commit()
            return assets

    def artifacts_by_assistant_message(self, chat_id: str, message_ids: list[str]) -> dict[str, list[LibraryAsset]]:
        if not message_ids:
            return {}
        with self.database.session() as session:
            rows = session.execute(
                select(ArtifactMessageLink.assistant_message_id, LibraryAsset)
                .join(LibraryAsset, LibraryAsset.id == ArtifactMessageLink.asset_id)
                .where(
                    ArtifactMessageLink.chat_id == chat_id,
                    ArtifactMessageLink.assistant_message_id.in_(message_ids),
                )
                .order_by(ArtifactMessageLink.created_at)
            ).all()
            result: dict[str, list[LibraryAsset]] = {}
            for message_id, asset in rows:
                result.setdefault(message_id, []).append(asset)
            return result

    def backfill_artifact_links(self, chat_id: str) -> None:
        """Recover links for files made before artifact provenance was introduced."""
        with self.database.session() as session:
            messages = list(session.scalars(
                select(ChatMessage).where(ChatMessage.chat_id == chat_id).order_by(ChatMessage.position)
            ))
            latest_user: ChatMessage | None = None
            for index, message in enumerate(messages):
                if message.role == "user":
                    latest_user = message
                    continue
                if message.role != "tool" or message.tool_name != "create_file" or latest_user is None:
                    continue
                try:
                    asset_id = str(json.loads(message.content).get("id", ""))
                except (TypeError, ValueError):
                    continue
                asset = session.get(LibraryAsset, asset_id)
                assistant = next((item for item in messages[index + 1 :] if item.role == "assistant"), None)
                if asset is None or assistant is None:
                    continue
                exists = session.scalar(select(ArtifactMessageLink).where(
                    ArtifactMessageLink.asset_id == asset.id,
                    ArtifactMessageLink.assistant_message_id == assistant.id,
                ))
                if exists is None:
                    session.add(ArtifactMessageLink(
                        asset_id=asset.id,
                        chat_id=chat_id,
                        user_message_id=latest_user.id,
                        assistant_message_id=assistant.id,
                        user_id=asset.user_id,
                        workspace_id=asset.workspace_id,
                    ))
            session.commit()

    def set_unread(self, chat_id: str, unread: bool) -> Chat | None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            chat.is_unread = unread
            session.commit()
            return chat

    def update_model(self, chat_id: str, provider: str, model: str) -> None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                raise ValueError(CHAT_NOT_FOUND_ERROR)
            chat.provider = provider
            chat.model = model
            chat.updated_at = utc_now()
            session.commit()

    def update(self, chat_id: str, **values) -> Chat | None:
        allowed = {"title", "pinned", "archived", "provider", "model", "project_id", "collection_id", "mode"}
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            for key, value in values.items():
                # project_id must be nullable so a chat can be moved back to
                # the global workspace; all other optional values retain their
                # existing "not supplied" behavior.
                if key in allowed and (key in {"project_id", "collection_id"} or value is not None):
                    setattr(chat, key, value)
            chat.updated_at = utc_now()
            session.commit()
            return chat

    def delete(self, chat_id: str) -> bool:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return False
            session.delete(chat)
            session.commit()
            return True

    def create_or_update_share(self, chat_id: str, expires_at: datetime | None = None) -> ChatShare | None:
        with self.database.session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                return None
            records = session.scalars(
                select(ChatMessage).where(ChatMessage.chat_id == chat_id).order_by(ChatMessage.position)
            ).all()
            messages = [
                {key: value for key, value in {
                    "role": item.role,
                    "content": item.content,
                    "contentBlocks": item.content_blocks or [],
                }.items() if value not in (None, [])}
                for item in records if item.role in {"user", "assistant"}
            ]
            share = session.scalar(select(ChatShare).where(ChatShare.chat_id == chat_id))
            if share is None:
                share = ChatShare(chat_id=chat.id, title=chat.title, provider=chat.provider, model=chat.model, messages=messages, expires_at=expires_at)
                session.add(share)
            else:
                share.title, share.provider, share.model, share.messages, share.expires_at = chat.title, chat.provider, chat.model, messages, expires_at
                share.token = token_urlsafe(24)
                share.updated_at = utc_now()
            session.commit()
            return share

    def get_share(self, token: str) -> ChatShare | None:
        with self.database.session() as session:
            return session.scalar(select(ChatShare).where(ChatShare.token == token))

    def revoke_share(self, chat_id: str) -> bool:
        with self.database.session() as session:
            share = session.scalar(select(ChatShare).where(ChatShare.chat_id == chat_id))
            if share is None:
                return False
            session.delete(share)
            session.commit()
            return True

    def history(self, chat_id: str) -> list[dict]:
        # Query messages directly while the Session is open.  A Chat returned by
        # ``get()`` is detached after the context manager exits, so accessing its
        # lazy ``messages`` relationship there raises DetachedInstanceError.
        with self.database.session() as session:
            messages = session.scalars(
                select(ChatMessage)
                .where(ChatMessage.chat_id == chat_id)
                .order_by(ChatMessage.position)
            ).all()
            return [
                {key: value for key, value in {
                    "message_id": message.id,
                    "position": message.position,
                    "role": message.role, "content": message.content, "id": message.tool_call_id,
                    "name": message.tool_name, "tool_calls": message.tool_calls,
                    "attachments": message.attachments,
                    "content_blocks": message.content_blocks,
                    "sources": message.sources,
                    "generated_asset_ids": message.generated_asset_ids,
                    "pinned": message.pinned,
                    "created_at": message.created_at.isoformat(),
                }.items() if value is not None}
                for message in messages
            ]
