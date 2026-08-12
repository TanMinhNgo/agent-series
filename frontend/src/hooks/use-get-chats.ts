import { useQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Chat } from '@/src/types';

export const useGetChats = () =>
  useQuery({ queryKey: queryKeys.chats, queryFn: () => request<Chat[]>({ url: '/chats' }) });
