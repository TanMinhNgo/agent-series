"""Shared API serializers used by feature routers."""

from typing import Any

from agent_core.persistence.store import (
    BackgroundJob,
    Chat,
    ChatShare,
    Document,
    KnowledgeCollection,
    Plugin,
    Project,
    PromptTemplate,
    Schedule,
    ScheduleRun,
    User,
)

from agent_core.content.contracts import library_asset_json


def chat_json(chat: Chat) -> dict[str, Any]:
    return {"id": chat.id, "title": chat.title, "provider": chat.provider, "model": chat.model, "mode": getattr(chat, "mode", "standard"), "createdAt": chat.created_at.isoformat(), "updatedAt": chat.updated_at.isoformat(), "pinned": chat.pinned, "archived": chat.archived, "isUnread": bool(getattr(chat, "is_unread", False)), "contextSourceChatId": chat.context_source_chat_id, "projectId": getattr(chat, "project_id", None), "parentChatId": getattr(chat, "parent_chat_id", None), "branchFromPosition": getattr(chat, "branch_from_position", None), "collectionId": getattr(chat, "collection_id", None)}


def share_json(share: ChatShare) -> dict[str, Any]:
    return {"token": share.token, "title": share.title, "provider": share.provider, "model": share.model, "messages": share.messages, "createdAt": share.created_at.isoformat(), "updatedAt": share.updated_at.isoformat(), "expiresAt": share.expires_at.isoformat() if share.expires_at else None}


def document_json(document: Document, job: BackgroundJob | None = None) -> dict[str, Any]:
    return {"id": document.id, "name": document.original_name, "status": document.status, "pageCount": document.page_count, "error": document.error, "jobAttempts": job.attempts if job else 0, "jobMaxAttempts": job.max_attempts if job else 3, "jobError": job.last_error if job else None, "projectId": document.project_id, "url": f"/api/documents/{document.id}/file"}


def collection_json(item: KnowledgeCollection, documents: list[Document] | None = None) -> dict[str, Any]:
    return {"id": item.id, "projectId": item.project_id, "name": item.name, "description": item.description, "documentIds": [document.id for document in documents] if documents is not None else None, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def template_json(item: PromptTemplate) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "content": item.content, "projectId": item.project_id, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def project_json(item: Project) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "description": item.description, "status": item.status, "instructions": item.instructions, "memoryMode": item.memory_mode, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def schedule_json(item: Schedule) -> dict[str, Any]:
    return {"id": item.id, "title": item.title, "startsAt": item.starts_at.isoformat(), "endsAt": item.ends_at.isoformat() if item.ends_at else None, "notes": item.notes, "projectId": item.project_id, "chatId": item.chat_id, "provider": item.provider, "model": item.model, "prompt": item.prompt, "requireWebSource": item.require_web_source, "notifyEmail": item.notify_email, "recurrence": item.recurrence, "status": item.status, "nextRunAt": item.next_run_at.isoformat() if item.next_run_at else None, "lastRunAt": item.last_run_at.isoformat() if item.last_run_at else None, "timezone": item.timezone, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def schedule_run_json(item: ScheduleRun) -> dict[str, Any]:
    return {"id": item.id, "scheduleId": item.schedule_id, "scheduledFor": item.scheduled_for.isoformat(), "status": item.status, "retryCount": item.retry_count, "retryAt": item.retry_at.isoformat() if item.retry_at else None, "summary": item.summary, "error": item.error, "emailStatus": item.email_status, "emailSentAt": item.email_sent_at.isoformat() if item.email_sent_at else None, "emailError": item.email_error, "startedAt": item.started_at.isoformat(), "finishedAt": item.finished_at.isoformat() if item.finished_at else None}



def retrieval_trace_json(item: Any) -> dict[str, Any]:
    return {"sourceKind": item.source_kind, "sourceId": item.source_id, "sourceName": item.source_name, "version": item.version, "chunkRef": item.chunk_ref, "url": item.url}


def project_activity_json(item: Any, actor: User | None = None) -> dict[str, Any]:
    return {"id": item.id, "eventType": item.event_type, "subjectType": item.subject_type, "subjectId": item.subject_id, "summary": item.summary, "metadata": item.metadata_json or {}, "actorUserId": item.actor_user_id, "actorDisplayName": actor.display_name if actor else None, "createdAt": item.created_at.isoformat()}


def plugin_json(item: Plugin) -> dict[str, Any]:
    return {"id": item.id, "slug": item.slug, "name": item.name, "description": item.description, "enabled": item.enabled, "config": item.config, "catalogSlug": item.catalog_slug, "category": item.category, "capabilities": item.capabilities, "connectionStatus": item.connection_status, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}
