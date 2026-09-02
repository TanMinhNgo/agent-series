import { type UIEvent, useCallback, useState } from 'react';

import { DeleteChatDialog, RenameChatDialog } from './app-sidebar-dialogs';
import { SidebarHistory, type ChatUpdate } from './app-sidebar-history';
import {
  AccountMenu,
  SidebarHeader,
  SidebarNavigationMenu,
  WorkspaceSwitcher,
} from './app-sidebar-navigation';
import type { WorkspaceView } from '@/src/components/workspace-panel';
import type { AuthUser } from '@/src/hooks/use-auth';
import type { AppWorkspace, Chat, Project, Theme } from '@/src/types';
import type { SidebarNavigation } from './app-sidebar-navigation';

export type { SidebarNavigation } from './app-sidebar-navigation';

type Props = {
  chats: Chat[];
  projects: Project[];
  activeChatId?: string;
  activeNavigation?: SidebarNavigation;
  hasMoreChats?: boolean;
  loadingMoreChats?: boolean;
  onLoadMoreChats?: () => void;
  theme: Theme;
  onCreateChat: () => void;
  onSelectChat: (chat: Chat) => void;
  onThemeChange: (theme: Theme) => void;
  onRename: (chat: Chat, title: string) => void;
  onUpdate: ChatUpdate;
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
  onOpenLibrary: () => void;
  onOpenWorkspace: (view: WorkspaceView) => void;
  isSystemAdmin?: boolean;
  onOpenAdmin?: () => void;
  user?: AuthUser | null;
  onOpenApiKeys?: () => void;
  onLogout?: () => void;
  workspaces?: AppWorkspace[];
  activeWorkspaceId?: string | null;
  onWorkspaceChange?: (workspaceId: string) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
};

export function AppSidebar({
  chats,
  projects,
  activeChatId,
  activeNavigation,
  hasMoreChats = false,
  loadingMoreChats = false,
  onLoadMoreChats,
  theme,
  onCreateChat,
  onSelectChat,
  onThemeChange,
  onRename,
  onUpdate,
  onDelete,
  onShare,
  onOpenLibrary,
  onOpenWorkspace,
  isSystemAdmin = false,
  onOpenAdmin,
  user,
  onOpenApiKeys,
  onLogout,
  workspaces = [],
  activeWorkspaceId,
  onWorkspaceChange,
  collapsed = false,
  onToggleCollapsed,
}: Props) {
  // The backend already sorts pinned first, so every pinned chat is on the
  // first page and this split never hides one behind lazy-loaded history.
  const pinned = chats.filter((chat) => chat.pinned && !chat.archived);
  const recent = chats.filter((chat) => !chat.pinned && !chat.archived);
  const archived = chats.filter((chat) => chat.archived);
  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [title, setTitle] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);

  const startRename = (chat: Chat) => {
    setRenameTarget(chat);
    setTitle(chat.title);
  };
  const handleHistoryScroll = useCallback(
    (event: UIEvent<HTMLDivElement>) => {
      const element = event.currentTarget;
      if (
        hasMoreChats &&
        !loadingMoreChats &&
        element.scrollHeight - element.scrollTop - element.clientHeight < 120
      ) {
        onLoadMoreChats?.();
      }
    },
    [hasMoreChats, loadingMoreChats, onLoadMoreChats],
  );

  return (
    <aside
      className={`flex min-h-dvh flex-col border-b border-border bg-sidebar/85 p-3 transition-[width,padding] duration-200 lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0 ${
        collapsed ? 'lg:px-2' : 'lg:p-4'
      }`}
    >
      <SidebarHeader collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
      {!collapsed ? (
        <WorkspaceSwitcher
          workspaces={workspaces}
          activeWorkspaceId={activeWorkspaceId}
          onWorkspaceChange={onWorkspaceChange}
        />
      ) : null}
      <SidebarNavigationMenu
        activeNavigation={activeNavigation}
        collapsed={collapsed}
        isSystemAdmin={isSystemAdmin}
        onCreateChat={onCreateChat}
        onOpenLibrary={onOpenLibrary}
        onOpenWorkspace={onOpenWorkspace}
        onOpenAdmin={onOpenAdmin}
      />
      {!collapsed ? (
        <SidebarHistory
          pinned={pinned}
          recent={recent}
          archived={archived}
          projects={projects}
          activeChatId={activeChatId}
          hasMoreChats={hasMoreChats}
          loadingMoreChats={loadingMoreChats}
          onSelectChat={onSelectChat}
          onRename={startRename}
          onUpdate={onUpdate}
          onDelete={setDeleteTarget}
          onShare={onShare}
          onHistoryScroll={handleHistoryScroll}
        />
      ) : (
        <div className="flex-1" />
      )}
      <AccountMenu
        collapsed={collapsed}
        user={user}
        theme={theme}
        onThemeChange={onThemeChange}
        onOpenApiKeys={onOpenApiKeys}
        onLogout={onLogout}
      />
      <RenameChatDialog
        chat={renameTarget}
        title={title}
        onTitleChange={setTitle}
        onClose={() => setRenameTarget(null)}
        onRename={onRename}
      />
      <DeleteChatDialog chat={deleteTarget} onClose={() => setDeleteTarget(null)} onDelete={onDelete} />
    </aside>
  );
}
