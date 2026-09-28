from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from agent_core.persistence.database import Database
from agent_core.persistence.models import (
    ExternalActionProposal,
    MessageRetrievalTrace,
    Plugin,
    ProjectActivity,
    ProjectConnectorScope,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMember,
    current_user_id,
    utc_now,
)


class WorkspaceRepository:
    def __init__(self, database: Database):
        self.database = database

    def list(self, entity):
        with self.database.session() as session:
            return list(session.scalars(select(entity).order_by(entity.updated_at.desc())))

    def list_plugins(self) -> list[Plugin]:
        return self.list(Plugin)

    def get(self, entity, item_id: str):
        with self.database.session() as session:
            return session.get(entity, item_id)

    def get_plugin_by_catalog_slug(self, catalog_slug: str) -> Plugin | None:
        with self.database.session() as session:
            return session.scalar(select(Plugin).where(Plugin.catalog_slug == catalog_slug))

    def catalog_plugin_ids(self) -> dict[str, str]:
        with self.database.session() as session:
            rows = session.scalars(select(Plugin).where(Plugin.catalog_slug.is_not(None))).all()
            return {item.catalog_slug: item.id for item in rows if item.catalog_slug}

    def create(self, entity, **values):
        with self.database.session() as session:
            item = entity(**values)
            session.add(item)
            session.commit()
            return item

    def update(self, entity, item_id: str, **values):
        with self.database.session() as session:
            item = session.get(entity, item_id)
            if item is None:
                return None
            for key, value in values.items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            session.commit()
            return item

    def delete(self, entity, item_id: str) -> bool:
        with self.database.session() as session:
            item = session.get(entity, item_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True

    def add_project_activity(self, project_id: str | None, event_type: str, subject_type: str, subject_id: str | None, summary: str, metadata: dict | None = None) -> ProjectActivity:
        with self.database.session() as session:
            item = ProjectActivity(
                project_id=project_id, actor_user_id=current_user_id.get(), event_type=event_type,
                subject_type=subject_type, subject_id=subject_id, summary=summary, metadata_json=metadata,
            )
            session.add(item); session.commit(); return item

    def project_activity(self, project_id: str, limit: int = 50) -> list[ProjectActivity]:
        with self.database.session() as session:
            return list(session.scalars(
                select(ProjectActivity).where(
                    (ProjectActivity.project_id == project_id) | (ProjectActivity.project_id.is_(None))
                ).order_by(ProjectActivity.created_at.desc()).limit(limit)
            ))

    def save_retrieval_traces(self, message_id: str, project_id: str | None, traces: list[dict]) -> None:
        if not traces:
            return
        with self.database.session() as session:
            session.add_all(MessageRetrievalTrace(message_id=message_id, project_id=project_id, **trace) for trace in traces)
            session.commit()

    def retrieval_traces(self, message_ids: list[str]) -> dict[str, list[MessageRetrievalTrace]]:
        if not message_ids:
            return {}
        with self.database.session() as session:
            rows = session.scalars(select(MessageRetrievalTrace).where(MessageRetrievalTrace.message_id.in_(message_ids)).order_by(MessageRetrievalTrace.created_at)).all()
            result: dict[str, list[MessageRetrievalTrace]] = {}
            for item in rows:
                result.setdefault(item.message_id, []).append(item)
            return result

    def connector_scopes(self, project_id: str) -> list[ProjectConnectorScope]:
        with self.database.session() as session:
            return list(session.scalars(select(ProjectConnectorScope).where(ProjectConnectorScope.project_id == project_id).order_by(ProjectConnectorScope.connector_slug)))

    def save_connector_scope(self, project_id: str, connector_slug: str, config: dict) -> ProjectConnectorScope:
        with self.database.session() as session:
            item = session.scalar(select(ProjectConnectorScope).where(ProjectConnectorScope.project_id == project_id, ProjectConnectorScope.connector_slug == connector_slug))
            if item is None:
                item = ProjectConnectorScope(project_id=project_id, connector_slug=connector_slug, config=config)
                session.add(item)
            else:
                item.config, item.updated_at = config, utc_now()
            session.commit(); return item

    def delete_connector_scope(self, project_id: str, connector_slug: str) -> bool:
        with self.database.session() as session:
            item = session.scalar(select(ProjectConnectorScope).where(ProjectConnectorScope.project_id == project_id, ProjectConnectorScope.connector_slug == connector_slug))
            if item is None: return False
            session.delete(item); session.commit(); return True

    def create_external_proposal(self, action_type: str, config: dict, project_id: str | None = None) -> ExternalActionProposal:
        with self.database.session() as session:
            item = ExternalActionProposal(action_type=action_type, config=config, project_id=project_id, expires_at=utc_now() + timedelta(minutes=15))
            session.add(item); session.commit(); return item

    def claim_external_proposal(self, proposal_id: str) -> ExternalActionProposal | None:
        """Consume a one-time confirmation before a non-idempotent external write."""
        with self.database.session() as session:
            item = session.get(ExternalActionProposal, proposal_id)
            if item is None or item.status != "pending" or item.expires_at <= utc_now(): return None
            item.status, item.confirmed_at = "running", utc_now(); session.commit(); return item

    def finish_external_proposal(self, proposal_id: str, error: str | None = None) -> ExternalActionProposal | None:
        with self.database.session() as session:
            item = session.get(ExternalActionProposal, proposal_id)
            if item is None or item.status != "running": return None
            item.status, item.error = ("failed", error[:2_000]) if error else ("completed", None)
            session.commit(); return item

    def list_for_user(self, user_id: str) -> list[tuple[Workspace, WorkspaceMember]]:
        with self.database.session() as session:
            return list(session.execute(
                select(Workspace, WorkspaceMember)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == user_id)
                .order_by(Workspace.is_personal.desc(), Workspace.updated_at.asc())
                .execution_options(skip_user_scope=True)
            ).all())

    def membership(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        with self.database.session() as session:
            return session.scalar(select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
            ).execution_options(skip_user_scope=True))

    def default_for_user(self, user_id: str) -> WorkspaceMember | None:
        with self.database.session() as session:
            return session.scalar(select(WorkspaceMember).join(Workspace).where(
                WorkspaceMember.user_id == user_id
            ).order_by(Workspace.is_personal.desc(), Workspace.created_at.asc()).execution_options(skip_user_scope=True))

    def create_workspace(self, user_id: str, name: str, is_personal: bool = False) -> Workspace:
        with self.database.session() as session:
            item = Workspace(name=name, is_personal=is_personal, created_by_user_id=user_id)
            session.add(item); session.flush()
            session.add(WorkspaceMember(workspace_id=item.id, user_id=user_id, role="owner"))
            session.commit(); return item

    def ensure_personal_workspace(self, user_id: str, display_name: str | None = None) -> Workspace:
        with self.database.session() as session:
            item = session.scalar(select(Workspace).join(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id, Workspace.is_personal.is_(True)
            ).execution_options(skip_user_scope=True))
            if item:
                return item
            item = Workspace(name=f"{display_name or 'Không gian cá nhân'}", is_personal=True, created_by_user_id=user_id)
            session.add(item); session.flush(); session.add(WorkspaceMember(workspace_id=item.id, user_id=user_id, role="owner")); session.commit()
            return item

    def invite(self, workspace_id: str, email: str, role: str, invited_by_user_id: str, expires_at: datetime) -> WorkspaceInvitation:
        with self.database.session() as session:
            item = session.scalar(select(WorkspaceInvitation).where(
                WorkspaceInvitation.workspace_id == workspace_id, WorkspaceInvitation.email == email
            ).execution_options(skip_user_scope=True))
            if item:
                item.role, item.invited_by_user_id, item.expires_at = role, invited_by_user_id, expires_at
            else:
                item = WorkspaceInvitation(workspace_id=workspace_id, email=email, role=role, invited_by_user_id=invited_by_user_id, expires_at=expires_at)
                session.add(item)
            session.commit(); return item

    def invitations(self, workspace_id: str) -> list[WorkspaceInvitation]:
        with self.database.session() as session:
            return list(session.scalars(select(WorkspaceInvitation).where(WorkspaceInvitation.workspace_id == workspace_id).order_by(WorkspaceInvitation.created_at.desc()).execution_options(skip_user_scope=True)))

    def cancel_invitation(self, workspace_id: str, invitation_id: str) -> bool:
        with self.database.session() as session:
            invitation = session.scalar(
                select(WorkspaceInvitation)
                .where(WorkspaceInvitation.id == invitation_id, WorkspaceInvitation.workspace_id == workspace_id)
                .execution_options(skip_user_scope=True)
            )
            if invitation is None:
                return False
            session.delete(invitation)
            session.commit()
            return True

    def accept_invitation(self, invitation_id: str, user_id: str, email: str, now: datetime) -> WorkspaceMember | None:
        with self.database.session() as session:
            invitation = session.get(WorkspaceInvitation, invitation_id, execution_options={"skip_user_scope": True})
            if invitation is None or invitation.email != email.lower() or invitation.expires_at <= now:
                return None
            member = session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == invitation.workspace_id, WorkspaceMember.user_id == user_id).execution_options(skip_user_scope=True))
            if member is None:
                member = WorkspaceMember(workspace_id=invitation.workspace_id, user_id=user_id, role=invitation.role); session.add(member)
            session.delete(invitation); session.commit(); return member

    def update_member_role(self, workspace_id: str, user_id: str, role: str) -> WorkspaceMember | None:
        with self.database.session() as session:
            member = session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id).execution_options(skip_user_scope=True))
            if member is None:
                return None
            member.role = role; session.commit(); return member

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        with self.database.session() as session:
            member = session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id).execution_options(skip_user_scope=True))
            if member is None:
                return False
            session.delete(member); session.commit(); return True
