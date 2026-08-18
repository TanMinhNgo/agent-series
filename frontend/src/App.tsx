import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';

import { AppSidebar } from '@/src/components/app-sidebar';
import type { SidebarNavigation } from '@/src/components/app-sidebar';
import { ChatShareDialog } from '@/src/components/chat-share-dialog';
import { ChatComposer } from '@/src/components/chat-composer';
import { ChatHeader } from '@/src/components/chat-header';
import { MessageList } from '@/src/components/message-list';
import { LibraryPage } from '@/src/components/library-page';
import { PublicSharePage } from '@/src/components/public-share-page';
import { Button } from '@/components/ui/button';
import type { WorkspaceView } from '@/src/components/workspace-panel';
import { useChatActions } from '@/src/hooks/use-chat-actions';
import { useCreateChat } from '@/src/hooks/use-create-chat';
import { useGetChatMessages } from '@/src/hooks/use-get-chat-messages';
import { useGetChat } from '@/src/hooks/use-get-chat';
import { useGetChats } from '@/src/hooks/use-get-chats';
import { useGetConfig } from '@/src/hooks/use-get-config';
import { useGetDocuments } from '@/src/hooks/use-get-documents';
import { useStreamChat } from '@/src/hooks/use-stream-chat';
import { useUploadDocuments } from '@/src/hooks/use-upload-documents';
import { useUploadMedia } from '@/src/hooks/use-upload-media';
import { useWorkspace } from '@/src/hooks/use-workspace';
import { queryKeys } from '@/src/hooks/query-keys';
import { request } from '@/src/hooks/client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Chat, Theme } from '@/src/types';

const WorkspacePanel = lazy(() =>
  import('@/src/components/workspace-panel').then(({ WorkspacePanel: Component }) => ({
    default: Component,
  })),
);

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname);
  const navigate = useCallback((to: string) => {
    if (window.location.pathname === to) return;
    window.history.pushState(null, '', to);
    setPathname(to);
  }, []);

  useEffect(() => {
    const handlePopState = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const token = /^\/share\/([^/]+)\/?$/.exec(pathname)?.[1];
  const chatId = /^\/chat\/([^/]+)\/?$/.exec(pathname)?.[1];
  const workspaceView = /^\/(projects|schedules|plugins)\/?$/.exec(pathname)?.[1] as
    WorkspaceView | undefined;
  return token ? (
    <PublicSharePage token={token} />
  ) : (
    <ChatWorkspace
      chatId={chatId}
      libraryPage={pathname === '/library'}
      workspaceView={workspaceView}
      navigate={navigate}
    />
  );
}

type ChatWorkspaceProps = {
  chatId?: string;
  libraryPage: boolean;
  workspaceView?: WorkspaceView;
  navigate: (to: string) => void;
};

function ChatWorkspace({ chatId, libraryPage, workspaceView, navigate }: ChatWorkspaceProps) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('agent-series.theme') as Theme) || 'system',
  );
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [userScrollRequest, setUserScrollRequest] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shareChat, setShareChat] = useState<Chat | null>(null);
  const [messageSearch, setMessageSearch] = useState('');
  const activeNavigation: SidebarNavigation | undefined = libraryPage
    ? 'library'
    : workspaceView || (chatId ? undefined : 'chat');

  const config = useGetConfig();
  const chats = useGetChats();
  const selectedChat = useGetChat(chatId);
  const documents = useGetDocuments();
  const activeChat = useMemo(
    () => selectedChat.data || chats.data.find((chat) => chat.id === chatId) || null,
    [chatId, chats.data, selectedChat.data],
  );
  const messages = useGetChatMessages(activeChat?.id);
  const createChat = useCreateChat();
  const chatActions = useChatActions();
  const uploadDocuments = useUploadDocuments();
  const uploadMedia = useUploadMedia();
  const streamChat = useStreamChat();
  const { projects } = useWorkspace();
  const queryClient = useQueryClient();
  const collections = useQuery({
    queryKey: queryKeys.collections(activeChat?.projectId),
    queryFn: () => request<{ id: string; name: string; documentIds: string[] }[]>({ url: `/projects/${activeChat?.projectId}/collections` }),
    enabled: Boolean(activeChat?.projectId),
  });
  const templates = useQuery({
    queryKey: queryKeys.templates(activeChat?.projectId),
    queryFn: () => request<{ id: string; name: string; content: string; projectId: string | null }[]>({ url: '/templates', params: activeChat?.projectId ? { projectId: activeChat.projectId } : {} }),
  });
  const searchResults = useQuery({
    queryKey: queryKeys.messageSearch(messageSearch, activeChat?.projectId),
    queryFn: () => request<{ messageId: string; content: string; chat: Chat }[]>({ url: '/messages/search', params: { q: messageSearch, ...(activeChat?.projectId ? { projectId: activeChat.projectId } : {}) } }),
    enabled: messageSearch.trim().length > 1,
  });
  const bookmarks = useQuery({
    queryKey: queryKeys.bookmarks(activeChat?.projectId),
    queryFn: () => request<{ messageId: string; content: string; chat: Chat }[]>({ url: '/bookmarks', params: activeChat?.projectId ? { projectId: activeChat.projectId } : {} }),
  });
  const branchChat = useMutation({
    mutationFn: (messageId: string) => request<Chat>({ url: `/chats/${activeChat?.id}/branch/${messageId}`, method: 'POST' }),
    onSuccess: (chat) => {
      void queryClient.invalidateQueries({ queryKey: ['chats'] });
      navigate(`/chat/${chat.id}`);
    },
  });
  const bookmark = useMutation({
    mutationFn: ({ messageId, bookmarked }: { messageId: string; bookmarked: boolean }) => request({ url: `/messages/${messageId}/bookmark`, method: 'PATCH', data: { bookmarked } }),
    onSuccess: () => {
      if (activeChat) void queryClient.invalidateQueries({ queryKey: queryKeys.messages(activeChat.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookmarks(activeChat?.projectId) });
    },
  });
  const saveTemplate = useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) => request({ url: '/templates', method: 'POST', data: { name, content, projectId: activeChat?.projectId || null } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['templates'] }),
  });
  const updateTemplate = useMutation({
    mutationFn: ({ id, name, content, projectId }: { id: string; name: string; content: string; projectId: string | null }) => request({ url: `/templates/${id}`, method: 'PATCH', data: { name, content, projectId } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['templates'] }),
  });
  const deleteTemplate = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/templates/${id}`, method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['templates'] }),
  });

  useEffect(() => {
    document.documentElement.classList.toggle(
      'dark',
      theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches),
    );
    localStorage.setItem('agent-series.theme', theme);
  }, [theme]);

  const error =
    uiError ||
    config.error?.message ||
    chats.error?.message ||
    selectedChat.error?.message ||
    documents.error?.message ||
    messages.error?.message ||
    createChat.error?.message ||
    chatActions.update.error?.message ||
    chatActions.remove.error?.message ||
    uploadDocuments.error?.message ||
    uploadMedia.error?.message ||
    streamChat.error?.message ||
    null;
  const createAndSelect = async (provider?: string, model?: string, contextSourceChatId?: string) => {
    setUiError(null);
    const chat = await createChat.mutateAsync({ provider, model, contextSourceChatId });
    navigate(`/chat/${chat.id}`);
  };
  const changeModel = async (event: ChangeEvent<HTMLSelectElement>) => {
    if (!activeChat) return;
    const model = event.target.value;
    if (model === activeChat.model) return;
    setUiError(null);
    await createAndSelect(activeChat.provider, model, activeChat.id);
  };
  const changeProvider = async (event: ChangeEvent<HTMLSelectElement>) => {
    const provider = event.target.value;
    if (provider === activeChat?.provider) return;
    const model = config.data?.providers[provider]?.[0];
    if (model) await createAndSelect(provider, model, activeChat?.id);
  };
  const updateChat = async (
    chat: Chat,
    values: { pinned?: boolean; archived?: boolean; projectId?: string | null },
  ) => {
    setUiError(null);
    await chatActions.update.mutateAsync({ chatId: chat.id, values });
    if (values.archived && chat.id === activeChat?.id) navigate('/');
  };
  const renameChat = async (chat: Chat, title: string) => {
    setUiError(null);
    await chatActions.update.mutateAsync({ chatId: chat.id, values: { title } });
  };
  const deleteChat = async (chat: Chat) => {
    setUiError(null);
    await chatActions.remove.mutateAsync(chat.id);
    if (chat.id === activeChat?.id) navigate('/');
  };
  const send = async (contentValue: string, files: File[]) => {
    if ((!contentValue.trim() && !files.length) || createChat.isPending || streamChat.isPending) return;
    const content = contentValue.trim() || 'Hãy phân tích các tệp đính kèm này.';
    setPrompt('');
    setStatus(null);
    setUiError(null);
    try {
      const chat = activeChat || (await createChat.mutateAsync({}));
      if (!activeChat) navigate(`/chat/${chat.id}`);
      const pdfs = files.filter((file) => file.type === 'application/pdf');
      const images = files.filter((file) => file.type.startsWith('image/'));
      const [uploadedImages] = await Promise.all([
        images.length ? uploadMedia.mutateAsync(images) : Promise.resolve([]),
        pdfs.length
          ? uploadDocuments.mutateAsync({ files: pdfs, projectId: chat.projectId || undefined })
          : Promise.resolve([]),
      ]);
      await streamChat.mutateAsync({
        chatId: chat.id,
        content,
        attachments: uploadedImages,
        onEvent: (name, data) => {
          if (name === 'status') setStatus(String(data.message));
          if (name === 'tool_call') setStatus(`Đang dùng ${String(data.name)}...`);
          if (name === 'tool_result') setStatus(`Đã nhận kết quả từ ${String(data.name)}.`);
          if (name === 'message') setStatus(null);
          if (name === 'error') setUiError(String(data.message));
        },
        onUserMessageQueued: () => setUserScrollRequest((request) => request + 1),
      });
    } catch (reason) {
      setUiError(reason instanceof Error ? reason.message : 'Gửi tin nhắn thất bại.');
    }
  };

  return (
    <main className="min-h-[100dvh] bg-background text-foreground">
      <div className="grid min-h-[100dvh] w-full lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="hidden lg:block">
          <AppSidebar
            chats={chats.data || []}
            projects={projects.data || []}
            activeChatId={chatId}
            activeNavigation={activeNavigation}
            hasMoreChats={chats.hasNextPage}
            loadingMoreChats={chats.isFetchingNextPage}
            onLoadMoreChats={() => {
              if (chats.hasNextPage && !chats.isFetchingNextPage) void chats.fetchNextPage();
            }}
            theme={theme}
            onCreateChat={() => {
              void createAndSelect();
            }}
            onSelectChat={(chat: Chat) => {
              navigate(`/chat/${chat.id}`);
            }}
            onThemeChange={setTheme}
            onRename={(chat, title) => void renameChat(chat, title)}
            onUpdate={(chat, values) => void updateChat(chat, values)}
            onDelete={(chat) => void deleteChat(chat)}
            onShare={setShareChat}
            onOpenLibrary={() => {
              navigate('/library');
            }}
            onOpenWorkspace={(view) => {
              navigate(`/${view}`);
            }}
          />
        </div>
        {sidebarOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-black/55"
              aria-label="Đóng lịch sử chat"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 w-[min(86vw,340px)] shadow-2xl">
              <AppSidebar
                chats={chats.data || []}
                projects={projects.data || []}
                activeChatId={chatId}
                activeNavigation={activeNavigation}
                hasMoreChats={chats.hasNextPage}
                loadingMoreChats={chats.isFetchingNextPage}
                onLoadMoreChats={() => {
                  if (chats.hasNextPage && !chats.isFetchingNextPage) void chats.fetchNextPage();
                }}
                theme={theme}
                onCreateChat={() => {
                  setSidebarOpen(false);
                  void createAndSelect();
                }}
                onSelectChat={(chat) => {
                  setSidebarOpen(false);
                  navigate(`/chat/${chat.id}`);
                }}
                onThemeChange={setTheme}
                onRename={(chat, title) => void renameChat(chat, title)}
                onUpdate={(chat, values) => void updateChat(chat, values)}
                onDelete={(chat) => void deleteChat(chat)}
                onShare={(chat) => {
                  setShareChat(chat);
                  setSidebarOpen(false);
                }}
                onOpenLibrary={() => {
                  setSidebarOpen(false);
                  navigate('/library');
                }}
                onOpenWorkspace={(view) => {
                  setSidebarOpen(false);
                  navigate(`/${view}`);
                }}
              />
            </div>
          </div>
        ) : null}
        <section className="flex min-w-0 flex-col">
          {libraryPage ? null : workspaceView ? (
            <div className="sticky top-0 z-20 flex h-15 items-center border-b bg-background/95 px-4 backdrop-blur sm:px-8">
              <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
                ← Chat
              </Button>
            </div>
          ) : (
            <ChatHeader
              chat={activeChat}
              config={config.data || null}
              busy={createChat.isPending || streamChat.isPending}
              onOpenSidebar={() => setSidebarOpen(true)}
              onProviderChange={(event) => void changeProvider(event)}
              onModelChange={(event) => void changeModel(event)}
              collections={collections.data || []}
              onCollectionChange={(collectionId) => activeChat && chatActions.update.mutate({ chatId: activeChat.id, values: { collectionId } })}
            />
          )}
          {libraryPage ? (
            <LibraryPage />
          ) : workspaceView ? (
            <Suspense fallback={<WorkspacePanelFallback />}>
              <WorkspacePanel view={workspaceView} />
            </Suspense>
          ) : (
            <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-5 sm:px-8 lg:px-12">
              <label className="mb-3 flex items-center gap-2 rounded-lg border px-3 text-sm"><span>⌕</span><input className="w-full bg-transparent py-2 outline-none" value={messageSearch} onChange={(event) => setMessageSearch(event.target.value)} placeholder="Tìm trong chat…" /></label>
              {messageSearch.trim().length > 1 ? <div className="mb-4 space-y-2 rounded-lg border p-3 text-sm">{(searchResults.data || []).map((result) => <button key={result.messageId} className="block w-full text-left hover:underline" onClick={() => navigate(`/chat/${result.chat.id}#message-${result.messageId}`)}><span className="font-medium">{result.chat.title}: </span>{result.content}</button>)}{!searchResults.isLoading && !searchResults.data?.length ? <p className="text-muted-foreground">Không có kết quả.</p> : null}</div> : null}
              {bookmarks.data?.length ? <div className="mb-4 flex gap-2 overflow-x-auto"><span className="shrink-0 text-xs text-muted-foreground">Đã lưu:</span>{bookmarks.data.slice(0, 5).map((item) => <button key={item.messageId} className="shrink-0 rounded-full border px-2 py-1 text-xs hover:bg-muted" onClick={() => navigate(`/chat/${item.chat.id}#message-${item.messageId}`)}>{item.content.slice(0, 36)}</button>)}</div> : null}
              <MessageList
                messages={messages.data || []}
                status={status}
                error={error}
                userScrollRequest={userScrollRequest}
                onBranch={(message) => message.messageId && branchChat.mutate(message.messageId)}
                onBookmark={(message) => message.messageId && bookmark.mutate({ messageId: message.messageId, bookmarked: !message.bookmarked })}
              />
              <ChatComposer
                prompt={prompt}
                busy={streamChat.isPending || uploadDocuments.isPending || uploadMedia.isPending}
                onPromptChange={setPrompt}
                onSubmit={(content, attachments) => void send(content, attachments)}
                templates={templates.data || []}
                onSelectTemplate={(content) => setPrompt(content)}
                onSaveTemplate={(name, content) => saveTemplate.mutate({ name, content })}
                onEditTemplate={(template) => { const name = window.prompt('Tên template', template.name); const content = name ? window.prompt('Nội dung template', template.content) : null; if (name?.trim() && content?.trim()) updateTemplate.mutate({ id: template.id, name, content, projectId: template.projectId }); }}
                onDeleteTemplate={(id) => deleteTemplate.mutate(id)}
              />
            </div>
          )}
        </section>
      </div>
      {shareChat ? <ChatShareDialog chat={shareChat} onClose={() => setShareChat(null)} /> : null}
    </main>
  );
}

function WorkspacePanelFallback() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 sm:px-8 lg:px-12">
      <div className="h-8 w-44 animate-pulse rounded-lg bg-muted" />
      <div className="h-10 w-full animate-pulse rounded-lg bg-muted" />
      <div className="grid gap-3 md:grid-cols-2">
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}
