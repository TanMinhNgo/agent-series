import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type Variables = { chatId: string; provider: string; model: string };

export const useUpdateChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chatId, provider, model }: Variables) =>
      request<Chat>({ url: `/chats/${chatId}`, method: 'PATCH', data: { provider, model } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.chats }),
  });
};
