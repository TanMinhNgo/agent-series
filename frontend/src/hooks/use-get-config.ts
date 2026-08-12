import { useQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Config } from '@/src/types';

export const useGetConfig = () =>
  useQuery({ queryKey: queryKeys.config, queryFn: () => request<Config>({ url: '/config' }) });
