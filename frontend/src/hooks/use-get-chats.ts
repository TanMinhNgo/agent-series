import { useInfiniteQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

type ChatPage = {
  items: Chat[];
  total: number;
  nextOffset: number | null;
};

const CHAT_PAGE_SIZE = 40;

export const useGetChats = () => {
  const query = useInfiniteQuery({
    queryKey: queryKeys.chats,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      request<ChatPage>({ url: '/chats', params: { offset: pageParam, limit: CHAT_PAGE_SIZE } }),
    getNextPageParam: (lastPage) => lastPage.nextOffset ?? undefined,
  });

  return {
    ...query,
    data: query.data?.pages.flatMap((page) => page.items) ?? [],
    total: query.data?.pages[0]?.total ?? 0,
  };
};
