export type AdminTab = 'overview' | 'users' | 'system' | 'security';
export type AdminModel = { id: string; displayName: string; isActive: boolean };
export type AdminOverview = {
  counts: { users: number; activeUsers: number; chats: number; projects: number; documents: number };
  worker: {
    online: boolean;
    queued: number;
    running: number;
    failed: number;
    lastHeartbeatAt: string | null;
    lastError: string | null;
  };
  providers: Record<string, { models: AdminModel[]; configured: boolean }>;
};
export type AdminUser = {
  id: string;
  email: string;
  displayName: string | null;
  role: string;
  isActive: boolean;
  createdAt: string;
  lastSignInAt: string | null;
};
export type AdminCredential = {
  id: string;
  userId: string;
  userEmail: string;
  provider: string;
  keyHint: string;
  validatedAt: string;
  updatedAt: string;
};
export type AdminPluginConnection = {
  id: string;
  userId: string;
  userEmail: string;
  connectorSlug: string;
  status: 'connected' | 'reauth_required' | 'not_connected';
  scopeCount: number;
  expiresAt: string | null;
  createdAt: string;
  updatedAt: string;
};
export type AdminAudit = {
  id: string;
  eventType: string;
  actorEmail: string | null;
  subjectEmail: string | null;
  summary: string | null;
  createdAt: string;
};
export type AdminList<T> = { items: T[]; total: number };
export const ADMIN_PAGE_SIZE = 10;
