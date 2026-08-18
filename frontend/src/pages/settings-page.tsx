import { ChatWorkspace } from '@/src/pages/chat-workspace-page';

type Props = { isSystemAdmin: boolean; navigate: (to: string) => void };

export function SettingsPage({ isSystemAdmin, navigate }: Props) {
  return <ChatWorkspace libraryPage={false} adminPage={false} settingsPage isSystemAdmin={isSystemAdmin} navigate={navigate} />;
}
