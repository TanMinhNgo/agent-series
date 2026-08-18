import type { WorkspaceView } from '@/src/components/workspace-panel';
import { ChatWorkspace } from '@/src/pages/chat-workspace-page';

type Props = { view: WorkspaceView; isSystemAdmin: boolean; navigate: (to: string) => void };

export function WorkspacePage({ view, isSystemAdmin, navigate }: Props) {
  return (
    <ChatWorkspace
      workspaceView={view}
      libraryPage={false}
      adminPage={false}
      isSystemAdmin={isSystemAdmin}
      navigate={navigate}
    />
  );
}
