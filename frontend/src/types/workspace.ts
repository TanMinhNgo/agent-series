export type Project = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  instructions: string | null;
  memoryMode: 'default' | 'project_only';
  createdAt: string;
  updatedAt: string;
};
export type Schedule = {
  id: string;
  title: string;
  startsAt: string;
  endsAt: string | null;
  notes: string | null;
  projectId: string | null;
  prompt: string | null;
  recurrence: 'once' | 'daily' | 'weekly';
  status: 'active' | 'paused' | 'completed';
  nextRunAt: string | null;
  lastRunAt: string | null;
  timezone: string;
  chatId: string | null;
  createdAt: string;
  updatedAt: string;
};
export type ScheduleRun = {
  id: string;
  scheduleId: string;
  scheduledFor: string;
  status: 'running' | 'succeeded' | 'failed';
  summary: string | null;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
};
export type Plugin = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  enabled: boolean;
  config: Record<string, unknown> | null;
  catalogSlug: string | null;
  category: string | null;
  capabilities: string[] | null;
  connectionStatus: 'not_connected' | 'connected' | null;
  createdAt: string;
  updatedAt: string;
};
export type PluginCatalogItem = {
  slug: string;
  name: string;
  description: string;
  category: string;
  capabilities: string[];
  setup_url: string;
  featured: boolean;
  installedPluginId: string | null;
};
export type GoogleConnectorStatus = {
  connectorSlug: 'google-workspace';
  configured: boolean;
  status: 'not_connected' | 'connected' | 'reauth_required';
  accountEmail: string | null;
  scopes: string[];
  expiresAt: string | null;
};
export type ConnectorAuditLog = {
  id: string;
  eventType: string;
  toolName: string | null;
  summary: string | null;
  createdAt: string;
};
