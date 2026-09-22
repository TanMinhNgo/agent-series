"""Validated schedule proposal shared by API and agent runtime."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator

VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh"

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
