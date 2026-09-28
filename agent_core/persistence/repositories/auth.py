from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, func, select

from agent_core.persistence.database import Database
from agent_core.persistence.models import (
    ArtifactChunk,
    ArtifactMessageLink,
    AuthIdentity,
    AuthSession,
    BackgroundJob,
    Chat,
    ChatMemoryChunk,
    ChatMessage,
    ChatShare,
    ConnectorAuditLog,
    ConnectorConnection,
    Document,
    DocumentChunk,
    KnowledgeCollection,
    LibraryAsset,
    MediaAttachment,
    OAuthState,
    Plugin,
    Project,
    PromptTemplate,
    ResponseFeedback,
    Schedule,
    ScheduleRun,
    SystemAuditLog,
    User,
    UserPreference,
    UserProviderCredential,
    Workspace,
    utc_now,
)
from agent_core.persistence.repositories.workspace import WorkspaceRepository


class AuthRepository:
    def __init__(self, database: Database):
        self.database = database

    def user_count(self) -> int:
        with self.database.session() as session:
            return int(session.scalar(select(func.count()).select_from(User).execution_options(skip_user_scope=True)) or 0)

    def get_user(self, user_id: str) -> User | None:
        with self.database.session() as session:
            return session.get(User, user_id, execution_options={"skip_user_scope": True})

    def get_user_by_email(self, email: str) -> User | None:
        with self.database.session() as session:
            return session.scalar(select(User).where(User.email == email).execution_options(skip_user_scope=True))

    def create_user(self, email: str, display_name: str | None = None, role: str = "member") -> User:
        with self.database.session() as session:
            item = User(email=email, display_name=display_name, role=role)
            session.add(item); session.commit(); return item

    def list_users(self, query: str | None, offset: int, limit: int) -> tuple[list[tuple[User, datetime | None]], int]:
        with self.database.session() as session:
            last_sign_in = select(AuthSession.user_id.label("user_id"), func.max(AuthSession.created_at).label("last_sign_in_at")).group_by(AuthSession.user_id).subquery()
            statement = select(User, last_sign_in.c.last_sign_in_at).outerjoin(last_sign_in, last_sign_in.c.user_id == User.id).execution_options(skip_user_scope=True)
            if query:
                statement = statement.where(User.email.ilike(f"%{query.strip()}%"))
            total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = list(session.execute(statement.order_by(desc(User.created_at)).offset(offset).limit(limit)).all())
            return rows, total

    def set_user_active(self, user_id: str, active: bool) -> User | None:
        with self.database.session() as session:
            user = session.get(User, user_id, execution_options={"skip_user_scope": True})
            if user is None:
                return None
            user.is_active = active
            if not active:
                session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
            session.commit()
            return user

    def provider_credential_metadata(self, offset: int, limit: int) -> tuple[list[tuple[UserProviderCredential, User]], int]:
        with self.database.session() as session:
            statement = select(UserProviderCredential, User).join(User, User.id == UserProviderCredential.user_id).execution_options(skip_user_scope=True)
            total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
            rows = list(session.execute(statement.order_by(desc(UserProviderCredential.updated_at)).offset(offset).limit(limit)).all())
            return rows, total

    def user_provider_credentials(self, user_id: str) -> list[UserProviderCredential]:
        with self.database.session() as session:
            return list(session.scalars(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id).order_by(UserProviderCredential.provider)))

    def user_provider_credential(self, user_id: str, provider: str) -> UserProviderCredential | None:
        with self.database.session() as session:
            return session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))

    def save_user_provider_credential(self, user_id: str, provider: str, ciphertext: str, key_hint: str) -> UserProviderCredential:
        with self.database.session() as session:
            item = session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))
            if item is None:
                item = UserProviderCredential(user_id=user_id, provider=provider, ciphertext=ciphertext, key_hint=key_hint)
                session.add(item)
            else:
                item.ciphertext, item.key_hint, item.validated_at, item.updated_at = ciphertext, key_hint, utc_now(), utc_now()
            session.commit()
            return item

    def delete_user_provider_credential(self, user_id: str, provider: str) -> bool:
        with self.database.session() as session:
            item = session.scalar(select(UserProviderCredential).where(UserProviderCredential.user_id == user_id, UserProviderCredential.provider == provider))
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def add_system_audit(self, event_type: str, actor_user_id: str | None = None, subject_user_id: str | None = None, summary: str | None = None, metadata_json: dict | None = None) -> SystemAuditLog:
        with self.database.session() as session:
            item = SystemAuditLog(actor_user_id=actor_user_id, subject_user_id=subject_user_id, event_type=event_type, summary=summary, metadata_json=metadata_json)
            session.add(item); session.commit(); return item

    def list_system_audit(self, offset: int, limit: int) -> tuple[list[SystemAuditLog], int]:
        with self.database.session() as session:
            statement = select(SystemAuditLog).execution_options(skip_user_scope=True)
            total = int(session.scalar(select(func.count()).select_from(SystemAuditLog).execution_options(skip_user_scope=True)) or 0)
            return list(session.scalars(statement.order_by(desc(SystemAuditLog.created_at)).offset(offset).limit(limit))), total

    def system_counts(self) -> dict[str, int]:
        with self.database.session() as session:
            return {
                "users": int(session.scalar(select(func.count()).select_from(User).execution_options(skip_user_scope=True)) or 0),
                "activeUsers": int(session.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)).execution_options(skip_user_scope=True)) or 0),
                "chats": int(session.scalar(select(func.count()).select_from(Chat).execution_options(skip_user_scope=True)) or 0),
                "projects": int(session.scalar(select(func.count()).select_from(Project).execution_options(skip_user_scope=True)) or 0),
                "documents": int(session.scalar(select(func.count()).select_from(Document).execution_options(skip_user_scope=True)) or 0),
            }

    def get_user_for_identity(self, provider: str, subject: str) -> User | None:
        with self.database.session() as session:
            row = session.execute(
                select(User).join(AuthIdentity, AuthIdentity.user_id == User.id).where(
                    AuthIdentity.provider == provider,
                    AuthIdentity.provider_subject == subject,
                ).execution_options(skip_user_scope=True)
            ).first()
            return row[0] if row else None

    def link_or_get_identity(self, user_id: str, provider: str, subject: str) -> User:
        with self.database.session() as session:
            identity = session.scalar(select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_subject == subject,
            ).with_for_update().execution_options(skip_user_scope=True))
            if identity is None:
                session.add(AuthIdentity(user_id=user_id, provider=provider, provider_subject=subject))
                session.commit()
                return session.get(User, user_id, execution_options={"skip_user_scope": True})
            return session.get(User, identity.user_id, execution_options={"skip_user_scope": True})

    def create_auth_oauth_state(self, state: str, purpose: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(OAuthState(state=state, connector_slug=purpose, expires_at=expires_at)); session.commit()

    def consume_auth_oauth_state(self, state: str, now: datetime) -> str | None:
        with self.database.session() as session:
            item = session.get(OAuthState, state, execution_options={"skip_user_scope": True})
            if item is None:
                return None
            session.delete(item); session.commit()
            return item.connector_slug if item.expires_at > now else None

    def create_session(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(AuthSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at)); session.commit()

    def user_for_session(self, token_hash: str, now: datetime) -> User | None:
        with self.database.session() as session:
            row = session.execute(
                select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.token_hash == token_hash, AuthSession.expires_at > now).execution_options(skip_user_scope=True)
            ).first()
            return row[1] if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self.database.session() as session:
            session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash)); session.commit()

    def claim_legacy_data(self, user_id: str) -> None:
        entities = (Chat, ChatMemoryChunk, ChatShare, ChatMessage, ResponseFeedback, UserPreference, PromptTemplate, MediaAttachment, LibraryAsset, ArtifactMessageLink, ArtifactChunk, Project, Schedule, ScheduleRun, Plugin, ConnectorConnection, OAuthState, ConnectorAuditLog, Document, DocumentChunk, KnowledgeCollection, BackgroundJob)
        with self.database.session() as session:
            for entity in entities:
                session.execute(entity.__table__.update().where(entity.user_id.is_(None)).values(user_id=user_id))
            session.commit()

    def ensure_personal_workspace(self, user_id: str, display_name: str | None = None) -> Workspace:
        return WorkspaceRepository(self.database).ensure_personal_workspace(user_id, display_name)

    def claim_legacy_workspace_data(self, user_id: str, workspace_id: str) -> None:
        entities = (Chat, ChatMemoryChunk, ChatShare, ChatMessage, ResponseFeedback, UserPreference, PromptTemplate, MediaAttachment, LibraryAsset, ArtifactMessageLink, ArtifactChunk, Project, Schedule, ScheduleRun, Plugin, ConnectorConnection, OAuthState, ConnectorAuditLog, Document, DocumentChunk, KnowledgeCollection, BackgroundJob)
        with self.database.session() as session:
            for entity in entities:
                session.execute(entity.__table__.update().where(entity.user_id == user_id, entity.workspace_id.is_(None)).values(workspace_id=workspace_id))
            session.commit()
