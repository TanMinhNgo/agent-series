import { Suspense, useEffect, useRef } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom';

import { useAuth } from '@/src/hooks/use-auth';
import { AdminPage } from '@/src/pages/admin-page';
import { ChatPage } from '@/src/pages/chat-page';
import { LibraryPage } from '@/src/pages/library-page';
import { LoginPage } from '@/src/pages/login-page';
import { PublicSharePage } from '@/src/pages/public-share-page';
import { SettingsPage } from '@/src/pages/settings-page';
import { WorkspacePage } from '@/src/pages/workspace-page';

function LoadingPage() {
  return (
    <main className="grid min-h-[100dvh] place-items-center text-sm text-muted-foreground">
      Đang kiểm tra phiên đăng nhập...
    </main>
  );
}

function AuthSessionBridge() {
  const auth = useAuth();
  const refetchAuth = auth.status.refetch;
  const location = useLocation();
  const navigate = useNavigate();
  const lastUserId = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const refresh = () => void refetchAuth();
    const channel =
      typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('agent-series-auth');
    channel?.addEventListener('message', refresh);
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'agent-series.auth-event') refresh();
    };
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      channel?.removeEventListener('message', refresh);
      channel?.close();
      window.removeEventListener('storage', onStorage);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refetchAuth]);

  useEffect(() => {
    if (!auth.session.checked) return;
    const currentUserId = auth.session.user?.id ?? null;
    const isGoogleCallback = new URLSearchParams(location.search).get('auth') === 'google';
    if ((lastUserId.current !== undefined && lastUserId.current !== currentUserId) || isGoogleCallback) {
      const channel =
        typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('agent-series-auth');
      channel?.postMessage({ type: 'session-changed' });
      channel?.close();
      localStorage.setItem('agent-series.auth-event', String(Date.now()));
      if (isGoogleCallback) {
        const returnTo = sessionStorage.getItem('agent-series.auth-return-to');
        sessionStorage.removeItem('agent-series.auth-return-to');
        navigate(returnTo || location.pathname, { replace: true });
      }
    }
    lastUserId.current = currentUserId;
  }, [auth.session.checked, auth.session.user?.id, location.pathname, location.search, navigate]);
  return null;
}

function PublicShareRoute() {
  const { token = '' } = useParams();
  return (
    <Suspense fallback={<LoadingPage />}>
      <PublicSharePage token={token} />
    </Suspense>
  );
}

function ProtectedRoutes() {
  const auth = useAuth();
  const navigate = useNavigate();
  if (auth.status.isLoading || !auth.session.checked) return <LoadingPage />;
  if (!auth.session.user) return <Navigate to="/login" replace />;
  const props = { isSystemAdmin: auth.session.user.role === 'system_admin', navigate };
  return (
    <Routes>
      <Route index element={<ChatPage {...props} />} />
      <Route path="chat/:chatId" element={<ChatRoute {...props} />} />
      <Route path="library" element={<LibraryPage {...props} />} />
      <Route path="projects" element={<WorkspacePage {...props} view="projects" />} />
      <Route path="schedules" element={<WorkspacePage {...props} view="schedules" />} />
      <Route path="plugins" element={<WorkspacePage {...props} view="plugins" />} />
      <Route path="members" element={<WorkspacePage {...props} view="members" />} />
      <Route path="settings/api-keys" element={<SettingsPage {...props} />} />
      <Route path="admin" element={<Navigate to="/admin/overview" replace />} />
      <Route
        path="admin/:view"
        element={props.isSystemAdmin ? <AdminRoute {...props} /> : <Navigate to="/" replace />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function ChatRoute(props: { isSystemAdmin: boolean; navigate: (to: string) => void }) {
  const { chatId } = useParams();
  return <ChatPage {...props} chatId={chatId} />;
}

function AdminRoute(props: { isSystemAdmin: boolean; navigate: (to: string) => void }) {
  const { view } = useParams();
  const validViews = ['overview', 'users', 'system', 'security'] as const;
  if (!validViews.includes(view as (typeof validViews)[number]))
    return <Navigate to="/admin/overview" replace />;
  return <AdminPage {...props} view={view as (typeof validViews)[number]} />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <AuthSessionBridge />
      <Routes>
        <Route path="/share/:token" element={<PublicShareRoute />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<ProtectedRoutes />} />
      </Routes>
    </BrowserRouter>
  );
}
