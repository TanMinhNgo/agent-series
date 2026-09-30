import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';

import { ChatWorkspace } from './chat-workspace-page';

const mutations = vi.hoisted(() => ({ create: vi.fn(), stream: vi.fn() }));
const chat = { id: 'created', provider: 'gemini', model: 'test', mode: 'standard', projectId: null };
const idle = { isPending: false, error: null, mutate: vi.fn(), mutateAsync: vi.fn() };

vi.mock('@/src/components/app-sidebar', () => ({ AppSidebar: () => null }));
vi.mock('@/src/components/chat-header', () => ({ ChatHeader: () => null }));
vi.mock('@/src/components/artifact-panel', () => ({ ArtifactPanel: () => null }));
vi.mock('@/src/components/message-list', () => ({
  MessageList: ({
    status,
    isResponding,
    messages,
    error,
  }: {
    status: string | null;
    isResponding: boolean;
    messages: unknown[];
    error: string | null;
  }) => (
    <div>
      <span>Messages: {messages.length}</span>
      {(status || isResponding) && <span>AI thinking</span>}
      {error && <span>{error}</span>}
    </div>
  ),
}));
vi.mock('@/src/components/chat-composer', () => ({
  ChatComposer: ({
    onSubmit,
    onPromptChange,
    busy,
    prompt,
  }: {
    onSubmit: (text: string, files: File[]) => void;
    onPromptChange: (text: string) => void;
    busy: boolean;
    prompt: string;
  }) => (
    <>
      <span>Draft: {prompt}</span>
      <input aria-label="Prompt" value={prompt} onChange={(event) => onPromptChange(event.target.value)} />
      <button disabled={busy} onClick={() => onSubmit(prompt, [])}>
        Send
      </button>
    </>
  ),
}));
vi.mock('@/src/hooks/use-auth', () => ({
  useAuth: () => ({ session: { user: { id: 'user' } }, logout: idle }),
}));
vi.mock('@/src/hooks/use-get-config', () => ({
  useGetConfig: () => ({
    data: { providers: { gemini: ['test'] }, defaultProvider: 'gemini', defaultModel: 'test' },
  }),
}));
vi.mock('@/src/hooks/use-get-chats', () => ({ useGetChats: () => ({ data: [], hasNextPage: false }) }));
vi.mock('@/src/hooks/use-get-chat', () => ({ useGetChat: (id?: string) => ({ data: id ? chat : null }) }));
vi.mock('@/src/hooks/use-get-chat-messages', () => ({ useGetChatMessages: () => ({ data: [] }) }));
vi.mock('@/src/hooks/use-create-chat', () => ({
  useCreateChat: () => ({ ...idle, mutateAsync: mutations.create }),
}));
vi.mock('@/src/hooks/use-chat-actions', () => ({
  useChatActions: () => ({ update: idle, remove: idle, markRead: idle }),
}));
vi.mock('@/src/hooks/use-get-documents', () => ({ useGetDocuments: () => ({ data: [] }) }));
vi.mock('@/src/hooks/use-upload-documents', () => ({ useUploadDocuments: () => idle }));
vi.mock('@/src/hooks/use-upload-media', () => ({ useUploadMedia: () => idle }));
vi.mock('@/src/hooks/use-stream-chat', () => ({
  useStreamChat: () => ({ ...idle, mutateAsync: mutations.stream, cancel: vi.fn() }),
}));
vi.mock('@/src/hooks/use-workspace', () => ({
  useWorkspace: () => ({
    projects: { data: [] },
    workspaces: { data: [] },
    activeWorkspaceId: null,
    selectWorkspace: vi.fn(),
  }),
}));
vi.mock('@/src/hooks/use-chat-workspace-data', () => ({
  useChatWorkspaceData: () => ({
    collections: { data: [] },
    templates: { data: [] },
    pins: { data: [] },
    pin: idle,
    scheduleProposal: idle,
    saveTemplate: idle,
    updateTemplate: idle,
    deleteTemplate: idle,
  }),
}));

beforeEach(() => {
  mutations.create.mockReset();
  mutations.stream.mockReset();
});

it('shows AI thinking only after the new chat route is active', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  let resolveCreate!: (value: typeof chat) => void;
  mutations.create.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveCreate = resolve;
    }),
  );
  mutations.stream.mockReturnValueOnce(new Promise(() => {}));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Page() {
    const [chatId, setChatId] = useState<string>();
    return (
      <QueryClientProvider client={client}>
        <span>Route: {chatId || 'home'}</span>
        <ChatWorkspace
          chatId={chatId}
          libraryPage={false}
          adminPage={false}
          isSystemAdmin={false}
          navigate={(to) => setChatId(to.split('/').pop())}
        />
      </QueryClientProvider>
    );
  }
  render(<Page />);
  fireEvent.change(screen.getByRole('textbox', { name: 'Prompt' }), { target: { value: 'Hello' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(screen.getByText('Route: home')).toBeInTheDocument();
  expect(screen.getByText('Đang tạo cuộc trò chuyện...')).toBeInTheDocument();
  expect(screen.queryByText('AI thinking')).not.toBeInTheDocument();
  expect(mutations.stream).not.toHaveBeenCalled();

  await act(async () => resolveCreate(chat));
  expect(screen.getByText('Route: created')).toBeInTheDocument();
  expect(screen.getByText('Messages: 1')).toBeInTheDocument();
  expect(screen.getByText('AI thinking')).toBeInTheDocument();
  expect(mutations.stream).toHaveBeenCalledOnce();
});

it('keeps the home draft available when chat creation fails', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  mutations.create.mockRejectedValueOnce(new Error('Create failed'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatWorkspace libraryPage={false} adminPage={false} isSystemAdmin={false} navigate={vi.fn()} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByRole('textbox', { name: 'Prompt' }), { target: { value: 'Hello' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(await screen.findByText('Create failed')).toBeInTheDocument();
  expect(screen.getByText('Draft: Hello')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  expect(screen.queryByText('AI thinking')).not.toBeInTheDocument();
  expect(mutations.stream).not.toHaveBeenCalled();
});
