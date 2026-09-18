"""Connector tool selection for chat generation."""

from agent_core.integrations.plugin_execution import connected_read_tools, project_scoped_read_tools
from agent_core.persistence.store import Chat
from agent_core.runtime.services import Services


def project_connector_tools(app_services: Services, chat: Chat):
    """Expose connector reads only where a Project has explicitly scoped them."""
    if not chat.project_id:
        return connected_read_tools(app_services.workspace.list_plugins())
    scopes = {item.connector_slug: item.config or {} for item in app_services.workspace.connector_scopes(chat.project_id)}
    return project_scoped_read_tools(app_services.workspace.list_plugins(), scopes)
