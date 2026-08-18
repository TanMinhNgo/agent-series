import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/src/hooks/client';
import type { AdminAudit, AdminCredential, AdminList, AdminOverview, AdminTab, AdminUser } from '@/src/features/admin/types/admin';
import { ADMIN_PAGE_SIZE } from '@/src/features/admin/types/admin';

export function useAdminDashboard({ tab, query, userPage, securityPage }: { tab: AdminTab; query: string; userPage: number; securityPage: number }) {
  const client = useQueryClient();
  const overview = useQuery({ queryKey: ['admin', 'overview'], queryFn: () => request<AdminOverview>({ url: '/admin/overview' }), refetchInterval: 30_000 });
  const users = useQuery({ queryKey: ['admin', 'users', query, userPage], queryFn: () => request<AdminList<AdminUser>>({ url: '/admin/users', params: { q: query || undefined, offset: (userPage - 1) * ADMIN_PAGE_SIZE, limit: ADMIN_PAGE_SIZE } }), enabled: tab === 'users' || tab === 'overview' });
  const credentials = useQuery({ queryKey: ['admin', 'credentials', securityPage], queryFn: () => request<AdminList<AdminCredential>>({ url: '/admin/credentials', params: { offset: (securityPage - 1) * ADMIN_PAGE_SIZE, limit: ADMIN_PAGE_SIZE } }), enabled: tab === 'security' });
  const audit = useQuery({ queryKey: ['admin', 'audit', securityPage], queryFn: () => request<AdminList<AdminAudit>>({ url: '/admin/audit', params: { offset: (securityPage - 1) * ADMIN_PAGE_SIZE, limit: ADMIN_PAGE_SIZE } }), enabled: tab === 'security' || tab === 'overview', refetchInterval: 30_000 });
  const updateUser = useMutation({ mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) => request({ url: `/admin/users/${userId}/active`, method: 'PATCH', data: { isActive } }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['admin', 'users'] }); void client.invalidateQueries({ queryKey: ['admin', 'overview'] }); void client.invalidateQueries({ queryKey: ['admin', 'audit'] }); } });
  const updateModel = useMutation({ mutationFn: ({ provider, modelId, isActive }: { provider: string; modelId: string; isActive: boolean }) => request({ url: `/admin/models/${encodeURIComponent(provider)}/${encodeURIComponent(modelId)}/active`, method: 'PATCH', data: { isActive } }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['admin', 'overview'] }); void client.invalidateQueries({ queryKey: ['admin', 'audit'] }); } });
  return { overview, users, credentials, audit, updateUser, updateModel, refresh: () => client.invalidateQueries({ queryKey: ['admin'] }) };
}
