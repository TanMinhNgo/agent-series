"""Confirmed external connector actions."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from agent_core.integrations.google_workspace import GoogleConnectorError
from api.contracts.requests import ExternalActionProposalRequest


@dataclass(frozen=True)
class IntegrationRouteDependencies:
    services: Callable[[], Any]
    record_project_activity: Callable[..., None]
    artifact_not_found_error: str
    error_responses: dict


def build_router(deps: IntegrationRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Connectors"])

    @router.post("/api/external-action-proposals", status_code=201, responses=deps.error_responses)
    def create_external_action_proposal(payload: ExternalActionProposalRequest) -> dict[str, Any]:
        asset = deps.services().library.ensure_remote(payload.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
        proposal = deps.services().workspace.create_external_proposal(payload.action_type, {"assetId": asset.id, "name": asset.name, "folderId": payload.folder_id}, asset.project_id)
        deps.record_project_activity(asset.project_id, "external_action.proposed", "artifact", asset.id, f"Đang chờ xác nhận upload {asset.name} lên Google Drive.")
        return {"proposalId": proposal.id, "status": proposal.status, "actionType": proposal.action_type, "assetId": asset.id, "name": asset.name, "folderId": payload.folder_id, "expiresAt": proposal.expires_at.isoformat()}

    @router.post("/api/external-action-proposals/{proposal_id}/confirm", responses=deps.error_responses)
    def confirm_external_action_proposal(proposal_id: str) -> dict[str, Any]:
        services = deps.services()
        proposal = services.workspace.claim_external_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=409, detail="Đề xuất đã hết hạn hoặc đã được xử lý.")
        if proposal.action_type != "google_drive_upload":
            raise HTTPException(status_code=422, detail="Loại action chưa hỗ trợ.")
        asset = services.library.ensure_remote(str(proposal.config.get("assetId") or ""))
        if asset is None:
            raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
        try:
            data = services.library.storage.read(asset.storage_provider, asset.stored_name, asset.storage_file_id)
            result = services.google_workspace.upload_drive_file(asset.name, data, asset.mime_type, proposal.config.get("folderId"))
        except GoogleConnectorError as exc:
            services.workspace.finish_external_proposal(proposal.id, str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            services.workspace.finish_external_proposal(proposal.id, str(exc))
            raise HTTPException(status_code=502, detail="Không thể upload lên Google Drive.") from exc
        services.workspace.finish_external_proposal(proposal.id)
        deps.record_project_activity(asset.project_id, "external_action.completed", "artifact", asset.id, f"Đã upload {asset.name} lên Google Drive sau xác nhận.")
        return {"proposalId": proposal.id, "status": "completed", "result": result}

    return router
