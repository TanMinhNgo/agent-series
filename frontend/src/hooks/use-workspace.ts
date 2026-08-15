import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Plugin, PluginCatalogItem, Project, Schedule } from '@/src/types';

type ProjectInput = Pick<Project, 'name' | 'description' | 'status'>;
type ScheduleInput = Pick<Schedule, 'title' | 'startsAt' | 'endsAt' | 'notes' | 'projectId'> & Partial<Pick<Schedule, 'prompt' | 'recurrence' | 'status' | 'nextRunAt'>>;
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
  });
  const plugins = useQuery({
    queryKey: queryKeys.plugins,
    queryFn: () => request<Plugin[]>({ url: endpoints.plugin.url }),
  });
  const pluginCatalog = useQuery({
    queryKey: ['plugin-catalog'],
    queryFn: () => request<PluginCatalogItem[]>({ url: '/plugin-catalog' }),
  });
  const projectActions = useResourceActions<ProjectInput>('project');
  const scheduleActions = useResourceActions<ScheduleInput>('schedule');
  const pluginActions = useResourceActions<PluginInput>('plugin');
  const installCatalogPlugin = useMutation({
    mutationFn: (slug: string) => request<Plugin>({ url: `/plugin-catalog/${slug}/install`, method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.plugins });
      void client.invalidateQueries({ queryKey: ['plugin-catalog'] });
    },
  });

  return {
    projects,
    schedules,
    plugins,
    pluginCatalog,
    projectActions,
    scheduleActions,
    pluginActions,
    installCatalogPlugin,
  };
};
