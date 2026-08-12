import { useEffect, useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';

import { AppSidebar } from '@/src/components/app-sidebar';
import { ChatShareDialog } from '@/src/components/chat-share-dialog';
import { ChatComposer } from '@/src/components/chat-composer';
import { ChatHeader } from '@/src/components/chat-header';
import { MessageList } from '@/src/components/message-list';
import { MemoryLibraryDialog } from '@/src/components/memory-library-dialog';
import { PublicSharePage } from '@/src/components/public-share-page';
import { useChatActions } from '@/src/hooks/use-chat-actions';
import { useCreateChat } from '@/src/hooks/use-create-chat';
import { useGetChatMessages } from '@/src/hooks/use-get-chat-messages';
import { useGetChats } from '@/src/hooks/use-get-chats';
import { useGetConfig } from '@/src/hooks/use-get-config';
import { useGetDocuments } from '@/src/hooks/use-get-documents';
import { useStreamChat } from '@/src/hooks/use-stream-chat';
import { useUploadDocuments } from '@/src/hooks/use-upload-documents';
import { useUploadMedia } from '@/src/hooks/use-upload-media';
import type { Chat, Theme } from '@/src/types';

export default function App() {
  const token = /^\/share\/([^/]+)\/?$/.exec(window.location.pathname)?.[1];
  return token ? <PublicSharePage token={token} /> : <ChatWorkspace />;
}

function ChatWorkspace() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('agent-series.theme') as Theme) || 'system',
  );
  const [activeChatId, setActiveChatId] = useState<string>();
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [userScrollRequest, setUserScrollRequest] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [shareChat, setShareChat] = useState<Chat | null>(null);
  const [libraryOpen, setLibraryOpen] = useState(false);

  const config = useGetConfig();
  const chats = useGetChats();
  const documents = useGetDocuments();
  const activeChat = useMemo(
    () => (chats.data || []).find((chat) => chat.id === (activeChatId || chats.data?.[0]?.id)) || null,
    [activeChatId, chats.data],
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
    setActiveChatId(chat.id);
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
    if (values.archived && chat.id === activeChat?.id) setActiveChatId(undefined);
  };
  const renameChat = async (chat: Chat, title: string) => {
    setUiError(null);
    await chatActions.update.mutateAsync({ chatId: chat.id, values: { title } });
  };
  const deleteChat = async (chat: Chat) => {
    setUiError(null);
    await chatActions.remove.mutateAsync(chat.id);
    if (chat.id === activeChat?.id) setActiveChatId(undefined);
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
        <div className="hidden lg:block"><AppSidebar
          chats={chats.data || []}
          documents={documents.data || []}
          activeChatId={activeChat?.id}
          theme={theme}
          onCreateChat={() => void createAndSelect()}
          onSelectChat={(chat: Chat) => setActiveChatId(chat.id)}
          onThemeChange={setTheme}
          onRename={(chat, title) => void renameChat(chat, title)}
          onUpdate={(chat, values) => void updateChat(chat, values)}
          onDelete={(chat) => void deleteChat(chat)}
          onShare={setShareChat}
          onOpenLibrary={() => setLibraryOpen(true)}
        /></div>
        {sidebarOpen ? <div className="fixed inset-0 z-40 lg:hidden"><button type="button" className="absolute inset-0 bg-black/55" aria-label="Đóng lịch sử chat" onClick={() => setSidebarOpen(false)} /><div className="absolute inset-y-0 left-0 w-[min(86vw,340px)] shadow-2xl"><AppSidebar chats={chats.data || []} documents={documents.data || []} activeChatId={activeChat?.id} theme={theme} onCreateChat={() => { setSidebarOpen(false); void createAndSelect(); }} onSelectChat={(chat) => { setActiveChatId(chat.id); setSidebarOpen(false); }} onThemeChange={setTheme} onRename={(chat, title) => void renameChat(chat, title)} onUpdate={(chat, values) => void updateChat(chat, values)} onDelete={(chat) => void deleteChat(chat)} onShare={(chat) => { setShareChat(chat); setSidebarOpen(false); }} onOpenLibrary={() => { setSidebarOpen(false); setLibraryOpen(true); }} /></div></div> : null}
        <section className="flex min-w-0 flex-col">
          <ChatHeader
            chat={activeChat}
            config={config.data || null}
            busy={createChat.isPending || streamChat.isPending}
            onOpenSidebar={() => setSidebarOpen(true)}
            onProviderChange={(event) => void changeProvider(event)}
            onModelChange={(event) => void changeModel(event)}
          />
          <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-5 sm:px-8 lg:px-12">
            <MessageList messages={messages.data || []} status={status} error={error} userScrollRequest={userScrollRequest} />
            <ChatComposer
              prompt={prompt}
              busy={streamChat.isPending || uploadDocuments.isPending || uploadMedia.isPending}
              onPromptChange={setPrompt}
              onSubmit={(content, attachments) => void send(content, attachments)}
            />
          </div>
        </section>
      </div>
      {shareChat ? <ChatShareDialog chat={shareChat} onClose={() => setShareChat(null)} /> : null}
      {libraryOpen ? <MemoryLibraryDialog onClose={() => setLibraryOpen(false)} /> : null}
    </main>
  );
}
