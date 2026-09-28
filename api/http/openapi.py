"""Swagger error documentation shared by every router."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

JSON_MEDIA_TYPE = "application/json"
AUTHENTICATION_REQUIRED_ERROR = "Cần đăng nhập."
API_ERROR_SCHEMA_REFERENCE = "#/components/schemas/ApiError"
CHAT_DETAIL_PATH = "/api/chats/{chat_id}"
FORBIDDEN_ACTION_DESCRIPTION = "Không có quyền thực hiện thao tác này."
INVALID_STATE_DESCRIPTION = "Trạng thái hiện tại không cho phép thao tác."
API_ERROR_RESPONSES = {
    403: {"description": FORBIDDEN_ACTION_DESCRIPTION},
    404: {"description": "Không tìm thấy tài nguyên."},
    409: {"description": INVALID_STATE_DESCRIPTION},
    422: {"description": "Dữ liệu yêu cầu không hợp lệ."},
    502: {"description": "Dịch vụ phụ thuộc trả lỗi."},
    503: {"description": "Dịch vụ tạm thời không khả dụng."},
}


def _error(description: str, example: str) -> dict[str, Any]:
    return {"description": description, "content": {JSON_MEDIA_TYPE: {"schema": {"$ref": API_ERROR_SCHEMA_REFERENCE}, "example": {"detail": example}}}}


# Swagger uses these responses consistently, while the route implementations
# remain focused on their actual application behavior.
ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: _error("Cần đăng nhập để thực hiện thao tác này.", AUTHENTICATION_REQUIRED_ERROR),
    403: _error(FORBIDDEN_ACTION_DESCRIPTION, FORBIDDEN_ACTION_DESCRIPTION),
    404: _error("Không tìm thấy tài nguyên được yêu cầu.", "Không tìm thấy chat."),
    422: _error("Dữ liệu gửi lên không hợp lệ hoặc không thỏa điều kiện nghiệp vụ.", "Model không được hỗ trợ."),
    409: _error(INVALID_STATE_DESCRIPTION, INVALID_STATE_DESCRIPTION),
    500: _error("Lỗi máy chủ không mong đợi. Kiểm tra log FastAPI để biết chi tiết.", "Lỗi máy chủ nội bộ."),
}

# Only list errors the endpoint can actually return as an HTTP response.
# The streaming endpoint reports missing chats/model failures as SSE `error`
# events after its HTTP 200 connection has started.
ROUTE_ERROR_STATUSES: dict[tuple[str, str], tuple[int, ...]] = {
    ("post", "/api/chats"): (422, 500),
    ("get", CHAT_DETAIL_PATH): (404, 500),
    ("get", "/api/chats/{chat_id}/messages"): (404, 500),
    ("patch", CHAT_DETAIL_PATH): (404, 422, 500),
    ("delete", CHAT_DETAIL_PATH): (404, 500),
    ("post", "/api/chats/{chat_id}/share"): (404, 500),
    ("get", "/api/public/shares/{token}"): (404, 500),
    ("post", "/api/chats/{chat_id}/stream"): (422, 500),
    ("delete", "/api/memories/{memory_id}"): (404, 500),
    ("post", "/api/documents"): (422, 500),
    ("post", "/api/media"): (422, 500),
    ("post", "/api/projects"): (422, 500),
    ("patch", "/api/projects/{project_id}"): (404, 422, 500),
    ("delete", "/api/projects/{project_id}"): (404, 500),
    ("post", "/api/schedules"): (422, 500),
    ("patch", "/api/schedules/{schedule_id}"): (404, 422, 500),
    ("delete", "/api/schedules/{schedule_id}"): (404, 500),
    ("post", "/api/plugins"): (422, 500),
    ("get", "/api/plugin-catalog"): (500,),
    ("post", "/api/plugin-catalog/{slug}/install"): (404, 500),
    ("patch", "/api/plugins/{plugin_id}"): (404, 422, 500),
    ("delete", "/api/plugins/{plugin_id}"): (404, 500),
}


def install(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        schema["tags"] = app.openapi_tags
        schema.setdefault("components", {}).setdefault("schemas", {})["ApiError"] = {
            "type": "object",
            "required": ["detail"],
            "properties": {"detail": {"type": "string", "description": "Thông báo lỗi cho client."}},
        }
        for (method, path), statuses in ROUTE_ERROR_STATUSES.items():
            operation = schema["paths"][path][method]
            operation.setdefault("responses", {}).update({str(status): ERROR_RESPONSES[status] for status in statuses})
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
