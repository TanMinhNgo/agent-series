import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type {
  ConnectorAuditLog,
  GoogleConnectorStatus,
  Plugin,
  PluginCatalogItem,
  Project,
  Schedule,
  ScheduleRun,
} from '@/src/types';

type ProjectInput = Pick<Project, 'name' | 'description' | 'status' | 'instructions' | 'memoryMode'>;
type ScheduleInput = Pick<
  Schedule,
  'title' | 'startsAt' | 'endsAt' | 'notes' | 'projectId' | 'prompt' | 'recurrence'
> &
  Partial<Pick<Schedule, 'status' | 'nextRunAt' | 'timezone'>>;
type PluginInput = Pick<Plugin, 'slug' | 'name' | 'description' | 'enabled' | 'config'>;

const endpoints = {
  project: { key: queryKeys.projects, url: '/projects' },
  schedule: { key: queryKeys.schedules, url: '/schedules' },
  plugin: { key: queryKeys.plugins, url: '/plugins' },
} as const;

const useResourceActions = <T>(kind: keyof typeof endpoints) => {
  const client = useQueryClient();
  const endpoint = endpoints[kind];
  return {
    create: useMutation({
      mutationFn: (data: T) => request<T>({ url: endpoint.url, method: 'POST', data }),
      onSuccess: () => client.invalidateQueries({ queryKey: endpoint.key }),
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Partial<T> }) =>
        request<T>({ url: `${endpoint.url}/${id}`, method: 'PATCH', data }),
      onSuccess: () => client.invalidateQueries({ queryKey: endpoint.key }),
    }),
    remove: useMutation({
      mutationFn: (id: string) => request<void>({ url: `${endpoint.url}/${id}`, method: 'DELETE' }),
      onSuccess: () => client.invalidateQueries({ queryKey: endpoint.key }),
    }),
  };
};

export const useWorkspace = () => {
  const client = useQueryClient();
  const projects = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => request<Project[]>({ url: endpoints.project.url }),
  });
  const schedules = useQuery({
    queryKey: queryKeys.schedules,
    queryFn: () => request<Schedule[]>({ url: endpoints.schedule.url }),
    refetchInterval: 15_000,
  });
  const plugins = useQuery({
    queryKey: queryKeys.plugins,
    queryFn: () => request<Plugin[]>({ url: endpoints.plugin.url }),
  });
  const pluginCatalog = useQuery({
    queryKey: ['plugin-catalog'],
    queryFn: () => request<PluginCatalogItem[]>({ url: '/plugin-catalog' }),
  });
  const googleConnector = useQuery({
    queryKey: queryKeys.googleConnector,
    queryFn: () => request<GoogleConnectorStatus>({ url: '/connectors/google' }),
  });
  const googleConnectorAudit = useQuery({
    queryKey: queryKeys.googleConnectorAudit,
    queryFn: () => request<ConnectorAuditLog[]>({ url: '/connectors/google/audit' }),
  });
  const projectActions = useResourceActions<ProjectInput>('project');
  const deleteProject = useMutation({
    mutationFn: ({ id, confirmName }: { id: string; confirmName: string }) =>
      request<{ deleted: Record<string, number>; fileCleanupQueued: boolean }>({
        url: `/projects/${id}`,
        method: 'DELETE',
        data: { confirmName },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.projects });
      void client.invalidateQueries({ queryKey: queryKeys.chats });
      void client.invalidateQueries({ queryKey: queryKeys.schedules });
      void client.invalidateQueries({ queryKey: ['documents'] });
      void client.invalidateQueries({ queryKey: ['library-assets'] });
      void client.invalidateQueries({ queryKey: ['templates'] });
      void client.invalidateQueries({ queryKey: ['chats'] });
      void client.invalidateQueries({ queryKey: queryKeys.collectionsRoot });
    },
  });
  const scheduleActions = useResourceActions<ScheduleInput>('schedule');
  const runScheduleNow = useMutation({
    mutationFn: (id: string) =>
      request<{ status: string; chatId: string }>({ url: `/schedules/${id}/run-now`, method: 'POST' }),
    onSuccess: (_, id) => {
      void client.invalidateQueries({ queryKey: queryKeys.schedules });
      void client.invalidateQueries({ queryKey: ['schedule-runs', id] });
    },
  });
  const pluginActions = useResourceActions<PluginInput>('plugin');
  const installCatalogPlugin = useMutation({
    mutationFn: (slug: string) => request<Plugin>({ url: `/plugin-catalog/${slug}/install`, method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.plugins });
      void client.invalidateQueries({ queryKey: ['plugin-catalog'] });
    },
  });
  const authorizeGoogle = useMutation({
    mutationFn: () =>
      request<{ authorizationUrl: string }>({ url: '/connectors/google/authorize', method: 'POST' }),
  });
  const disconnectGoogle = useMutation({
    mutationFn: () => request<void>({ url: '/connectors/google', method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.plugins });
      void client.invalidateQueries({ queryKey: queryKeys.googleConnector });
      void client.invalidateQueries({ queryKey: queryKeys.googleConnectorAudit });
    },
  });

  return {
    projects,
    schedules,
    plugins,
    pluginCatalog,
    googleConnector,
    googleConnectorAudit,
    projectActions,
    deleteProject,
    scheduleActions,
    runScheduleNow,
    pluginActions,
    installCatalogPlugin,
    authorizeGoogle,
    disconnectGoogle,
  };
};

export const useScheduleRuns = (scheduleId?: string) =>
  useQuery({
    queryKey: ['schedule-runs', scheduleId],
    queryFn: () => request<ScheduleRun[]>({ url: `/schedules/${scheduleId}/runs` }),
    enabled: Boolean(scheduleId),
  });
