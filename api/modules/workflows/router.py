"""Reusable workflow recipe catalog."""

from fastapi import APIRouter


def build_router(error_responses: dict) -> APIRouter:
    router = APIRouter(tags=["Workflows"])

    @router.get("/api/workflow-recipes", responses=error_responses)
    def workflow_recipes() -> list[dict[str, object]]:
        return [
            {"id": "daily-ai-digest", "title": "Daily AI digest", "prompt": "Tìm nguồn web mới, tổng hợp tin AI quan trọng hôm nay, nêu nguồn và tạo báo cáo Markdown.", "recurrence": "daily", "requireWebSource": True, "notifyEmail": True},
            {"id": "github-weekly-summary", "title": "GitHub weekly summary", "prompt": "Dùng GitHub đã chọn cho Project để tổng hợp issue, PR và workflow trong tuần; tạo báo cáo Markdown có nguồn.", "recurrence": "weekly", "requireWebSource": False, "notifyEmail": True},
            {"id": "project-report", "title": "Project report", "prompt": "Tổng hợp tiến độ Project, nguồn đã ghim, chat và artifact gần đây; tạo báo cáo Markdown.", "recurrence": "weekly", "requireWebSource": False, "notifyEmail": True},
        ]

    return router
