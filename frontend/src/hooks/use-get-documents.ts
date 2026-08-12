import { useQuery } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Document } from '@/src/types';

export const useGetDocuments = () =>
  useQuery({ queryKey: queryKeys.documents, queryFn: () => request<Document[]>({ url: '/documents' }) });
