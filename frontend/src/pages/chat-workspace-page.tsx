import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import { AppSidebar } from '@/src/components/app-sidebar';
import type { SidebarNavigation } from '@/src/components/app-sidebar';
import { ChatComposer } from '@/src/components/chat-composer';
import { ChatHeader } from '@/src/components/chat-header';
import { MessageList } from '@/src/components/message-list';
import { Button } from '@/components/ui/button';
import type { WorkspaceView } from '@/src/components/workspace-panel';
import type { AdminTab } from '@/src/features/admin/types/admin';
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
import { useAuth } from '@/src/hooks/use-auth';
import { useChatWorkspaceData } from '@/src/hooks/use-chat-workspace-data';
import { request } from '@/src/hooks/client';
import type { Chat, Message, Theme } from '@/src/types';
import { SettingsApiKeysPage } from '@/src/pages/settings-api-keys-page';

const WorkspacePanel = lazy(() =>
  import('@/src/components/workspace-panel').then(({ WorkspacePanel: Component }) => ({
    default: Component,
  })),
);
const LibraryPage = lazy(() =>
  import('@/src/components/library-page').then(({ LibraryPage: Component }) => ({ default: Component })),
);
const ChatShareDialog = lazy(() =>
  import('@/src/components/chat-share-dialog').then(({ ChatShareDialog: Component }) => ({
    default: Component,
  })),
);
const AdminPage = lazy(() =>
  import('@/src/features/admin/pages/admin-dashboard-page').then(({ AdminDashboardPage: Component }) => ({
    default: Component,
  })),
);

type ChatWorkspaceProps = {
  chatId?: string;
  libraryPage: boolean;
  workspaceView?: WorkspaceView;
  adminPage: boolean;
  adminView?: AdminTab;
  settingsPage?: boolean;
  isSystemAdmin: boolean;
  navigate: (to: string) => void;
};

const NEW_CHAT_SELECTION_KEY = 'agent-series.new-chat-selection';

type DraftSelection = { provider: string; model: string };
type TemplateDraft = {
  id?: string;
  name: string;
  content: string;
  projectId: string | null;
};

function savedNewChatSelection(): DraftSelection {
  try {
    const value = sessionStorage.getItem(NEW_CHAT_SELECTION_KEY);
    if (!value) return { provider: '', model: '' };
    const selection: unknown = JSON.parse(value);
    if (
      typeof selection === 'object' &&
      selection !== null &&
      typeof (selection as DraftSelection).provider === 'string' &&
      typeof (selection as DraftSelection).model === 'string'
    ) {
      return selection as DraftSelection;
    }
  } catch {
    // A malformed browser value should fall back to the configured default.
  }
  return { provider: '', model: '' };
}

export function ChatWorkspace({
  chatId,
  libraryPage,
  workspaceView,
  adminPage,
  adminView,
  settingsPage = false,
  isSystemAdmin,
  navigate,
}: ChatWorkspaceProps) {
  const auth = useAuth();
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('agent-series.theme') as Theme) || 'system',
  );
  const [prompt, setPrompt] = useState('');
  const [draftSelection, setDraftSelection] = useState(savedNewChatSelection);
  const [status, setStatus] = useState<string | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [userScrollRequest, setUserScrollRequest] = useState(0);
  const [runwayChatId, setRunwayChatId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shareChat, setShareChat] = useState<Chat | null>(null);
  const [templateDraft, setTemplateDraft] = useState<TemplateDraft | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  // React state updates asynchronously, so `streamChat.isPending` alone cannot
  // stop an Enter key and a click (or two rapid clicks) from starting two turns.
  const sendLock = useRef(false);
  const logoutToLogin = () => auth.logout.mutate(undefined, { onSuccess: () => navigate('/login') });
  const activeNavigation: SidebarNavigation | undefined = libraryPage
    ? 'library'
    : adminPage
      ? 'admin'
      : settingsPage
        ? 'settings'
        : workspaceView || (chatId ? undefined : 'chat');
  const isChatView = !libraryPage && !workspaceView && !adminPage && !settingsPage;

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
  const {
    collections,
    templates,
    pins,
    pin,
    scheduleProposal,
    saveTemplate,
    updateTemplate,
    deleteTemplate,
  } = useChatWorkspaceData(activeChat?.id, activeChat?.projectId);
  const draftProvider =
    config.data && config.data.providers[draftSelection.provider]
      ? draftSelection.provider
      : (config.data?.defaultProvider ?? draftSelection.provider);
  const draftModels = config.data?.providers[draftProvider] || [];
  const draftModel = draftModels.includes(draftSelection.model)
    ? draftSelection.model
    : draftModels[0] || config.data?.defaultModel || draftSelection.model;

  useEffect(() => {
    if (activeChat?.isUnread && !chatActions.markRead.isPending) {
      chatActions.markRead.mutate(activeChat.id);
    }
  }, [activeChat?.id, activeChat?.isUnread, chatActions.markRead]);

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
  const openTemplateEditor = (draft: TemplateDraft) => {
    saveTemplate.reset();
    updateTemplate.reset();
    setTemplateDraft(draft);
  };
  const saveTemplateDraft = async () => {
    if (!templateDraft) return;
    const name = templateDraft.name.trim();
    const content = templateDraft.content.trim();
    if (!name || !content) return;
    try {
      if (templateDraft.id) {
        await updateTemplate.mutateAsync({
          id: templateDraft.id,
          name,
          content,
          projectId: templateDraft.projectId,
        });
      } else {
        await saveTemplate.mutateAsync({ name, content });
      }
      setTemplateDraft(null);
    } catch {
      // The modal renders the mutation error and keeps the entered values.
    }
  };
  const startNewChat = () => {
    setUiError(null);
    setPrompt('');
    setStatus(null);
    setRunwayChatId(null);
    if (activeChat) {
      const selection = { provider: activeChat.provider, model: activeChat.model };
      sessionStorage.setItem(NEW_CHAT_SELECTION_KEY, JSON.stringify(selection));
      setDraftSelection(selection);
    }
    setSidebarOpen(false);
    navigate('/');
  };
  const changeModel = async (event: ChangeEvent<HTMLSelectElement>) => {
    const model = event.target.value;
    if (!activeChat) {
      setDraftSelection((selection) => ({ ...selection, model }));
      return;
    }
    if (model === activeChat.model) return;
    setUiError(null);
    await chatActions.update.mutateAsync({
      chatId: activeChat.id,
      values: { provider: activeChat.provider, model },
    });
  };
  const changeProvider = async (event: ChangeEvent<HTMLSelectElement>) => {
    const provider = event.target.value;
    if (!activeChat) {
      const model = config.data?.providers[provider]?.[0];
      if (!model) return;
      setDraftSelection({ provider, model });
      return;
    }
    if (provider === activeChat.provider) return;
    const model = config.data?.providers[provider]?.[0];
    if (!model) return;
    setUiError(null);
    await chatActions.update.mutateAsync({
      chatId: activeChat.id,
      values: { provider, model },
    });
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
  const branchFromMessage = async (message: Message) => {
    if (!activeChat || !message.messageId) return;
    setUiError(null);
    try {
      const branch = await request<Chat>({
        url: `/chats/${activeChat.id}/branches`,
        method: 'POST',
        data: { assistantMessageId: message.messageId },
      });
      navigate(`/chat/${branch.id}`);
    } catch (reason) {
      setUiError(reason instanceof Error ? reason.message : 'Không thể mở nhánh chat.');
    }
  };
  const regenerateMessage = async (message: Message) => {
    if (!activeChat || !message.messageId || streamChat.isPending) return;
    setUiError(null);
    setStatus('Agent đang suy nghĩ...');
    try {
      const { content } = await request<{ content: string }>({
        url: `/chats/${activeChat.id}/regenerate`,
        method: 'POST',
        data: { assistantMessageId: message.messageId },
      });
      await streamChat.mutateAsync({
        chatId: activeChat.id,
        content,
        skipOptimisticUser: true,
        replaceAssistantMessageId: message.messageId,
        onEvent: (name, data) => {
          if (name === 'status') setStatus(String(data.message));
          if (name === 'tool_call') setStatus(`Đang dùng ${String(data.name)}...`);
          if (name === 'tool_result') setStatus(`Đã nhận kết quả từ ${String(data.name)}.`);
          if (name === 'message') setStatus(null);
          if (name === 'error') {
            setStatus(null);
            setUiError(String(data.message));
          }
        },
      });
    } catch (reason) {
      setStatus(null);
      setUiError(reason instanceof Error ? reason.message : 'Không thể tạo lại phản hồi.');
    }
  };
  const send = async (contentValue: string, files: File[]) => {
    if (
      (!contentValue.trim() && !files.length) ||
      sendLock.current ||
      createChat.isPending ||
      chatActions.update.isPending ||
      streamChat.isPending
    )
      return;
    sendLock.current = true;
    const content = contentValue.trim() || 'Hãy phân tích các tệp đính kèm này.';
    setPrompt('');
    // Show the thinking state immediately. Waiting for the first SSE event
    // leaves a noticeable blank period while uploads, retrieval, or the API
    // connection is still being established.
    setStatus('Agent đang suy nghĩ...');
    setUiError(null);
    try {
      const chat =
        activeChat ||
        (await createChat.mutateAsync({
          provider: draftProvider || undefined,
          model: draftModel || undefined,
        }));
      if (!activeChat) navigate(`/chat/${chat.id}`);
      const knowledgeFiles = files.filter((file) => /\.(pdf|docx|md)$/i.test(file.name));
      const images = files.filter((file) => file.type.startsWith('image/'));
      const [uploadedImages] = await Promise.all([
        images.length ? uploadMedia.mutateAsync(images) : Promise.resolve([]),
        knowledgeFiles.length
          ? uploadDocuments.mutateAsync({ files: knowledgeFiles, projectId: chat.projectId || undefined })
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
          if (name === 'error') {
            setStatus(null);
            setUiError(String(data.message));
          }
        },
        onUserMessageQueued: () => {
          setRunwayChatId(chat.id);
          setUserScrollRequest((request) => request + 1);
        },
      });
    } catch (reason) {
      setStatus(null);
      setUiError(reason instanceof Error ? reason.message : 'Gửi tin nhắn thất bại.');
    } finally {
      sendLock.current = false;
    }
  };

  return (
    <main className="min-h-dvh bg-background text-foreground">
      <div className="grid min-h-dvh w-full lg:grid-cols-[280px_minmax(0,1fr)]">
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
            onCreateChat={startNewChat}
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
            isSystemAdmin={isSystemAdmin}
            onOpenAdmin={() => {
              setSidebarOpen(false);
              navigate('/admin/overview');
            }}
            user={auth.session.user}
            onOpenApiKeys={() => navigate('/settings/api-keys')}
            onLogout={logoutToLogin}
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
                onCreateChat={startNewChat}
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
                isSystemAdmin={isSystemAdmin}
                onOpenAdmin={() => {
                  setSidebarOpen(false);
                  navigate('/admin/overview');
                }}
                user={auth.session.user}
                onOpenApiKeys={() => {
                  setSidebarOpen(false);
                  navigate('/settings/api-keys');
                }}
                onLogout={logoutToLogin}
              />
            </div>
          </div>
        ) : null}
        <section
          className={
            isChatView ? 'flex h-dvh min-w-0 min-h-0 flex-col overflow-hidden' : 'flex min-w-0 flex-col'
          }
        >
          {libraryPage ? null : workspaceView || adminPage || settingsPage ? (
            <div className="sticky top-0 z-20 flex h-15 items-center border-b bg-background/95 px-4 backdrop-blur sm:px-8">
              <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
                ← Chat
              </Button>
            </div>
          ) : (
            <ChatHeader
              chat={activeChat}
              config={config.data || null}
              provider={draftProvider}
              model={draftModel}
              busy={createChat.isPending || chatActions.update.isPending || streamChat.isPending}
              onOpenSidebar={() => setSidebarOpen(true)}
              onProviderChange={(event) => void changeProvider(event)}
              onModelChange={(event) => void changeModel(event)}
              collections={collections.data || []}
              onCollectionChange={(collectionId) =>
                activeChat && chatActions.update.mutate({ chatId: activeChat.id, values: { collectionId } })
              }
            />
          )}
          {libraryPage ? (
            <Suspense fallback={<WorkspacePanelFallback />}>
              <LibraryPage />
            </Suspense>
          ) : workspaceView ? (
            <Suspense fallback={<WorkspacePanelFallback />}>
              <WorkspacePanel view={workspaceView} />
            </Suspense>
          ) : adminPage ? (
            <Suspense fallback={<WorkspacePanelFallback />}>
              <AdminPage view={adminView || 'overview'} navigate={navigate} />
            </Suspense>
          ) : settingsPage ? (
            <SettingsApiKeysPage />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              <div ref={transcriptRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
                <div className="mx-auto min-h-full w-full max-w-5xl px-4 sm:px-8 lg:px-12">
                  {pins.data?.length ? (
                    <div className="sticky top-0 z-10 flex gap-2 overflow-x-auto border-b bg-background/95 py-3 backdrop-blur">
                      <span className="shrink-0 text-xs text-muted-foreground">Đã ghim:</span>
                      {pins.data.map((item) => (
                        <button
                          key={item.messageId}
                          className="shrink-0 rounded-full border px-2 py-1 text-xs hover:bg-muted"
                          onClick={() =>
                            document
                              .getElementById(`message-${item.messageId}`)
                              ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                          }
                        >
                          {item.content.slice(0, 48)}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <MessageList
                    key={activeChat?.id || 'new-chat'}
                    chatId={activeChat?.id}
                    messages={messages.data || []}
                    status={status}
                    error={error}
                    userScrollRequest={userScrollRequest}
                    isRunwayRequested={runwayChatId === activeChat?.id}
                    scrollContainerRef={transcriptRef}
                    onRunwayRelease={() => setRunwayChatId(null)}
                    onPin={(message) =>
                      message.messageId &&
                      pin.mutate({ messageId: message.messageId, pinned: !message.pinned })
                    }
                    onScheduleProposalAction={(proposalId, action) =>
                      scheduleProposal.mutate({ proposalId, action })
                    }
                    onBranch={branchFromMessage}
                    onRegenerate={regenerateMessage}
                  />
                </div>
              </div>
              <div className="mx-auto w-full max-w-5xl px-4 sm:px-8 lg:px-12">
                <ChatComposer
                  key={activeChat?.id || 'new-chat'}
                  prompt={prompt}
                  busy={
                    chatActions.update.isPending ||
                    streamChat.isPending ||
                    uploadDocuments.isPending ||
                    uploadMedia.isPending
                  }
                  onPromptChange={setPrompt}
                  onSubmit={(content, attachments) => void send(content, attachments)}
                  templates={templates.data || []}
                  onSelectTemplate={(content) => setPrompt(content)}
                  onSaveTemplate={(content) =>
                    openTemplateEditor({ name: '', content, projectId: activeChat?.projectId || null })
                  }
                  onEditTemplate={(template) => openTemplateEditor(template)}
                  onDeleteTemplate={(id) => deleteTemplate.mutate(id)}
                />
              </div>
            </div>
          )}
        </section>
      </div>
      {shareChat ? (
        <Suspense fallback={null}>
          <ChatShareDialog chat={shareChat} onClose={() => setShareChat(null)} />
        </Suspense>
      ) : null}
      {templateDraft ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <form
            className="w-full max-w-xl rounded-xl border bg-background p-5 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="template-editor-title"
            onSubmit={(event) => {
              event.preventDefault();
              void saveTemplateDraft();
            }}
          >
            <h2 id="template-editor-title" className="text-lg font-semibold">
              {templateDraft.id ? 'Sửa template' : 'Lưu prompt thành template'}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Lưu lại để dùng nhanh trong những cuộc trò chuyện sau.
            </p>
            <label className="mt-5 block text-sm font-medium" htmlFor="template-name">
              Tên template
            </label>
            <input
              id="template-name"
              autoFocus
              required
              value={templateDraft.name}
              onChange={(event) =>
                setTemplateDraft((draft) => (draft ? { ...draft, name: event.target.value } : draft))
              }
              className="mt-2 w-full rounded-md border bg-transparent px-3 py-2 outline-none ring-ring focus:ring-2"
              placeholder="Ví dụ: Tóm tắt tài liệu"
            />
            <label className="mt-4 block text-sm font-medium" htmlFor="template-content">
              Nội dung
            </label>
            <textarea
              id="template-content"
              required
              value={templateDraft.content}
              onChange={(event) =>
                setTemplateDraft((draft) => (draft ? { ...draft, content: event.target.value } : draft))
              }
              className="mt-2 min-h-40 w-full resize-y rounded-md border bg-transparent px-3 py-2 outline-none ring-ring focus:ring-2"
              placeholder="Nhập nội dung prompt..."
            />
            {saveTemplate.error?.message || updateTemplate.error?.message ? (
              <p className="mt-3 text-sm text-destructive">
                {saveTemplate.error?.message || updateTemplate.error?.message}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setTemplateDraft(null)}
                disabled={saveTemplate.isPending || updateTemplate.isPending}
              >
                Hủy
              </Button>
              <Button type="submit" disabled={saveTemplate.isPending || updateTemplate.isPending}>
                {saveTemplate.isPending || updateTemplate.isPending ? 'Đang lưu...' : 'Lưu template'}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
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
