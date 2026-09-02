"""Shared application service composition for HTTP and durable workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..ai.ollama import OllamaCatalog
from ..content.artifacts import ArtifactService
from ..content.file_storage import FileStorageService
from ..content.library import LibraryService
from ..content.media import MediaService
from ..integrations.github_app import GITHUB_SLUG, GitHubAppExecutor, GitHubAppService
from ..integrations.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleWorkspaceExecutor, GoogleWorkspaceService
from ..integrations.notifications import EmailNotificationService
from ..integrations.plugin_execution import EXECUTORS
from ..integrations.web_search import WebSearchService
from ..knowledge.memory import MemoryService
from ..knowledge.personalization import PersonalizationService
from ..knowledge.rag import KnowledgeService
from ..persistence.store import AuthRepository, ChatRepository, ConnectorRepository, Database, MediaRepository, ModelRegistryRepository, WorkspaceRepository
from .auth import AuthService
from .config import Settings, load_settings
from .credentials import UserCredentialService


@dataclass
class Services:
    settings: Settings
    chats: ChatRepository
    knowledge: KnowledgeService
    media: MediaService
    memory: MemoryService
    workspace: WorkspaceRepository
    library: LibraryService
    artifacts: ArtifactService
    google_workspace: GoogleWorkspaceService
    github: GitHubAppService
    auth: AuthService
    model_registry: ModelRegistryRepository
    credentials: UserCredentialService
    personalization: PersonalizationService
    web_search: WebSearchService
    email: EmailNotificationService
    ollama: OllamaCatalog


def build_services(settings: Settings | None = None) -> Services:
    """Create one consistent service graph for the API or a background worker."""
    settings = settings or load_settings()
    database = Database(settings.database_url)
    media_storage = FileStorageService(settings.media_dir, settings.imagekit_private_key, settings.imagekit_url_endpoint)
    knowledge_storage = FileStorageService(Path(settings.knowledge_dir), settings.imagekit_private_key, settings.imagekit_url_endpoint)
    media = MediaService(MediaRepository(database), settings.media_dir, media_storage)
    connectors = ConnectorRepository(database)
    google_workspace = GoogleWorkspaceService(connectors, settings)
    github = GitHubAppService(connectors, settings)
    EXECUTORS[GOOGLE_WORKSPACE_SLUG] = GoogleWorkspaceExecutor(google_workspace)
    EXECUTORS[GITHUB_SLUG] = GitHubAppExecutor(github)
    auth_repository = AuthRepository(database)
    model_registry = ModelRegistryRepository(database)
    model_registry.seed(settings.provider_models)
    return Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, Path(settings.knowledge_dir), settings.embedding_model, knowledge_storage),
        media=media,
        library=LibraryService(database, settings.media_dir, media_storage),
        artifacts=ArtifactService(database, settings.media_dir, settings.embedding_model, media_storage),
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
        google_workspace=google_workspace,
        github=github,
        auth=AuthService(auth_repository, settings),
        model_registry=model_registry,
        credentials=UserCredentialService(auth_repository, settings),
        personalization=PersonalizationService(database),
        web_search=WebSearchService(settings.tavily_api_key),
        email=EmailNotificationService(settings),
        ollama=OllamaCatalog(settings.ollama_base_url),
    )
