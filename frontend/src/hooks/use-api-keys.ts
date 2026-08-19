import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';

export type ApiKeyMetadata = {
  provider: 'gemini' | 'openai' | 'anthropic';
  keyHint: string;
  validatedAt: string;
  updatedAt: string;
};
type ApiKeyList = { items: ApiKeyMetadata[] };

export function useApiKeys() {
  const client = useQueryClient();
  const keys = useQuery({
    queryKey: ['settings', 'api-keys'],
    queryFn: () => request<ApiKeyList>({ url: '/settings/api-keys' }),
  });
  const save = useMutation({
    mutationFn: ({ provider, apiKey }: { provider: string; apiKey: string }) =>
      request<ApiKeyMetadata>({ url: `/settings/api-keys/${provider}`, method: 'PUT', data: { apiKey } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['settings', 'api-keys'] });
      void client.invalidateQueries({ queryKey: ['config'] });
    },
  });
  const remove = useMutation({
    mutationFn: (provider: string) =>
      request<void>({ url: `/settings/api-keys/${provider}`, method: 'DELETE' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['settings', 'api-keys'] });
      void client.invalidateQueries({ queryKey: ['config'] });
    },
  });
  return { keys, save, remove };
}
