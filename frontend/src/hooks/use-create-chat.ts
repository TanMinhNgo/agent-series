import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type Variables = { provider?: string; model?: string; contextSourceChatId?: string };

export const useCreateChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Variables) => request<Chat>({ url: '/chats', method: 'POST', data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.chats }),
  });
};
