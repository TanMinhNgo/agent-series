import { useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Message } from '@/src/types';

export const useGetChatMessages = (chatId?: string) => {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: chatId ? queryKeys.messages(chatId) : ['chats', 'empty', 'messages'],
    queryFn: async () => {
      const persisted = await request<Message[]>({ url: `/chats/${chatId}/messages` });
      const cached = queryClient.getQueryData<Message[]>(queryKeys.messages(chatId!)) || [];
      const pending = cached.filter((message) => message.optimistic);

      // A newly created chat can be loaded before its streaming request has
      // persisted the first user turn. Keep that local turn visible until the
      // API returns its matching, persisted copy.
      return [
        ...persisted,
        ...pending.filter(
          (pendingMessage) =>
            !persisted.some(
              (message) => message.role === pendingMessage.role && message.content === pendingMessage.content,
            ),
        ),
      ];
    },
    enabled: Boolean(chatId),
  });
};
