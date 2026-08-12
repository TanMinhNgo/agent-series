import { useQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Message } from '@/src/types';

export const useGetChatMessages = (chatId?: string) =>
  useQuery({
    queryKey: chatId ? queryKeys.messages(chatId) : ['chats', 'empty', 'messages'],
    queryFn: () => request<Message[]>({ url: `/chats/${chatId}/messages` }),
    enabled: Boolean(chatId),
  });
