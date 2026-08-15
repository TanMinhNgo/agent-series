import { useCallback, useState } from 'react';
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
  Pencil,
  Pin,
  Plug,
  Plus,
  Share2,
  Settings,
  Sparkles,
  Sun,
  Trash2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
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
import type { Chat, Theme } from '@/src/types';
import type { WorkspaceView } from '@/src/components/workspace-panel';

export type SidebarNavigation = 'chat' | 'library' | WorkspaceView;

type Props = {
  chats: Chat[];
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
  onUpdate: (chat: Chat, values: { pinned?: boolean; archived?: boolean }) => void;
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
  onOpenLibrary: () => void;
  onOpenWorkspace: (view: WorkspaceView) => void;
};

const themeOptions = [
  { value: 'system', label: 'System', Icon: Monitor },
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
] as const;

export function AppSidebar({
  chats,
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
}: Props) {
  const recent = chats.filter((chat) => !chat.archived);
  const archived = chats.filter((chat) => chat.archived);
  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [title, setTitle] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);
  const startRename = (chat: Chat) => {
    setRenameTarget(chat);
    setTitle(chat.title);
  };
  const handleHistoryScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    if (hasMoreChats && !loadingMoreChats && element.scrollHeight - element.scrollTop - element.clientHeight < 120) {
      onLoadMoreChats?.();
    }
  }, [hasMoreChats, loadingMoreChats, onLoadMoreChats]);
  return (
    <aside className="flex min-h-[100dvh] flex-col border-b border-border bg-sidebar p-4 lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0">
      <div className="mb-5 flex items-center">
        <div className="flex items-center gap-2 font-semibold">
          <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles size={16} />
          </span>
          Local Agent
        </div>
      </div>
      <nav className="mb-5 grid gap-1">
        <Button variant="ghost" data-active={activeNavigation === 'chat'} aria-current={activeNavigation === 'chat' ? 'page' : undefined} className="sidebar-nav-item justify-start" onClick={onCreateChat}>
          <Plus size={16} />
          Đoạn chat mới
        </Button>
        <Button variant="ghost" data-active={activeNavigation === 'library'} aria-current={activeNavigation === 'library' ? 'page' : undefined} className="sidebar-nav-item justify-start" onClick={onOpenLibrary}>
          <Library size={16} />
          Thư viện
        </Button>
        <Button variant="ghost" data-active={activeNavigation === 'projects'} aria-current={activeNavigation === 'projects' ? 'page' : undefined} className="sidebar-nav-item justify-start" onClick={() => onOpenWorkspace('projects')}>
          <FolderKanban size={16} />
          Dự án
        </Button>
        <Button variant="ghost" data-active={activeNavigation === 'schedules'} aria-current={activeNavigation === 'schedules' ? 'page' : undefined} className="sidebar-nav-item justify-start" onClick={() => onOpenWorkspace('schedules')}>
          <CalendarDays size={16} />
          Lịch trình
        </Button>
        <Button variant="ghost" data-active={activeNavigation === 'plugins'} aria-current={activeNavigation === 'plugins' ? 'page' : undefined} className="sidebar-nav-item justify-start" onClick={() => onOpenWorkspace('plugins')}>
          <Plug size={16} />
          Plugin
        </Button>
      </nav>
      <div className="min-h-0 flex-1 overflow-y-auto" onScroll={handleHistoryScroll}>
        <p className="section-label">Gần đây</p>
        <nav className="space-y-1">
          {recent.map((chat) => (
            <ChatRow
              key={chat.id}
              chat={chat}
              active={activeChatId === chat.id}
              onSelect={onSelectChat}
              onRename={startRename}
              onUpdate={onUpdate}
              onDelete={setDeleteTarget}
              onShare={onShare}
            />
          ))}
        </nav>
        {archived.length ? (
          <>
            <Separator className="my-5" />
            <p className="section-label">Lưu trữ</p>
            <nav className="space-y-1">
              {archived.map((chat) => (
                <ChatRow
                  key={chat.id}
                  chat={chat}
                  active={activeChatId === chat.id}
                  onSelect={onSelectChat}
                  onRename={startRename}
                  onUpdate={onUpdate}
                  onDelete={setDeleteTarget}
                  onShare={onShare}
                />
              ))}
            </nav>
          </>
        ) : null}
        {loadingMoreChats ? <p className="px-2 py-3 text-center text-xs text-muted-foreground">Đang tải thêm...</p> : null}
        {!loadingMoreChats && hasMoreChats ? <p className="px-2 py-3 text-center text-xs text-muted-foreground">Cuộn xuống để tải thêm lịch sử</p> : null}
      </div>
      <div className="mt-6 shrink-0 border-t pt-5">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" className="w-full justify-start" />}>
            <Settings size={16} />
            Settings
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side="top"
            sideOffset={12}
            align="start"
            className="w-56 rounded-xl p-1.5 shadow-xl"
          >
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Palette />
                Theme mode
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuRadioGroup
                  value={theme}
                  onValueChange={(value) => onThemeChange(value as Theme)}
                >
                  {themeOptions.map(({ value, label, Icon }) => (
                    <DropdownMenuRadioItem key={value} value={value}>
                      <Icon />
                      {label}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuItem>
              <Palette />
              Cá nhân hóa
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings />
              Cài đặt
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <CircleHelp />
              Trợ giúp
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {renameTarget ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <form
            className="w-full max-w-sm rounded-2xl border bg-card p-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (title.trim()) onRename(renameTarget, title.trim());
              setRenameTarget(null);
            }}
          >
            <h2 className="text-lg font-semibold">Đổi tên cuộc trò chuyện</h2>
            <input
              autoFocus
              maxLength={160}
              className="mt-4 w-full rounded-xl border bg-background px-3 py-2"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setRenameTarget(null)}>
                Hủy
              </Button>
              <Button type="submit">Lưu</Button>
            </div>
          </form>
        </div>
      ) : null}
      {deleteTarget ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <section className="w-full max-w-sm rounded-2xl border bg-card p-5">
            <h2 className="text-lg font-semibold">Xóa cuộc trò chuyện?</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Toàn bộ lịch sử và liên kết chia sẻ công khai sẽ bị thu hồi.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
                Hủy
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  onDelete(deleteTarget);
                  setDeleteTarget(null);
                }}
              >
                Xóa
              </Button>
            </div>
          </section>
        </div>
      ) : null}
    </aside>
  );
}

type ChatRowProps = {
  chat: Chat;
  active: boolean;
  onSelect: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: Props['onUpdate'];
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
};
function ChatRow({ chat, active, onSelect, onRename, onUpdate, onDelete, onShare }: ChatRowProps) {
  return (
    <div className="group flex items-center gap-1">
      <Button
        variant="ghost"
        data-active={active}
        aria-current={active ? 'page' : undefined}
        className="sidebar-chat-item min-w-0 flex-1 justify-start truncate"
        onClick={() => onSelect(chat)}
      >
        {chat.pinned ? <Pin className="mr-1.5 shrink-0" size={13} /> : null}
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
