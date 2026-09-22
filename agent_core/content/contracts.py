"""Public artifact metadata shared by tools and HTTP responses."""

from typing import Any
from agent_core.persistence.store import LibraryAsset

def library_asset_json(item: LibraryAsset) -> dict[str, Any]:
    return {"id": item.id, "artifactId": item.artifact_id, "name": item.name, "version": item.version, "mimeType": item.mime_type, "sizeBytes": item.size_bytes, "source": item.source, "projectId": item.project_id, "isProjectSource": item.is_project_source, "indexStatus": item.index_status, "indexError": item.index_error, "createdAt": item.created_at.isoformat(), "url": f"/api/library/assets/{item.id}/file"}
