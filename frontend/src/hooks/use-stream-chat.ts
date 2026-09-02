import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { ApiError, apiBaseUrl, readSse, request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { MediaAttachment, Message } from '@/src/types';

type StreamEvent = (name: string, data: Record<string, unknown>) => void;
type Variables = {
  chatId: string;
  content: string;
  attachments?: MediaAttachment[];
  editAssetId?: string | null;
  runId: string;
  skipOptimisticUser?: boolean;
  replaceAssistantMessageId?: string;
  onEvent: StreamEvent;
  onUserMessageQueued?: () => void;
};

export const useStreamChat = () => {
  const queryClient = useQueryClient();
  const activeRequest = useRef<{ chatId: string; runId: string; controller: AbortController } | null>(null);
  const mutation = useMutation({
    mutationFn: async ({ chatId, content, attachments = [], editAssetId, runId, onEvent }: Variables) => {
      const controller = new AbortController();
      activeRequest.current = { chatId, runId, controller };
      const response = await fetch(`${apiBaseUrl}/chats/${chatId}/stream`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json' },
        // SSE uses fetch instead of the shared Axios client. Include the HTTP-only
        // Google session cookie just as every other authenticated API request does.
        credentials: 'include',
        signal: controller.signal,
        body: JSON.stringify({
          content,
          attachmentIds: attachments.map((item) => item.id),
          runId,
          ...(editAssetId ? { editAssetId } : {}),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new ApiError(payload.detail || 'Không thể gửi câu hỏi.');
      }
      try {
        await readSse(response, (name, data) => {
          if (name === 'message')
            queryClient.setQueryData<Message[]>(queryKeys.messages(chatId), (items = []) => [
              ...items,
              data as unknown as Message,
            ]);
          onEvent(name, data);
        });
      } catch (error) {
        if (!controller.signal.aborted) throw error;
      } finally {
        if (activeRequest.current?.runId === runId) activeRequest.current = null;
      }
    },
    onMutate: ({
      chatId,
      content,
      attachments = [],
      onUserMessageQueued,
      skipOptimisticUser,
      replaceAssistantMessageId,
    }) => {
      queryClient.setQueryData<Message[]>(queryKeys.messages(chatId), (items = []) => [
        ...items.filter((item) => item.messageId !== replaceAssistantMessageId),
        ...(skipOptimisticUser
          ? []
          : [
              {
                messageId: `optimistic-${crypto.randomUUID()}`,
                role: 'user' as const,
                content,
                attachments,
                createdAt: new Date().toISOString(),
                optimistic: true,
              },
            ]),
      ]);
      if (!skipOptimisticUser) onUserMessageQueued?.();
    },
    onSuccess: (_, { chatId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats });
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(chatId) });
    },
  });
  const cancel = async () => {
    const active = activeRequest.current;
    if (!active) return false;
    try {
      await request({ url: `/chats/${active.chatId}/runs/${active.runId}/cancel`, method: 'POST' });
    } finally {
      active.controller.abort();
      activeRequest.current = null;
    }
    return true;
  };
  return { ...mutation, cancel };
};
