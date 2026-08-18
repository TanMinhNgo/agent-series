import { ChatWorkspace } from '@/src/pages/chat-workspace-page';

type Props = { isSystemAdmin: boolean; navigate: (to: string) => void };

export function AdminPage({ isSystemAdmin, navigate }: Props) {
  return <ChatWorkspace libraryPage={false} adminPage isSystemAdmin={isSystemAdmin} navigate={navigate} />;
}
