import { ChatWorkspace } from '@/src/pages/chat-workspace-page';
import type { AdminTab } from '@/src/features/admin/types/admin';

type Props = { isSystemAdmin: boolean; navigate: (to: string) => void; view: AdminTab };

export function AdminPage({ isSystemAdmin, navigate, view }: Props) {
  return (
    <ChatWorkspace
      libraryPage={false}
      adminPage
      adminView={view}
      isSystemAdmin={isSystemAdmin}
      navigate={navigate}
    />
  );
}
