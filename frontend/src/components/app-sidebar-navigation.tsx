import {
  CalendarDays,
  ChevronRight,
  CircleHelp,
  FolderKanban,
  KeyRound,
  Library,
  LogOut,
  Monitor,
  Moon,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Plus,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  UserRound,
  type LucideIcon,
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
import type { AppWorkspace, Theme } from '@/src/types';
import type { AuthUser } from '@/src/hooks/use-auth';
import type { WorkspaceView } from '@/src/components/workspace-panel';

export type SidebarNavigation = 'chat' | 'library' | WorkspaceView | 'admin' | 'settings';

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

export function SidebarHeader({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed?: () => void;
}) {
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

export function SidebarNavigationMenu({
  activeNavigation,
  collapsed,
  isSystemAdmin,
  onCreateChat,
  onOpenLibrary,
  onOpenWorkspace,
  onOpenAdmin,
}: {
  activeNavigation?: SidebarNavigation;
  collapsed: boolean;
  isSystemAdmin: boolean;
  onCreateChat: () => void;
  onOpenLibrary: () => void;
  onOpenWorkspace: (view: WorkspaceView) => void;
  onOpenAdmin?: () => void;
}) {
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

export function AccountMenu({
  collapsed,
  user,
  theme,
  onThemeChange,
  onOpenApiKeys,
  onLogout,
  workspaces,
  activeWorkspaceId,
  onWorkspaceChange,
}: {
  collapsed: boolean;
  user?: AuthUser | null;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  onOpenApiKeys?: () => void;
  onLogout?: () => void;
  workspaces: AppWorkspace[];
  activeWorkspaceId?: string | null;
  onWorkspaceChange?: (workspaceId: string) => void;
}) {
  const accountName = user?.displayName || user?.email || 'Tài khoản';
  const accountInitials = (user?.displayName || user?.email || 'U').slice(0, 2).toUpperCase();
  const canSwitchWorkspace = workspaces.length > 1;
  const activeWorkspace = workspaces.find((workspace) => workspace.id === activeWorkspaceId) || workspaces[0];

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
          {canSwitchWorkspace ? (
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <UserRound />
                <span className="min-w-0 flex-1 truncate">
                  {activeWorkspace?.name || 'Không gian làm việc'}
                </span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="min-w-56">
                <DropdownMenuRadioGroup
                  value={activeWorkspaceId || workspaces[0]?.id}
                  onValueChange={(workspaceId) => onWorkspaceChange?.(workspaceId)}
                >
                  {workspaces.map((workspace) => (
                    <DropdownMenuRadioItem key={workspace.id} value={workspace.id}>
                      <span className="max-w-40 truncate">{workspace.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{workspace.role}</span>
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          ) : null}
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
