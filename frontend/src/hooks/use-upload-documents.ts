import { useMutation, useQueryClient } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Document } from '@/src/types';

export const useUploadDocuments = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ files, projectId }: { files: File[]; projectId?: string }) => {
      const body = new FormData();
      files.forEach((file) => body.append('files', file));
      if (projectId) body.append('project_id', projectId);
      return request<Document[]>({ url: '/documents', method: 'POST', data: body });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
};
