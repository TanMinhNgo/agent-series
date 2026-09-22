"""Validated configuration for the supported workflow templates."""
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STEP_IDS = ("source", "agent", "artifact", "notification")


class RetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stepId: Literal["source", "agent", "artifact", "notification"] | None = None
    confirmResend: bool = False


class WorkflowScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nextRunAt: datetime
    timezone: str = "Asia/Ho_Chi_Minh"
    title: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Múi giờ không hợp lệ.") from exc
        return value

    @field_validator("nextRunAt")
    @classmethod
    def future_slot(cls, value):
        if value.tzinfo is None or value <= datetime.now(UTC):
            raise ValueError("Lịch cần thời điểm tương lai có múi giờ.")
        return value.astimezone(UTC)


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    template: Literal["github-weekly-summary", "daily-ai-digest", "project-report"] = "github-weekly-summary"
    repository: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)
    prompt: str = Field(default="Tổng hợp tiến độ và những vấn đề cần chú ý.", min_length=1, max_length=10000)
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=160)
    notifyEmail: bool = False

    @model_validator(mode="after")
    def template_inputs(self):
        if self.template == "github-weekly-summary" and not self.repository:
            raise ValueError("Workflow GitHub cần repository.")
        return self


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startsAt: datetime
    endsAt: datetime

    @field_validator("startsAt", "endsAt")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Thời gian phải có múi giờ.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_range(self):
        if not self.startsAt < self.endsAt or self.endsAt - self.startsAt > timedelta(days=31) or self.endsAt > datetime.now(UTC):
            raise ValueError("Khoảng thời gian phải trong quá khứ, từ 1 đến tối đa 31 ngày.")
        return self
