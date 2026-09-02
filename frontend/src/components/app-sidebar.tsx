import { type UIEvent, useCallback, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  CalendarDays,
  CircleHelp,
  FolderKanban,
  Library,
  Monitor,
  Moon,
  MoreHorizontal,
  Palette,
  Archive,
  KeyRound,
  LogOut,
  Pencil,
  Pin,
  Plug,
  Plus,
  Share2,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  UserRound,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  type LucideIcon,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import type { AppWorkspace, Chat, Project, Theme } from '@/src/types';
import type { WorkspaceView } from '@/src/components/workspace-panel';
import type { AuthUser } from '@/src/hooks/use-auth';

export type SidebarNavigation = 'chat' | 'library' | WorkspaceView | 'admin' | 'settings';

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
  onUpdate: (chat: Chat, values: { pinned?: boolean; archived?: boolean; projectId?: string | null }) => void;
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

type SidebarNavButtonProps = {
  label: string;
  Icon: LucideIcon;
  active: boolean;
  collapsed: boolean;
  onClick?: () => void;
  primary?: boolean;
};

const themeOptions = [
  { value: 'system', label: 'System', Icon: Monitor },
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
] as const;

function SidebarNavButton({
  label,
  Icon,
  active,
  collapsed,
  onClick,
  primary = false,
}: SidebarNavButtonProps) {
  return (
    <Button
      variant={primary ? 'default' : 'ghost'}
      data-active={active}
      aria-current={active ? 'page' : undefined}
      className={`${primary ? '' : 'sidebar-nav-item'} justify-start ${
        collapsed ? 'size-9 px-0 lg:mx-auto' : 'w-full'
      } ${primary ? 'shadow-sm shadow-primary/15' : ''}`}
      onClick={onClick}
      title={label}
    >
      <Icon size={16} />
      <span className={collapsed ? 'sr-only' : undefined}>{label}</span>
    </Button>
  );
}

function SidebarHeader({ collapsed, onToggleCollapsed }: Pick<Props, 'collapsed' | 'onToggleCollapsed'>) {
  return (
    <div className={`mb-4 flex items-center ${collapsed ? 'flex-col gap-2' : 'justify-between'}`}>
      <div className="flex min-w-0 items-center gap-2 font-semibold tracking-tight">
        <span className="grid size-8 shrink-0 place-items-center rounded-[0.7rem] bg-primary text-primary-foreground shadow-sm shadow-primary/20">
          <Sparkles size={16} />
        </span>
        <span className={collapsed ? 'sr-only' : undefined}>Local Agent</span>
      </div>
      {onToggleCollapsed ? (
        <Button
          variant="ghost"
          size="icon-sm"
          className="hidden text-muted-foreground lg:inline-flex"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? 'Mở rộng sidebar' : 'Thu gọn sidebar'}
          title={collapsed ? 'Mở rộng sidebar' : 'Thu gọn sidebar'}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </Button>
      ) : null}
    </div>
  );
}

function WorkspaceSwitcher({
  workspaces,
  activeWorkspaceId,
  onWorkspaceChange,
}: Pick<Props, 'workspaces' | 'activeWorkspaceId' | 'onWorkspaceChange'>) {
  if (!workspaces?.length) return null;

  return (
    <label className="mb-4 block text-xs text-muted-foreground">
      <span className="section-label mb-1 block">Workspace</span>
      <Select
        value={activeWorkspaceId || workspaces[0]?.id}
        onValueChange={(workspaceId) => {
          if (workspaceId) onWorkspaceChange?.(workspaceId);
        }}
      >
        <SelectTrigger className="h-10 w-full rounded-xl border-border/80 bg-background/70 pr-2 text-left shadow-none hover:bg-background">
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="start" className="max-w-[min(20rem,var(--anchor-width))]">
          {workspaces.map((workspace) => (
            <SelectItem key={workspace.id} value={workspace.id} className="py-2">
              {workspace.name} · {workspace.role}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

function SidebarNavigation({
  activeNavigation,
  collapsed = false,
  isSystemAdmin = false,
  onCreateChat,
  onOpenLibrary,
  onOpenWorkspace,
  onOpenAdmin,
}: Pick<
  Props,
  | 'activeNavigation'
  | 'collapsed'
  | 'isSystemAdmin'
  | 'onCreateChat'
  | 'onOpenLibrary'
  | 'onOpenWorkspace'
  | 'onOpenAdmin'
>) {
  return (
    <nav className="mb-5 grid gap-1">
      <SidebarNavButton
        label="Đoạn chat mới"
        Icon={Plus}
        active={activeNavigation === 'chat'}
        collapsed={collapsed}
        onClick={onCreateChat}
        primary
      />
      <SidebarNavButton
        label="Thư viện"
        Icon={Library}
        active={activeNavigation === 'library'}
        collapsed={collapsed}
        onClick={onOpenLibrary}
      />
      <SidebarNavButton
        label="Dự án"
        Icon={FolderKanban}
        active={activeNavigation === 'projects'}
        collapsed={collapsed}
        onClick={() => onOpenWorkspace('projects')}
      />
      <SidebarNavButton
        label="Lịch trình"
        Icon={CalendarDays}
        active={activeNavigation === 'schedules'}
        collapsed={collapsed}
        onClick={() => onOpenWorkspace('schedules')}
      />
      <SidebarNavButton
        label="Plugin"
        Icon={Plug}
        active={activeNavigation === 'plugins'}
        collapsed={collapsed}
        onClick={() => onOpenWorkspace('plugins')}
      />
      <SidebarNavButton
        label="Thành viên"
        Icon={UserRound}
        active={activeNavigation === 'members'}
        collapsed={collapsed}
        onClick={() => onOpenWorkspace('members')}
      />
      {isSystemAdmin ? (
        <SidebarNavButton
          label="Quản trị hệ thống"
          Icon={ShieldCheck}
          active={activeNavigation === 'admin'}
          collapsed={collapsed}
          onClick={onOpenAdmin}
        />
      ) : null}
    </nav>
  );
}

type ChatListSectionProps = {
  title: string;
  chats: Chat[];
  projects: Project[];
  activeChatId?: string;
  onSelectChat: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: Props['onUpdate'];
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
  showPinIcon?: boolean;
  className?: string;
};

function ChatListSection({
  title,
  chats,
  projects,
  activeChatId,
  onSelectChat,
  onRename,
  onUpdate,
  onDelete,
  onShare,
  showPinIcon,
  className,
}: ChatListSectionProps) {
  if (!chats.length) return null;

  return (
    <section className={className}>
      <p className="section-label">{title}</p>
      <nav className="space-y-1">
        {chats.map((chat) => (
          <ChatRow
            key={chat.id}
            chat={chat}
            active={activeChatId === chat.id}
            onSelect={onSelectChat}
            onRename={onRename}
            onUpdate={onUpdate}
            projects={projects}
            onDelete={onDelete}
            onShare={onShare}
            showPinIcon={showPinIcon}
          />
        ))}
      </nav>
    </section>
  );
}

type SidebarHistoryProps = Pick<
  Props,
  | 'projects'
  | 'activeChatId'
  | 'hasMoreChats'
  | 'loadingMoreChats'
  | 'onSelectChat'
  | 'onUpdate'
  | 'onDelete'
  | 'onShare'
> & {
  pinned: Chat[];
  recent: Chat[];
  archived: Chat[];
  onRename: (chat: Chat) => void;
  onHistoryScroll: (event: UIEvent<HTMLDivElement>) => void;
};

function SidebarHistory({
  pinned,
  recent,
  archived,
  projects,
  activeChatId,
  hasMoreChats,
  loadingMoreChats,
  onSelectChat,
  onRename,
  onUpdate,
  onDelete,
  onShare,
  onHistoryScroll,
}: SidebarHistoryProps) {
  const sectionProps = { projects, activeChatId, onSelectChat, onRename, onUpdate, onDelete, onShare };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto" onScroll={onHistoryScroll}>
      <ChatListSection title="Đã ghim" chats={pinned} {...sectionProps} showPinIcon={false} />
      <ChatListSection
        title="Gần đây"
        chats={recent}
        {...sectionProps}
        className={pinned.length ? 'mt-5' : undefined}
      />
      {archived.length ? <Separator className="my-5" /> : null}
      <ChatListSection title="Lưu trữ" chats={archived} {...sectionProps} />
      {loadingMoreChats ? (
        <p className="px-2 py-3 text-center text-xs text-muted-foreground">Đang tải thêm...</p>
      ) : null}
      {hasMoreChats && !loadingMoreChats ? (
        <p className="px-2 py-3 text-center text-xs text-muted-foreground">Cuộn xuống để tải thêm lịch sử</p>
      ) : null}
    </div>
  );
}

function AccountMenu({
  collapsed = false,
  user,
  theme,
  onThemeChange,
  onOpenApiKeys,
  onLogout,
}: Pick<Props, 'collapsed' | 'user' | 'theme' | 'onThemeChange' | 'onOpenApiKeys' | 'onLogout'>) {
  const accountName = user?.displayName || user?.email || 'Tài khoản';
  const accountInitials = (user?.displayName || user?.email || 'U').slice(0, 2).toUpperCase();

  return (
    <div className={`mt-5 shrink-0 border-t pt-4 ${collapsed ? 'lg:border-t-0 lg:pt-0' : ''}`}>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              className={`h-auto w-full justify-start px-2 py-2 ${collapsed ? 'lg:size-9 lg:px-0 lg:justify-center' : ''}`}
            />
          }
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-pink-400 text-xs font-semibold text-white">
            {accountInitials}
          </span>
          <span className={`min-w-0 flex-1 text-left ${collapsed ? 'lg:hidden' : ''}`}>
            <span className="block truncate text-sm font-medium">{accountName}</span>
            <span className="block text-xs text-muted-foreground">Tài khoản Google</span>
          </span>
          <Settings size={17} className={`text-muted-foreground ${collapsed ? 'lg:hidden' : ''}`} />
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side="top"
          sideOffset={12}
          align="start"
          className="w-64 rounded-2xl p-2 shadow-xl"
        >
          <div className="flex items-center gap-3 px-2 py-2.5">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-pink-400 text-xs font-semibold text-white">
              {accountInitials}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{accountName}</span>
              <span className="block truncate text-xs text-muted-foreground">Tài khoản Google</span>
            </span>
            <ChevronRight size={16} className="text-muted-foreground" />
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onOpenApiKeys}>
            <KeyRound /> Thêm API key của bạn
          </DropdownMenuItem>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <Palette />
              Cá nhân hóa
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuRadioGroup value={theme} onValueChange={(value) => onThemeChange(value as Theme)}>
                {themeOptions.map(({ value, label, Icon }) => (
                  <DropdownMenuRadioItem key={value} value={value}>
                    <Icon />
                    {label}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuItem disabled>
            <UserRound /> Hỗ trợ <span className="ml-auto text-xs">Sắp có</span>
          </DropdownMenuItem>
          <DropdownMenuItem disabled>
            <Settings /> Cài đặt <span className="ml-auto text-xs">Sắp có</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled>
            <CircleHelp /> Trợ giúp <ChevronRight className="ml-auto" />
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onLogout} className="text-destructive focus:text-destructive">
            <LogOut /> Đăng xuất
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

type RenameChatDialogProps = {
  chat: Chat | null;
  title: string;
  onTitleChange: (title: string) => void;
  onClose: () => void;
  onRename: (chat: Chat, title: string) => void;
};

function RenameChatDialog({ chat, title, onTitleChange, onClose, onRename }: RenameChatDialogProps) {
  if (!chat) return null;

  return createPortal(
    <dialog
      open
      className="fixed inset-0 z-100 grid place-items-center bg-black/60 p-4"
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <form
        className="w-full max-w-sm rounded-2xl border bg-card p-5"
        onSubmit={(event) => {
          event.preventDefault();
          const nextTitle = title.trim();
          if (nextTitle) onRename(chat, nextTitle);
          onClose();
        }}
      >
        <h2 className="text-lg font-semibold">Đổi tên cuộc trò chuyện</h2>
        <input
          autoFocus
          maxLength={160}
          className="mt-4 w-full rounded-xl border bg-background px-3 py-2"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
        />
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit">Lưu</Button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
}

type DeleteChatDialogProps = {
  chat: Chat | null;
  onClose: () => void;
  onDelete: (chat: Chat) => void;
};

function DeleteChatDialog({ chat, onClose, onDelete }: DeleteChatDialogProps) {
  if (!chat) return null;

  return createPortal(
    <dialog
      open
      className="fixed inset-0 z-100 grid place-items-center bg-black/60 p-4"
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <section className="w-full max-w-sm rounded-2xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Xóa cuộc trò chuyện?</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Toàn bộ lịch sử và liên kết chia sẻ công khai sẽ bị thu hồi.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              onDelete(chat);
              onClose();
            }}
          >
            Xóa
          </Button>
        </div>
      </section>
    </dialog>,
    document.body,
  );
}

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
      <SidebarNavigation
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

type ChatRowProps = {
  chat: Chat;
  projects: Project[];
  active: boolean;
  onSelect: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: Props['onUpdate'];
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
  /** Redundant inside the "Đã ghim" section, where the heading already says so. */
  showPinIcon?: boolean;
};
function ChatRow({
  chat,
  projects,
  active,
  onSelect,
  onRename,
  onUpdate,
  onDelete,
  onShare,
  showPinIcon = true,
}: ChatRowProps) {
  return (
    <div className="group flex items-center gap-1">
      <Button
        variant="ghost"
        data-active={active}
        aria-current={active ? 'page' : undefined}
        className="sidebar-chat-item min-w-0 flex-1 justify-start truncate"
        onClick={() => onSelect(chat)}
      >
        {chat.isUnread ? (
          <span
            className="mr-2 size-2 shrink-0 rounded-full bg-primary shadow-[0_0_10px_hsl(var(--primary))]"
            aria-label="Chat AI mới, chưa đọc"
          />
        ) : null}
        {chat.pinned && showPinIcon ? <Pin className="mr-1.5 shrink-0" size={13} /> : null}
        {chat.title || 'Cuộc trò chuyện mới'}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0 opacity-70 sm:opacity-0 sm:group-hover:opacity-100"
              aria-label={`Thao tác với ${chat.title}`}
            />
          }
        >
          <MoreHorizontal size={17} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuItem onClick={() => onShare(chat)}>
            <Share2 /> Chia sẻ
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onRename(chat)}>
            <Pencil /> Đổi tên
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onUpdate(chat, { pinned: !chat.pinned })}>
            <Pin /> {chat.pinned ? 'Bỏ ghim' : 'Ghim đoạn chat'}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onUpdate(chat, { archived: !chat.archived })}>
            <Archive /> {chat.archived ? 'Khôi phục' : 'Lưu trữ'}
          </DropdownMenuItem>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <FolderKanban /> {chat.projectId ? 'Chuyển dự án' : 'Thêm vào dự án'}
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem onClick={() => onUpdate(chat, { projectId: null })}>
                Không thuộc dự án
              </DropdownMenuItem>
              {projects.map((project) => (
                <DropdownMenuItem key={project.id} onClick={() => onUpdate(chat, { projectId: project.id })}>
                  {project.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            onClick={() => onDelete(chat)}
          >
            <Trash2 /> Xóa
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
