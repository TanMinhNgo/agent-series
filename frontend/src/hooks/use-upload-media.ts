import { useMutation } from '@tanstack/react-query';

import { request } from '@/src/hooks/client';
import type { MediaAttachment } from '@/src/types';

export const useUploadMedia = () =>
  useMutation({
    mutationFn: (files: File[]) => {
      const body = new FormData();
      files.forEach((file) => body.append('files', file));
      return request<MediaAttachment[]>({ url: '/media', method: 'POST', data: body });
    },
  });
