import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type UpdateValues = Partial<
  Pick<Chat, 'title' | 'pinned' | 'archived' | 'provider' | 'model' | 'projectId' | 'collectionId'>
>;

export const useChatActions = () => {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: ({ chatId, values }: { chatId: string; values: UpdateValues }) =>
      request<Chat>({ url: `/chats/${chatId}`, method: 'PATCH', data: values }),
    onSuccess: (chat) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats });
      void queryClient.invalidateQueries({ queryKey: queryKeys.chat(chat.id) });
    },
  });
  const remove = useMutation({
    mutationFn: (chatId: string) => request<void>({ url: `/chats/${chatId}`, method: 'DELETE' }),
    onSuccess: (_result, chatId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats });
      queryClient.removeQueries({ queryKey: queryKeys.chat(chatId) });
      queryClient.removeQueries({ queryKey: queryKeys.messages(chatId) });
    },
  });
  return { update, remove };
};
