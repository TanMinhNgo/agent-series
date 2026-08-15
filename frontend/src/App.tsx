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
import type { Chat, Theme } from '@/src/types';

const WorkspacePanel = lazy(() =>
  import('@/src/components/workspace-panel').then(({ WorkspacePanel: Component }) => ({ default: Component })),
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
  return token ? <PublicSharePage token={token} /> : <ChatWorkspace chatId={chatId} libraryPage={pathname === '/library'} navigate={navigate} />;
}

type ChatWorkspaceProps = {
  chatId?: string;
  libraryPage: boolean;
  navigate: (to: string) => void;
};

function ChatWorkspace({ chatId, libraryPage, navigate }: ChatWorkspaceProps) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('agent-series.theme') as Theme) || 'system',
  );
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [userScrollRequest, setUserScrollRequest] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shareChat, setShareChat] = useState<Chat | null>(null);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView | null>(null);
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
  const updateChat = async (chat: Chat, values: { pinned?: boolean; archived?: boolean }) => {
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
    if ((!contentValue.trim() && !files.length) || !activeChat || streamChat.isPending) return;
    const content = contentValue.trim() || 'Hãy phân tích các tệp đính kèm này.';
    setPrompt('');
    setStatus(null);
    setUiError(null);
    try {
      const pdfs = files.filter((file) => file.type === 'application/pdf');
      const images = files.filter((file) => file.type.startsWith('image/'));
      const [uploadedImages] = await Promise.all([
        images.length ? uploadMedia.mutateAsync(images) : Promise.resolve([]),
        pdfs.length ? uploadDocuments.mutateAsync(pdfs) : Promise.resolve([]),
      ]);
      await streamChat.mutateAsync({
        chatId: activeChat.id,
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
            activeChatId={chatId}
            activeNavigation={activeNavigation}
            hasMoreChats={chats.hasNextPage}
            loadingMoreChats={chats.isFetchingNextPage}
            onLoadMoreChats={() => {
              if (chats.hasNextPage && !chats.isFetchingNextPage) void chats.fetchNextPage();
            }}
            theme={theme}
            onCreateChat={() => {
              setWorkspaceView(null);
              void createAndSelect();
            }}
            onSelectChat={(chat: Chat) => {
              setWorkspaceView(null);
              navigate(`/chat/${chat.id}`);
            }}
            onThemeChange={setTheme}
            onRename={(chat, title) => void renameChat(chat, title)}
            onUpdate={(chat, values) => void updateChat(chat, values)}
            onDelete={(chat) => void deleteChat(chat)}
            onShare={setShareChat}
            onOpenLibrary={() => {
              setWorkspaceView(null);
              navigate('/library');
            }}
            onOpenWorkspace={(view) => {
              setWorkspaceView(view);
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
                  setWorkspaceView(null);
                  void createAndSelect();
                }}
                onSelectChat={(chat) => {
                  setWorkspaceView(null);
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
                  setWorkspaceView(null);
                  navigate('/library');
                }}
                onOpenWorkspace={(view) => {
                  setWorkspaceView(view);
                  setSidebarOpen(false);
                }}
              />
            </div>
          </div>
        ) : null}
        <section className="flex min-w-0 flex-col">
          {libraryPage ? null : workspaceView ? (
            <div className="sticky top-0 z-20 flex h-15 items-center border-b bg-background/95 px-4 backdrop-blur sm:px-8">
              <Button variant="ghost" size="sm" onClick={() => setWorkspaceView(null)}>
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
            />
          )}
          {libraryPage ? <LibraryPage /> : workspaceView ? (
            <Suspense fallback={<WorkspacePanelFallback />}>
              <WorkspacePanel view={workspaceView} />
            </Suspense>
          ) : (
            <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-5 sm:px-8 lg:px-12">
              <MessageList
                messages={messages.data || []}
                status={status}
                error={error}
                userScrollRequest={userScrollRequest}
              />
              <ChatComposer
                prompt={prompt}
                busy={streamChat.isPending || uploadDocuments.isPending || uploadMedia.isPending}
                onPromptChange={setPrompt}
                onSubmit={(content, attachments) => void send(content, attachments)}
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
  return <div className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 sm:px-8 lg:px-12"><div className="h-8 w-44 animate-pulse rounded-lg bg-muted" /><div className="h-10 w-full animate-pulse rounded-lg bg-muted" /><div className="grid gap-3 md:grid-cols-2"><div className="h-32 animate-pulse rounded-xl bg-muted" /><div className="h-32 animate-pulse rounded-xl bg-muted" /></div></div>;
}
