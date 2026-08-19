import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, apiBaseUrl, readSse } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { MediaAttachment, Message } from '@/src/types';

type StreamEvent = (name: string, data: Record<string, unknown>) => void;
type Variables = {
  chatId: string;
  content: string;
  attachments?: MediaAttachment[];
  onEvent: StreamEvent;
  onUserMessageQueued?: () => void;
};

export const useStreamChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ chatId, content, attachments = [], onEvent }: Variables) => {
      const response = await fetch(`${apiBaseUrl}/chats/${chatId}/stream`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
        // SSE uses fetch instead of the shared Axios client. Include the HTTP-only
        // Google session cookie just as every other authenticated API request does.
        credentials: 'include',
        body: JSON.stringify({ content, attachmentIds: attachments.map((item) => item.id) }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new ApiError(payload.detail || 'Không thể gửi câu hỏi.');
      }
      await readSse(response, (name, data) => {
        if (name === 'message')
          queryClient.setQueryData<Message[]>(queryKeys.messages(chatId), (items = []) => [
            ...items,
            data as unknown as Message,
          ]);
        onEvent(name, data);
      });
    },
    onMutate: ({ chatId, content, attachments = [], onUserMessageQueued }) => {
      queryClient.setQueryData<Message[]>(queryKeys.messages(chatId), (items = []) => [
        ...items,
        { role: 'user', content, attachments, createdAt: new Date().toISOString() },
      ]);
      onUserMessageQueued?.();
    },
    onSuccess: (_, { chatId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats });
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(chatId) });
    },
  });
};
