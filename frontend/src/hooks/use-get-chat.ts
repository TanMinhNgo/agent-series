import { useQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

export const useGetChat = (chatId?: string) =>
  useQuery({
    queryKey: queryKeys.chat(chatId || 'current'),
    queryFn: () => request<Chat>({ url: `/chats/${chatId}` }),
    enabled: Boolean(chatId),
  });
