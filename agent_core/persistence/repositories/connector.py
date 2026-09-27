from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, or_, select

from agent_core.persistence.database import Database
from agent_core.persistence.models import ConnectorAuditLog, ConnectorConnection, OAuthState, User, utc_now


class ConnectorRepository:
    """Persistence for OAuth connections, short-lived CSRF state, and audit metadata."""

    def __init__(self, database: Database):
        self.database = database

    def get_connection(self, connector_slug: str, owner_id: str | None = None) -> ConnectorConnection | None:
        with self.database.session() as session:
            query = select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug)
            if owner_id is not None:
                query = query.where(ConnectorConnection.user_id == owner_id)
            return session.scalar(query)

    def save_connection(self, connector_slug: str, encrypted_token: str, account_email: str | None, scopes: list[str], expires_at: datetime | None, status: str = "connected") -> ConnectorConnection:
        with self.database.session() as session:
            item = session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))
            if item is None:
                item = ConnectorConnection(connector_slug=connector_slug, encrypted_token=encrypted_token, account_email=account_email, scopes=scopes, expires_at=expires_at, status=status)
                session.add(item)
            else:
                item.encrypted_token = encrypted_token
                item.account_email = account_email
                item.scopes = scopes
                item.expires_at = expires_at
                item.status = status
                item.updated_at = utc_now()
            session.commit()
            return item

    def set_connection_status(self, connector_slug: str, status: str, owner_id: str | None = None) -> ConnectorConnection | None:
        with self.database.session() as session:
            query = select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug)
            if owner_id is not None:
                query = query.where(ConnectorConnection.user_id == owner_id)
            item = session.scalar(query)
            if item is None:
                return None
            item.status = status
            item.updated_at = utc_now()
            session.commit()
            return item

    def delete_connection(self, connector_slug: str) -> bool:
        with self.database.session() as session:
            item = session.scalar(select(ConnectorConnection).where(ConnectorConnection.connector_slug == connector_slug))
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def create_oauth_state(self, state: str, connector_slug: str, expires_at: datetime) -> None:
        with self.database.session() as session:
            session.add(OAuthState(state=state, connector_slug=connector_slug, expires_at=expires_at))
            session.commit()

    def consume_oauth_state(self, state: str, now: datetime) -> OAuthState | None:
        with self.database.session() as session:
            item = session.get(OAuthState, state)
            if item is None:
                return None
            session.delete(item)
            session.commit()
            return item if item.expires_at > now else None

    def audit(self, connector_slug: str, event_type: str, connection_id: str | None = None, tool_name: str | None = None, summary: str | None = None) -> ConnectorAuditLog:
        with self.database.session() as session:
            item = ConnectorAuditLog(connector_slug=connector_slug, connection_id=connection_id, event_type=event_type, tool_name=tool_name, summary=summary)
            session.add(item)
            session.commit()
            return item

    def list_audit(self, connector_slug: str, limit: int = 20) -> list[ConnectorAuditLog]:
        with self.database.session() as session:
            return list(session.scalars(select(ConnectorAuditLog).where(ConnectorAuditLog.connector_slug == connector_slug).order_by(desc(ConnectorAuditLog.created_at)).limit(limit)))

    def list_connection_metadata(
        self,
        offset: int,
        limit: int,
        query: str | None = None,
        connector_slug: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """Return admin-safe connection metadata without ever selecting token material."""
        filters = []
        if query:
            term = f"%{query.strip()}%"
            filters.append(or_(User.email.ilike(term), ConnectorConnection.connector_slug.ilike(term)))
        if connector_slug:
            filters.append(ConnectorConnection.connector_slug == connector_slug)
        if status:
            filters.append(ConnectorConnection.status == status)
        statement = (
            select(
                ConnectorConnection.id.label("id"),
                ConnectorConnection.connector_slug.label("connector_slug"),
                ConnectorConnection.status.label("status"),
                ConnectorConnection.scopes.label("scopes"),
                ConnectorConnection.expires_at.label("expires_at"),
                ConnectorConnection.created_at.label("created_at"),
                ConnectorConnection.updated_at.label("updated_at"),
                User.id.label("user_id"),
                User.email.label("user_email"),
            )
            .join(User, User.id == ConnectorConnection.user_id)
            .where(*filters)
            .order_by(desc(ConnectorConnection.updated_at))
            .offset(offset)
            .limit(limit)
            .execution_options(skip_user_scope=True)
        )
        count_statement = (
            select(func.count())
            .select_from(ConnectorConnection)
            .join(User, User.id == ConnectorConnection.user_id)
            .where(*filters)
            .execution_options(skip_user_scope=True)
        )
        with self.database.session() as session:
            rows = [dict(row._mapping) for row in session.execute(statement).all()]
            return rows, int(session.scalar(count_statement) or 0)
