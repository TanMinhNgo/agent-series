from __future__ import annotations


from sqlalchemy import select

from agent_core.persistence.database import Database
from agent_core.persistence.models import MediaAttachment


class MediaRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, **values) -> MediaAttachment:
        with self.database.session() as session:
            item = MediaAttachment(**values)
            session.add(item)
            session.commit()
            return item

    def get_many(self, ids: list[str]) -> list[MediaAttachment]:
        with self.database.session() as session:
            return list(session.scalars(select(MediaAttachment).where(MediaAttachment.id.in_(ids))))

    def replace_storage(self, media_id: str, provider: str, stored_name: str, file_id: str | None) -> MediaAttachment | None:
        with self.database.session() as session:
            item = session.get(MediaAttachment, media_id)
            if item is None:
                return None
            item.storage_provider, item.stored_name, item.storage_file_id = provider, stored_name, file_id
            session.commit()
            return item
