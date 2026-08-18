import { ChatWorkspace } from '@/src/pages/chat-workspace-page';

type Props = { chatId?: string; isSystemAdmin: boolean; navigate: (to: string) => void };

export function ChatPage({ chatId, isSystemAdmin, navigate }: Props) {
  return (
    <ChatWorkspace
      chatId={chatId}
      libraryPage={false}
      adminPage={false}
      isSystemAdmin={isSystemAdmin}
      navigate={navigate}
    />
  );
}
