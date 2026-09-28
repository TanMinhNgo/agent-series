"""One repository per domain; import from here or from the submodule."""

from agent_core.persistence.repositories.model_registry import ModelRegistryRepository
from agent_core.persistence.repositories.chat import ChatRepository
from agent_core.persistence.repositories.workspace import WorkspaceRepository
from agent_core.persistence.repositories.connector import ConnectorRepository
from agent_core.persistence.repositories.auth import AuthRepository
from agent_core.persistence.repositories.schedule import ScheduleRepository
from agent_core.persistence.repositories.background_job import BackgroundJobRepository
from agent_core.persistence.repositories.media import MediaRepository

__all__ = [
    "ModelRegistryRepository",
    "ChatRepository",
    "WorkspaceRepository",
    "ConnectorRepository",
    "AuthRepository",
    "ScheduleRepository",
    "BackgroundJobRepository",
    "MediaRepository",
]
