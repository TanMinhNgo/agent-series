"""HTTP request contracts for the Agent Series API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh"

class CreateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    context_source_chat_id: str | None = Field(default=None, alias="contextSourceChatId")
    project_id: str | None = Field(default=None, alias="projectId")
    collection_id: str | None = Field(default=None, alias="collectionId")

    model_config = {"populate_by_name": True}


class UpdateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None
    archived: bool | None = None
    project_id: str | None = Field(default=None, alias="projectId")
    collection_id: str | None = Field(default=None, alias="collectionId")

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")
    edit_asset_id: str | None = Field(default=None, alias="editAssetId")
    run_id: str | None = Field(default=None, alias="runId", min_length=1, max_length=100)

    model_config = {"populate_by_name": True}


class ShareRequest(BaseModel):
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    model_config = {"populate_by_name": True}


class WorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class WorkspaceInvitationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["editor", "viewer"] = "viewer"


class WorkspaceMemberRoleRequest(BaseModel):
    role: Literal["owner", "editor", "viewer"]


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    status: Literal["active", "paused", "completed"] = "active"
    instructions: str | None = Field(default=None, max_length=10_000)
    memory_mode: Literal["default", "project_only"] = Field(default="default", alias="memoryMode")

    model_config = {"populate_by_name": True}


class KnowledgeCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)


class CollectionDocumentsRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")

    model_config = {"populate_by_name": True}


class DeleteProjectRequest(BaseModel):
    confirm_name: str = Field(alias="confirmName", min_length=1, max_length=160)

    model_config = {"populate_by_name": True}


class UpdateArtifactRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    project_id: str | None = Field(default=None, alias="projectId")
    is_project_source: bool | None = Field(default=None, alias="isProjectSource")

    model_config = {"populate_by_name": True}


class PromptTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20_000)
    project_id: str | None = Field(default=None, alias="projectId")

    model_config = {"populate_by_name": True}


class PinMessageRequest(BaseModel):
    pinned: bool


class FeedbackRequest(BaseModel):
    kind: Literal["helpful", "incorrect", "too_long", "too_short", "unclear", "wrong_style"]
    note: str | None = Field(default=None, max_length=2000)


class BranchChatRequest(BaseModel):
    assistant_message_id: str = Field(alias="assistantMessageId")

    model_config = {"populate_by_name": True}


class AdminUserStatusRequest(BaseModel):
    is_active: bool = Field(alias="isActive")

    model_config = {"populate_by_name": True}


class AdminModelStatusRequest(BaseModel):
    is_active: bool = Field(alias="isActive")

    model_config = {"populate_by_name": True}


class ApiKeyRequest(BaseModel):
    api_key: str = Field(alias="apiKey", min_length=8, max_length=1000)

    model_config = {"populate_by_name": True}


class ScheduleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    notes: str | None = Field(default=None, max_length=10_000)
    project_id: str | None = Field(default=None, alias="projectId")
    provider: str | None = None
    model: str | None = None
    prompt: str | None = Field(default=None, max_length=10_000)
    require_web_source: bool = Field(default=False, alias="requireWebSource")
    notify_email: bool = Field(default=False, alias="notifyEmail")
    recurrence: Literal["once", "daily", "weekly"] = "once"
    status: Literal["active", "paused", "completed"] = "active"
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    timezone: str = VIETNAM_TIMEZONE

    model_config = {"populate_by_name": True}


class ScheduleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    starts_at: datetime | None = Field(default=None, alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    notes: str | None = Field(default=None, max_length=10_000)
    project_id: str | None = Field(default=None, alias="projectId")
    provider: str | None = None
    model: str | None = None
    prompt: str | None = Field(default=None, max_length=10_000)
    require_web_source: bool | None = Field(default=None, alias="requireWebSource")
    notify_email: bool | None = Field(default=None, alias="notifyEmail")
    recurrence: Literal["once", "daily", "weekly"] | None = None
    status: Literal["active", "paused", "completed"] | None = None
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    timezone: str | None = None

    model_config = {"populate_by_name": True}


class ScheduleProposalPayload(BaseModel):
    """The small, server-validated draft an AI may show inside a chat."""

    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=10_000)
    starts_at: datetime = Field(alias="startsAt")
    recurrence: Literal["once", "daily", "weekly"] = "once"
    timezone: str = Field(default=VIETNAM_TIMEZONE, min_length=1, max_length=80)

    model_config = {"populate_by_name": True}

    @field_validator("starts_at")
    @classmethod
    def starts_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Thời điểm lịch phải có múi giờ.")
        return value


class PluginRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool = False
    config: dict[str, Any] | None = None


class PluginUpdateRequest(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool | None = None
    config: dict[str, Any] | None = None

