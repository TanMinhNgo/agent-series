import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiBaseUrl, request } from '@/src/hooks/client';
import { type AuthUser, useAuthStore } from '@/src/stores/use-auth-store';
export type { AuthUser } from '@/src/stores/use-auth-store';
type AuthStatus = { user: AuthUser | null };
export const useAuth = () => {
  const client = useQueryClient();
  const session = useAuthStore();
  const status = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => request<AuthStatus>({ url: '/auth/me' }),
  });
  useEffect(() => {
    if (status.isFetched) useAuthStore.getState().setSession(status.data?.user ?? null);
  }, [status.data?.user, status.isFetched]);
  const startGoogleSignIn = (email: string) => {
    const url = new URL(`${apiBaseUrl}/auth/google/authorize`, window.location.origin);
    url.searchParams.set('email', email.trim().toLowerCase());
    window.location.assign(url.toString());
  };
  const logout = useMutation({
    mutationFn: () => request<void>({ url: '/auth/logout', method: 'POST' }),
    onSuccess: () => {
      useAuthStore.getState().clearSession();
      client.clear();
    },
  });
  return { status, session, startGoogleSignIn, logout };
};
