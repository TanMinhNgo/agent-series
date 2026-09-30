import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';
import type { Theme } from '@/src/types';

export type AccountSettings = {
  displayName: string;
  email: string;
  avatarUrl: string | null;
  theme: Theme;
  customInstructions: string;
  autoLearn: boolean;
  defaultProvider: string | null;
  defaultModel: string | null;
};

const key = ['account-settings'];

export function useAccountSettings() {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: key, queryFn: () => request<AccountSettings>({ url: '/settings' }) });
  const save = useMutation({
    mutationFn: (data: AccountSettings) =>
      request<AccountSettings>({ url: '/settings', method: 'PUT', data }),
    onSuccess: (data) => {
      client.setQueryData(key, data);
      void client.invalidateQueries({ queryKey: ['config'] });
      void client.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });
  const clearLearned = useMutation({
    mutationFn: () => request<void>({ url: '/settings/learned-preferences', method: 'DELETE' }),
  });
  return { settings, save, clearLearned };
}
