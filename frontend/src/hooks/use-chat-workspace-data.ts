import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';

export function useChatWorkspaceData(chatId?: string, projectId?: string | null) {
  const client = useQueryClient();
  const collections = useQuery({
    queryKey: queryKeys.collections(projectId),
    queryFn: () =>
      request<{ id: string; name: string; documentIds: string[] }[]>({
        url: `/projects/${projectId}/collections`,
      }),
    enabled: Boolean(projectId),
  });
  const templates = useQuery({
    queryKey: queryKeys.templates(projectId),
    queryFn: () =>
      request<{ id: string; name: string; content: string; projectId: string | null }[]>({
        url: '/templates',
        params: projectId ? { projectId } : {},
      }),
  });
  const pins = useQuery({
    queryKey: queryKeys.chatPins(chatId),
    queryFn: () =>
      request<{ messageId: string; position: number; content: string }[]>({ url: `/chats/${chatId}/pins` }),
    enabled: Boolean(chatId),
  });
  const pin = useMutation({
    mutationFn: ({ messageId, pinned }: { messageId: string; pinned: boolean }) =>
      request({ url: `/messages/${messageId}/pin`, method: 'PATCH', data: { pinned } }),
    onSuccess: () => {
      if (chatId) void client.invalidateQueries({ queryKey: queryKeys.messages(chatId) });
      void client.invalidateQueries({ queryKey: queryKeys.chatPins(chatId) });
    },
  });
  const saveTemplate = useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) =>
      request({ url: '/templates', method: 'POST', data: { name, content, projectId: projectId || null } }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['templates'] }),
  });
  const updateTemplate = useMutation({
    mutationFn: ({
      id,
      name,
      content,
      projectId: templateProjectId,
    }: {
      id: string;
      name: string;
      content: string;
      projectId: string | null;
    }) =>
      request({
        url: `/templates/${id}`,
        method: 'PATCH',
        data: { name, content, projectId: templateProjectId },
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['templates'] }),
  });
  const deleteTemplate = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/templates/${id}`, method: 'DELETE' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['templates'] }),
  });
  return { collections, templates, pins, pin, saveTemplate, updateTemplate, deleteTemplate };
}
