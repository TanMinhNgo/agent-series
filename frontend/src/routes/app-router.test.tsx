import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { expect, it, vi } from 'vitest';
import { AppRouter } from './app-router';

vi.mock('@/src/hooks/use-auth', () => ({ useAuth: () => ({
  status: { isLoading: false, refetch: vi.fn() },
  session: { checked: true, user: { id: 'user-1', role: 'user' } },
}) }));
vi.mock('@/src/pages/chat-page', () => ({
  ChatPage: ({ chatId, navigate }: { chatId?: string; navigate: (to: string) => void }) => {
    const [pending, setPending] = useState(false);
    return <div>
      <button onClick={() => { setPending(true); navigate('/chat/created'); }}>Send</button>
      <span>{chatId || 'draft'}</span>
      {pending && <span>AI loading</span>}
    </div>;
  },
}));
vi.mock('@/src/pages/admin-page', () => ({ AdminPage: () => null }));
vi.mock('@/src/pages/library-page', () => ({ LibraryPage: () => null }));
vi.mock('@/src/pages/login-page', () => ({ LoginPage: () => null }));
vi.mock('@/src/pages/public-share-page', () => ({ PublicSharePage: () => null }));
vi.mock('@/src/pages/settings-page', () => ({ SettingsPage: () => null }));
vi.mock('@/src/pages/workspace-page', () => ({ WorkspacePage: () => null }));
vi.mock('@/src/pages/project-overview-page', () => ({ ProjectOverviewPage: () => null }));

it('preserves the active chat component and loading state when a draft gets its route', async () => {
  window.history.replaceState(null, '', '/');
  render(<AppRouter />);
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(await screen.findByText('created')).toBeInTheDocument();
  expect(screen.getByText('AI loading')).toBeInTheDocument();
});
