import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type Variables = {
  provider?: string;
  model?: string;
  contextSourceChatId?: string;
  projectId?: string;
  mode?: Chat['mode'];
};

export const useCreateChat = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Variables) => request<Chat>({ url: '/chats', method: 'POST', data }),
    onSuccess: (chat) => {
      queryClient.setQueryData(queryKeys.chat(chat.id), chat);
      void queryClient.invalidateQueries({ queryKey: queryKeys.chats, exact: true });
    },
  });
};
