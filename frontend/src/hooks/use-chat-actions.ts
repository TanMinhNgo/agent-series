import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type UpdateValues = Partial<Pick<Chat, 'title' | 'pinned' | 'archived' | 'projectId'>>;

export const useChatActions = () => {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: ({ chatId, values }: { chatId: string; values: UpdateValues }) =>
      request<Chat>({ url: `/chats/${chatId}`, method: 'PATCH', data: values }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.chats }),
  });
  const remove = useMutation({
    mutationFn: (chatId: string) => request<void>({ url: `/chats/${chatId}`, method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.chats }),
  });
  return { update, remove };
};
