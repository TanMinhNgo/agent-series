from __future__ import annotations


from sqlalchemy import select

from agent_core.persistence.database import Database
from agent_core.persistence.models import ProviderModel, SystemSetting


class ModelRegistryRepository:
    def __init__(self, database: Database): self.database = database
    def seed(self, models: dict[str, tuple[str, ...]]) -> None:
        with self.database.session() as s:
            for provider, items in models.items():
                for model in items:
                    if not s.scalar(select(ProviderModel).where(ProviderModel.provider == provider, ProviderModel.model_id == model)):
                        s.add(ProviderModel(provider=provider, model_id=model, display_name=model, approved=True, is_active=True))
            s.commit()
    def list(self) -> list[ProviderModel]:
        with self.database.session() as s: return list(s.scalars(select(ProviderModel).order_by(ProviderModel.provider, ProviderModel.model_id)))
    def active(self) -> dict[str, tuple[str, ...]]:
        with self.database.session() as s:
            rows = s.scalars(select(ProviderModel).where(ProviderModel.is_active.is_(True))).all(); result: dict[str, list[str]] = {}
            for row in rows: result.setdefault(row.provider, []).append(row.model_id)
            return {key: tuple(value) for key, value in result.items()}
    def set_active(self, provider: str, model_id: str, is_active: bool) -> ProviderModel | None:
        with self.database.session() as s:
            item = s.scalar(select(ProviderModel).where(ProviderModel.provider == provider, ProviderModel.model_id == model_id))
            if item is None:
                return None
            item.is_active = is_active
            s.commit()
            s.refresh(item)
            return item
    def setting(self, key: str) -> str | None:
        with self.database.session() as s: item = s.get(SystemSetting, key); return item.value if item else None
    def set_setting(self, key: str, value: str) -> None:
        with self.database.session() as s:
            item = s.get(SystemSetting, key)
            if item: item.value = value
            else: s.add(SystemSetting(key=key, value=value))
            s.commit()
