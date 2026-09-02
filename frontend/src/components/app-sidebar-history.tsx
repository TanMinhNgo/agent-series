import { type UIEvent } from 'react';
import { Archive, FolderKanban, MoreHorizontal, Pencil, Pin, Share2, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import type { Chat, Project } from '@/src/types';

export type ChatUpdate = (
  chat: Chat,
  values: { pinned?: boolean; archived?: boolean; projectId?: string | null },
) => void;

type ChatRowProps = {
  chat: Chat;
  projects: Project[];
  active: boolean;
  onSelect: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: ChatUpdate;
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
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

type ChatListSectionProps = {
  title: string;
  chats: Chat[];
  projects: Project[];
  activeChatId?: string;
  onSelectChat: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: ChatUpdate;
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

export function SidebarHistory({
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
}: {
  pinned: Chat[];
  recent: Chat[];
  archived: Chat[];
  projects: Project[];
  activeChatId?: string;
  hasMoreChats: boolean;
  loadingMoreChats: boolean;
  onSelectChat: (chat: Chat) => void;
  onRename: (chat: Chat) => void;
  onUpdate: ChatUpdate;
  onDelete: (chat: Chat) => void;
  onShare: (chat: Chat) => void;
  onHistoryScroll: (event: UIEvent<HTMLDivElement>) => void;
}) {
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
