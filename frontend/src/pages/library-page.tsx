import { ChatWorkspace } from '@/src/pages/chat-workspace-page';

type Props = { isSystemAdmin: boolean; navigate: (to: string) => void };

export function LibraryPage({ isSystemAdmin, navigate }: Props) {
  return <ChatWorkspace libraryPage adminPage={false} isSystemAdmin={isSystemAdmin} navigate={navigate} />;
}
