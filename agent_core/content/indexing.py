"""Queue and recover artifact indexing independently of HTTP."""

from typing import TYPE_CHECKING
from sqlalchemy import select
from agent_core.persistence.store import LibraryAsset, BackgroundJob, BackgroundJobRepository

if TYPE_CHECKING:
    from agent_core.runtime.services import Services

def enqueue_artifact_index(asset: LibraryAsset, app_services: "Services") -> BackgroundJob | None:
    if not asset.is_project_source:
        return None
    jobs = BackgroundJobRepository(app_services.chats.database)
    job, created = jobs.enqueue_unique("artifact_index", {"asset_id": asset.id}, dedupe_key=f"artifact:{asset.id}")
    if created:
        asset.index_status, asset.index_error = "queued", None
    return job


def queue_pending_artifacts(app_services: "Services") -> int:
    """Backfill Project Sources created before the artifact index existed."""
    with app_services.chats.database.session() as session:
        assets = list(session.scalars(select(LibraryAsset).where(
            LibraryAsset.is_project_source.is_(True),
            LibraryAsset.index_status.in_(("pending", "queued")),
        )))
    for asset in assets:
        enqueue_artifact_index(asset, app_services)
    if assets:
        with app_services.chats.database.session() as session:
            for asset_id in [item.id for item in assets]:
                item = session.get(LibraryAsset, asset_id)
                if item and item.index_status == "pending":
                    item.index_status = "queued"
            session.commit()
    return len(assets)
