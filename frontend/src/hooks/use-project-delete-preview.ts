import { useQuery } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';

export function useProjectDeletePreview(projectId?: string) {
  return useQuery({
    queryKey: ['project-delete-preview', projectId],
    queryFn: () =>
      request<{ chats: unknown[]; documents: unknown[]; assets: unknown[]; schedules: unknown[] }>({
        url: `/projects/${projectId}`,
      }),
    enabled: Boolean(projectId),
  });
}
