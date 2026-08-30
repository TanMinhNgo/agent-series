import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CirclePause,
  CirclePlay,
  CircleCheck,
  Check,
  ExternalLink,
  FolderKanban,
  Pencil,
  Plug,
  Plus,
  Search,
  Trash2,
  UserRound,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { PluginBrandIcon } from '@/src/components/plugin-brand-icon';
import { useGetConfig } from '@/src/hooks/use-get-config';
import { useInvitableWorkspaceUsers, useScheduleRuns, useWorkspace } from '@/src/hooks/use-workspace';
import { useProjectDeletePreview } from '@/src/hooks/use-project-delete-preview';
import type {
  ConnectorAuditLog,
  GitHubConnectorStatus,
  GoogleConnectorStatus,
  Plugin,
  PluginCatalogItem,
  Project,
  Schedule,
} from '@/src/types';

export type WorkspaceView = 'projects' | 'schedules' | 'plugins' | 'members';

const statusMeta = {
  active: { label: 'Đang hoạt động', Icon: CirclePlay, variant: 'default' as const },
  paused: { label: 'Tạm dừng', Icon: CirclePause, variant: 'secondary' as const },
  completed: { label: 'Hoàn thành', Icon: CircleCheck, variant: 'outline' as const },
};

const monthFormatter = new Intl.DateTimeFormat('vi-VN', {
  month: 'long',
  year: 'numeric',
  timeZone: 'Asia/Ho_Chi_Minh',
});

const toInputDateTime = (value: string) => {
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
};

const defaultDateTime = (day?: Date) => {
  const date = day ? new Date(day) : new Date();
  date.setHours(day ? 9 : date.getHours() + 1, 0, 0, 0);
  return toInputDateTime(date.toISOString());
};

function EmptyState({
  icon: Icon,
  title,
  detail,
  action,
}: {
  icon: typeof FolderKanban;
  title: string;
  detail: string;
  action: () => void;
}) {
  return (
    <div className="grid min-h-72 place-items-center rounded-xl border border-dashed bg-muted/20 p-8 text-center">
      <div>
        <span className="mx-auto grid size-11 place-items-center rounded-xl bg-muted text-muted-foreground">
          <Icon size={21} />
        </span>
        <h2 className="mt-4 text-base font-semibold">{title}</h2>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{detail}</p>
        <Button className="mt-5" onClick={action}>
          <Plus /> Tạo mới
        </Button>
      </div>
    </div>
  );
}

function FormDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="workspace-dialog-title"
    >
      <section className="max-h-[90dvh] w-full max-w-xl overflow-y-auto rounded-2xl border bg-card p-5 shadow-2xl sm:p-6">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 id="workspace-dialog-title" className="text-lg font-semibold">
            {title}
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
            ×
          </Button>
        </div>
        {children}
      </section>
    </div>
  );
}

function PageHeader({
  icon: Icon,
  title,
  detail,
  action,
}: {
  icon: typeof FolderKanban;
  title: string;
  detail: string;
  action: () => void;
}) {
  return (
    <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Icon size={16} /> Workspace
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
      </div>
      <Button onClick={action}>
        <Plus /> Tạo mới
      </Button>
    </header>
  );
}

function ProjectsView() {
  const { projects, projectActions, deleteProject } = useWorkspace();
  const [status, setStatus] = useState<'all' | keyof typeof statusMeta>('all');
  const [editing, setEditing] = useState<Project | null | undefined>();
  const [deleting, setDeleting] = useState<Project | null>(null);
  const deletionPreview = useProjectDeletePreview(deleting?.id);
  const [query, setQuery] = useState('');
  const items = useMemo(
    () =>
      (projects.data || []).filter(
        (item) =>
          (status === 'all' || item.status === status) &&
          item.name.toLowerCase().includes(query.toLowerCase()),
      ),
    [projects.data, query, status],
  );
  const save = async (
    data: Pick<Project, 'name' | 'description' | 'status' | 'instructions' | 'memoryMode'>,
  ) => {
    if (editing) await projectActions.update.mutateAsync({ id: editing.id, data });
    else await projectActions.create.mutateAsync(data);
    setEditing(undefined);
  };
  if (projects.isLoading) return <WorkspaceSkeleton />;
  if (projects.error) return <WorkspaceError message={projects.error.message} />;
  return (
    <>
      <PageHeader
        icon={FolderKanban}
        title="Dự án"
        detail="Tổ chức các mục tiêu và công việc cá nhân của bạn."
        action={() => setEditing(null)}
      />
      <div className="mb-5 flex flex-col gap-3 sm:flex-row">
        <input
          className="h-9 flex-1 rounded-lg border bg-background px-3 text-sm"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Tìm dự án..."
          aria-label="Tìm dự án"
        />
        <div className="flex gap-1 rounded-lg border bg-muted/40 p-1">
          {(['all', 'active', 'paused', 'completed'] as const).map((item) => (
            <Button
              key={item}
              size="sm"
              variant={status === item ? 'secondary' : 'ghost'}
              onClick={() => setStatus(item)}
            >
              {item === 'all' ? 'Tất cả' : statusMeta[item].label}
            </Button>
          ))}
        </div>
      </div>
      {!items.length ? (
        <EmptyState
          icon={FolderKanban}
          title={query || status !== 'all' ? 'Không có dự án phù hợp' : 'Chưa có dự án'}
          detail={
            query || status !== 'all'
              ? 'Thử đổi bộ lọc hoặc từ khóa tìm kiếm.'
              : 'Tạo dự án đầu tiên để bắt đầu tổ chức workspace.'
          }
          action={() => {
            setQuery('');
            setStatus('all');
            setEditing(null);
          }}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <ProjectCard
              key={item.id}
              item={item}
              onEdit={() => setEditing(item)}
              onDelete={() => setDeleting(item)}
            />
          ))}
        </div>
      )}
      {editing !== undefined ? (
        <ProjectForm
          project={editing}
          busy={projectActions.create.isPending || projectActions.update.isPending}
          error={projectActions.create.error?.message || projectActions.update.error?.message}
          onClose={() => setEditing(undefined)}
          onSave={save}
        />
      ) : null}
      {deleting ? (
        <DeleteProjectDialog
          project={deleting}
          busy={deleteProject.isPending}
          error={deleteProject.error?.message}
          counts={
            deletionPreview.data
              ? {
                  chats: deletionPreview.data.chats.length,
                  documents: deletionPreview.data.documents.length,
                  assets: deletionPreview.data.assets.length,
                  schedules: deletionPreview.data.schedules.length,
                }
              : undefined
          }
          onClose={() => setDeleting(null)}
          onConfirm={async (confirmName) => {
            await deleteProject.mutateAsync({ id: deleting.id, confirmName });
            setDeleting(null);
          }}
        />
      ) : null}
    </>
  );
}

function ProjectCard({
  item,
  onEdit,
  onDelete,
}: {
  item: Project;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const meta = statusMeta[item.status as keyof typeof statusMeta] || statusMeta.active;
  return (
    <Card className="min-h-44">
      <CardHeader>
        <CardTitle className="flex items-start justify-between gap-3">
          <span className="line-clamp-2">{item.name}</span>
          <Button variant="ghost" size="icon-sm" onClick={onEdit} aria-label={`Sửa ${item.name}`}>
            <Pencil />
          </Button>
        </CardTitle>
        <CardDescription className="line-clamp-3 min-h-10">
          {item.description || 'Chưa có mô tả cho dự án này.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="mt-auto flex items-center justify-between">
        <Badge variant={meta.variant}>
          <meta.Icon /> {meta.label}
        </Badge>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground hover:text-destructive"
          onClick={onDelete}
          aria-label={`Xóa ${item.name}`}
        >
          <Trash2 />
        </Button>
      </CardContent>
    </Card>
  );
}

function ProjectForm({
  project,
  busy,
  error,
  onClose,
  onSave,
}: {
  project: Project | null;
  busy: boolean;
  error?: string;
  counts?: { chats: number; documents: number; assets: number; schedules: number };
  onClose: () => void;
  onSave: (
    data: Pick<Project, 'name' | 'description' | 'status' | 'instructions' | 'memoryMode'>,
  ) => Promise<void>;
}) {
  const [name, setName] = useState(project?.name || '');
  const [description, setDescription] = useState(project?.description || '');
  const [status, setStatus] = useState(project?.status || 'active');
  const [memoryMode, setMemoryMode] = useState<Project['memoryMode']>(project?.memoryMode || 'default');
  const [instructions, setInstructions] = useState(project?.instructions || '');
  return (
    <FormDialog title={project ? 'Sửa dự án' : 'Tạo dự án'} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSave({
            name,
            description: description || null,
            status,
            instructions: instructions || null,
            memoryMode,
          });
        }}
      >
        <Field label="Tên dự án">
          <input
            required
            maxLength={160}
            className="workspace-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Mô tả">
          <textarea
            className="workspace-input min-h-24"
            maxLength={10_000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Trạng thái">
          <select
            className="workspace-input"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {Object.entries(statusMeta).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Bộ nhớ">
          <select
            className="workspace-input"
            value={memoryMode}
            onChange={(event) => setMemoryMode(event.target.value as Project['memoryMode'])}
          >
            <option value="default">Bộ nhớ mặc định</option>
            <option value="project_only">Chỉ bộ nhớ dự án</option>
          </select>
        </Field>
        <Field label="Hướng dẫn cho AI trong dự án">
          <textarea
            className="workspace-input min-h-24"
            maxLength={10_000}
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            placeholder="Ví dụ: Trả lời ngắn gọn, luôn nêu nguồn tài liệu."
          />
        </Field>
        {error ? <FormError message={error} /> : null}
        <FormActions busy={busy} onClose={onClose} submit={project ? 'Lưu thay đổi' : 'Tạo dự án'} />
      </form>
    </FormDialog>
  );
}

function DeleteProjectDialog({
  project,
  busy,
  error,
  counts,
  onClose,
  onConfirm,
}: {
  project: Project;
  busy: boolean;
  error?: string;
  counts?: { chats: number; documents: number; assets: number; schedules: number };
  onClose: () => void;
  onConfirm: (name: string) => Promise<void>;
}) {
  const [step, setStep] = useState(1);
  const [confirmation, setConfirmation] = useState('');
  return (
    <FormDialog
      title={step === 1 ? `Xóa dự án "${project.name}"?` : 'Xác nhận xóa vĩnh viễn'}
      onClose={onClose}
    >
      {step === 1 ? (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Toàn bộ chat, tài liệu RAG, file, lịch trình và memory thuộc dự án sẽ bị xóa vĩnh viễn.
          </p>
          <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
            {counts
              ? `${counts.chats} chat · ${counts.documents} tài liệu RAG · ${counts.assets} file · ${counts.schedules} lịch trình`
              : 'Đang kiểm tra dữ liệu sẽ bị xóa...'}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Hủy
            </Button>
            <Button variant="destructive" onClick={() => setStep(2)}>
              Tiếp tục
            </Button>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void onConfirm(confirmation);
          }}
        >
          <p className="text-sm text-muted-foreground">
            Nhập chính xác <strong>{project.name}</strong> để xác nhận.
          </p>
          <input
            className="workspace-input"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoFocus
          />
          {error ? <FormError message={error} /> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setStep(1)}>
              Quay lại
            </Button>
            <Button type="submit" variant="destructive" disabled={busy || confirmation !== project.name}>
              Xóa vĩnh viễn
            </Button>
          </div>
        </form>
      )}
    </FormDialog>
  );
}

type ScheduleFormData = Pick<
  Schedule,
  | 'title'
  | 'startsAt'
  | 'endsAt'
  | 'notes'
  | 'projectId'
  | 'provider'
  | 'model'
  | 'prompt'
  | 'recurrence'
  | 'requireWebSource'
  | 'notifyEmail'
>;

function SchedulesView() {
  const { schedules, projects, scheduleActions, runScheduleNow } = useWorkspace();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<'active' | 'paused' | 'all'>('active');
  const [editing, setEditing] = useState<Schedule | null | undefined>();
  const [deleting, setDeleting] = useState<Schedule | null>(null);
  const save = async (data: ScheduleFormData) => {
    if (editing) await scheduleActions.update.mutateAsync({ id: editing.id, data });
    else await scheduleActions.create.mutateAsync({ ...data, status: 'active', nextRunAt: data.startsAt });
    setEditing(undefined);
  };
  const startNow = async (scheduleId: string) => {
    const run = await runScheduleNow.mutateAsync(scheduleId);
    navigate(`/chat/${run.chatId}`);
  };
  if (schedules.isLoading || projects.isLoading) return <WorkspaceSkeleton />;
  if (schedules.error || projects.error)
    return (
      <WorkspaceError message={(schedules.error || projects.error)?.message || 'Không thể tải lịch trình.'} />
    );
  const events = (schedules.data || []).filter((item) => filter === 'all' || item.status === filter);
  return (
    <>
      <div className="mx-auto max-w-3xl py-8">
        <header className="flex items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Đã lên lịch</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Tạo và quản lý các tác vụ AI cần thực hiện định kỳ.
            </p>
          </div>
          <div className="flex rounded-xl border p-1">
            {(['active', 'paused', 'all'] as const).map((value) => (
              <Button
                key={value}
                size="sm"
                variant={filter === value ? 'secondary' : 'ghost'}
                onClick={() => setFilter(value)}
              >
                {value === 'active' ? 'Đang hoạt động' : value === 'paused' ? 'Tạm dừng' : 'Tất cả'}
              </Button>
            ))}
          </div>
        </header>
        <Button className="mt-7" onClick={() => setEditing(null)}>
          <Plus /> Tạo tác vụ AI
        </Button>
        <div className="mt-6 space-y-2">
          {events.map((item) => (
            <article
              key={item.id}
              className="flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-start"
            >
              <span className="mt-1.5 size-2 rounded-full bg-primary" />
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setEditing(item)}>
                <p className="font-medium">{item.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {item.recurrence === 'once'
                    ? 'Một lần'
                    : item.recurrence === 'daily'
                      ? 'Hằng ngày'
                      : 'Hằng tuần'}
                  {' · '}
                  {item.nextRunAt
                    ? `Lần tới: ${new Date(item.nextRunAt).toLocaleString('vi-VN')}`
                    : 'Không còn lần chạy'}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {item.provider && item.model ? `${item.provider} · ${item.model} · ` : ''}
                  Đã thiết lập: {new Date(item.startsAt).toLocaleString('vi-VN')}
                  {' · '}
                  {item.lastRunAt
                    ? `Đã chạy: ${new Date(item.lastRunAt).toLocaleString('vi-VN')}`
                    : 'Chưa chạy lần nào'}
                  {' · '}
                  {item.recurrence === 'once'
                    ? 'Một lần'
                    : item.status === 'paused'
                      ? 'Đang tạm dừng'
                      : item.status === 'completed'
                        ? 'Đã hoàn tất'
                        : 'Đang hoạt động'}
                </p>
              </button>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={runScheduleNow.isPending}
                  onClick={() => void startNow(item.id)}
                >
                  <CirclePlay /> Chạy ngay
                </Button>
                {item.status !== 'completed' ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      void scheduleActions.update.mutateAsync({
                        id: item.id,
                        data: { status: item.status === 'active' ? 'paused' : 'active' },
                      })
                    }
                  >
                    {item.status === 'active' ? 'Tạm dừng' : 'Bật lại'}
                  </Button>
                ) : null}
                {item.chatId ? (
                  <Button size="sm" variant="ghost" render={<a href={`/chat/${item.chatId}`} />}>
                    Mở chat
                  </Button>
                ) : null}
              </div>
            </article>
          ))}
          {!events.length ? (
            <EmptyState
              icon={CalendarDays}
              title="Chưa có tác vụ phù hợp"
              detail="Dùng ô phía trên để lên lịch cho một tác vụ."
              action={() => setEditing(null)}
            />
          ) : null}
        </div>
      </div>
      {editing !== undefined ? (
        <ScheduleForm
          schedule={editing}
          projects={projects.data || []}
          busy={scheduleActions.create.isPending || scheduleActions.update.isPending}
          error={scheduleActions.create.error?.message || scheduleActions.update.error?.message}
          onClose={() => {
            setEditing(undefined);
          }}
          onSave={save}
          onRunNow={editing ? () => startNow(editing.id) : undefined}
          runningNow={runScheduleNow.isPending}
          onDelete={editing ? async () => setDeleting(editing) : undefined}
        />
      ) : null}
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xóa lịch trình?"
        description={`Xóa lịch "${deleting?.title || ''}"? Thao tác này không thể hoàn tác.`}
        confirmLabel="Xóa lịch"
        destructive
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        onConfirm={async () => {
          if (!deleting) return;
          await scheduleActions.remove.mutateAsync(deleting.id);
          setEditing(undefined);
        }}
      />
    </>
  );
}

export function Calendar({
  month,
  events,
  onMonthChange,
  onAdd,
  onEdit,
}: {
  month: Date;
  events: Schedule[];
  onMonthChange: (date: Date) => void;
  onAdd: (date: Date) => void;
  onEdit: (item: Schedule) => void;
}) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay());
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
  const todayKey = new Date().toDateString();
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="flex items-center justify-between">
          <Button
            variant="outline"
            size="icon"
            onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
            aria-label="Tháng trước"
          >
            <ChevronLeft />
          </Button>
          <span className="capitalize">{monthFormatter.format(month)}</span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
            aria-label="Tháng sau"
          >
            <ChevronRight />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-7 border-b text-center text-xs font-medium text-muted-foreground">
          {['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'].map((name) => (
            <div className="py-3" key={name}>
              {name}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((day) => {
            const key = day.toDateString();
            const inMonth = day.getMonth() === month.getMonth();
            const dayEvents = events.filter((item) => new Date(item.startsAt).toDateString() === key);
            return (
              <div
                key={key}
                className={`min-h-28 border-r border-b p-1.5 last:border-r-0 sm:min-h-32 ${inMonth ? 'bg-card' : 'bg-muted/25 text-muted-foreground'}`}
              >
                <button
                  type="button"
                  className={`grid size-7 place-items-center rounded-full text-xs hover:bg-muted ${key === todayKey ? 'bg-primary text-primary-foreground hover:bg-primary' : ''}`}
                  onClick={() => onAdd(day)}
                  aria-label={`Tạo lịch ngày ${day.toLocaleDateString('vi-VN')}`}
                >
                  {day.getDate()}
                </button>
                <div className="mt-1 space-y-1">
                  {dayEvents.slice(0, 3).map((event) => (
                    <button
                      type="button"
                      key={event.id}
                      onClick={() => onEdit(event)}
                      className="block w-full truncate rounded-md bg-primary/10 px-1.5 py-1 text-left text-[11px] text-primary hover:bg-primary/15"
                    >
                      <span className="mr-1 font-medium">
                        {new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(
                          new Date(event.startsAt),
                        )}
                      </span>
                      {event.title}
                    </button>
                  ))}
                  {dayEvents.length > 3 ? (
                    <p className="px-1 text-[11px] text-muted-foreground">+{dayEvents.length - 3} lịch</p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function ScheduleForm({
  schedule,
  projects,
  busy,
  error,
  onClose,
  onSave,
  onRunNow,
  runningNow,
  onDelete,
}: {
  schedule: Schedule | null;
  projects: Project[];
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSave: (data: ScheduleFormData) => Promise<void>;
  onRunNow?: () => Promise<unknown>;
  runningNow?: boolean;
  onDelete?: () => Promise<void>;
}) {
  const [title, setTitle] = useState(schedule?.title || '');
  const [startsAt, setStartsAt] = useState(schedule ? toInputDateTime(schedule.startsAt) : defaultDateTime());
  const [endsAt, setEndsAt] = useState(schedule?.endsAt ? toInputDateTime(schedule.endsAt) : '');
  const [notes, setNotes] = useState(schedule?.notes || '');
  const [projectId, setProjectId] = useState(schedule?.projectId || '');
  const [prompt, setPrompt] = useState(schedule?.prompt || '');
  const [recurrence, setRecurrence] = useState<Schedule['recurrence']>(schedule?.recurrence || 'once');
  const [requireWebSource, setRequireWebSource] = useState(schedule?.requireWebSource || false);
  const [notifyEmail, setNotifyEmail] = useState(schedule?.notifyEmail || false);
  const config = useGetConfig();
  const [provider, setProvider] = useState(schedule?.provider || '');
  const [model, setModel] = useState(schedule?.model || '');
  const selectedProvider = provider || config.data?.defaultProvider || '';
  const models = config.data?.providers[selectedProvider] || [];
  const selectedModel = model && models.includes(model) ? model : models[0] || model;
  const runs = useScheduleRuns(schedule?.id);
  return (
    <FormDialog title={schedule ? 'Sửa lịch trình' : 'Tạo lịch trình'} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const start = new Date(startsAt);
          const end = endsAt ? new Date(endsAt) : null;
          if ((end && end < start) || !selectedProvider || !selectedModel) return;
          void onSave({
            title,
            startsAt: start.toISOString(),
            endsAt: end?.toISOString() || null,
            notes: notes || null,
            projectId: projectId || null,
            provider: selectedProvider,
            model: selectedModel,
            prompt,
            recurrence,
            requireWebSource,
            notifyEmail,
          });
        }}
      >
        <Field label="Tiêu đề">
          <input
            required
            maxLength={160}
            className="workspace-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
        <Field label="Yêu cầu AI">
          <textarea
            required
            className="workspace-input min-h-24"
            maxLength={10_000}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ví dụ: Tổng hợp thông tin quan trọng và nêu việc cần làm."
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Provider">
            <select
              required
              className="workspace-input"
              value={selectedProvider}
              disabled={config.isLoading || !Object.keys(config.data?.providers || {}).length}
              onChange={(event) => {
                const nextProvider = event.target.value;
                setProvider(nextProvider);
                setModel(config.data?.providers[nextProvider]?.[0] || '');
              }}
            >
              {!selectedProvider ? <option value="">Chưa có provider khả dụng</option> : null}
              {Object.keys(config.data?.providers || {}).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Model">
            <select
              required
              className="workspace-input"
              value={selectedModel}
              disabled={!selectedProvider || !models.length}
              onChange={(event) => setModel(event.target.value)}
            >
              {!selectedModel ? <option value="">Chưa có model khả dụng</option> : null}
              {models.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Bắt đầu">
            <input
              required
              type="datetime-local"
              className="workspace-input"
              value={startsAt}
              onChange={(event) => setStartsAt(event.target.value)}
            />
          </Field>
          <Field label="Kết thúc">
            <input
              type="datetime-local"
              min={startsAt}
              className="workspace-input"
              value={endsAt}
              onChange={(event) => setEndsAt(event.target.value)}
            />
          </Field>
        </div>
        <Field label="Lặp lại">
          <select
            className="workspace-input"
            value={recurrence}
            onChange={(event) => setRecurrence(event.target.value as Schedule['recurrence'])}
          >
            <option value="once">Một lần</option>
            <option value="daily">Hằng ngày</option>
            <option value="weekly">Hằng tuần</option>
          </select>
        </Field>
        <div className="space-y-2">
          <label className="flex items-center gap-3 rounded-lg border bg-muted/30 px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={requireWebSource}
              onChange={(event) => setRequireWebSource(event.target.checked)}
            />
            Bắt buộc lấy nguồn web mới trước khi trả lời
          </label>
          <label className="flex items-center gap-3 rounded-lg border bg-muted/30 px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={notifyEmail}
              onChange={(event) => setNotifyEmail(event.target.checked)}
            />
            Gửi email tới địa chỉ của tài khoản khi hoàn tất
          </label>
          {requireWebSource ? (
            <p className="text-xs text-muted-foreground">
              Nếu không tìm được nguồn web hợp lệ, lần chạy sẽ thất bại thay vì tạo nội dung thiếu nguồn.
            </p>
          ) : null}
        </div>
        <Field label="Dự án">
          <select
            className="workspace-input"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
          >
            <option value="">Không gắn dự án</option>
            {projects.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ghi chú">
          <textarea
            className="workspace-input min-h-20"
            maxLength={10_000}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        {endsAt && new Date(endsAt) < new Date(startsAt) ? (
          <FormError message="Thời điểm kết thúc phải sau thời điểm bắt đầu." />
        ) : null}
        {!config.isLoading && (!selectedProvider || !selectedModel) ? (
          <FormError message="Cần chọn provider và model khả dụng trước khi lưu lịch trình." />
        ) : null}
        {error ? <FormError message={error} /> : null}
        {schedule ? (
          <ScheduleRunHistory runs={runs.data || []} loading={runs.isLoading} scheduleId={schedule.id} />
        ) : null}
        <div className="flex flex-wrap justify-between gap-2">
          {onDelete ? (
            <Button type="button" variant="destructive" onClick={() => void onDelete()} disabled={busy}>
              <Trash2 /> Xóa
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            {onRunNow ? (
              <Button type="button" variant="secondary" disabled={runningNow} onClick={() => void onRunNow()}>
                <CirclePlay /> {runningNow ? 'Đang xếp hàng...' : 'Chạy ngay'}
              </Button>
            ) : null}
            <FormActions busy={busy} onClose={onClose} submit={schedule ? 'Lưu thay đổi' : 'Tạo lịch'} />
          </div>
        </div>
      </form>
    </FormDialog>
  );
}

function ScheduleRunHistory({
  runs,
  loading,
  scheduleId,
}: {
  runs: import('@/src/types').ScheduleRun[];
  loading: boolean;
  scheduleId?: string;
}) {
  const { resendScheduleRunEmail } = useWorkspace();
  return (
    <section className="rounded-xl border bg-muted/20 p-3">
      <h3 className="text-sm font-semibold">Lần chạy gần đây</h3>
      {loading ? (
        <p className="mt-2 text-xs text-muted-foreground">Đang tải nhật ký...</p>
      ) : !runs.length ? (
        <p className="mt-2 text-xs text-muted-foreground">Chưa có lần chạy nào.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {runs.slice(0, 5).map((run) => (
            <div key={run.id} className="rounded-lg bg-background p-2 text-xs">
              <p className="font-medium">
                {run.status === 'succeeded'
                  ? 'Hoàn tất'
                  : run.status === 'failed'
                    ? 'Thất bại'
                    : run.status === 'cancelled'
                      ? 'Đã thay thế'
                      : run.status === 'retrying'
                        ? `Sẽ tự thử lại (${run.retryCount}/3)`
                        : 'Đang chạy'}{' '}
                · Dự kiến {new Date(run.scheduledFor).toLocaleString('vi-VN')}
              </p>
              <p className="mt-1 text-muted-foreground">
                Bắt đầu {new Date(run.startedAt).toLocaleString('vi-VN')}
                {run.finishedAt ? ` · Kết thúc ${new Date(run.finishedAt).toLocaleString('vi-VN')}` : ''}
              </p>
              {run.status === 'retrying' && run.retryAt ? (
                <p className="mt-1 text-amber-700 dark:text-amber-400">
                  Provider đang tạm quá tải; sẽ thử lại lúc {new Date(run.retryAt).toLocaleString('vi-VN')}.
                </p>
              ) : null}
              <p className="mt-1 text-muted-foreground">
                {run.status === 'retrying'
                  ? 'Giữ nguyên chat và prompt, không tạo lượt trùng.'
                  : run.error || run.summary || 'Đang chờ kết quả...'}
              </p>
              {run.status === 'succeeded' && run.emailStatus === 'failed' ? (
                <div className="mt-1 flex flex-wrap items-center gap-2 text-amber-700 dark:text-amber-400">
                  <span>
                    Bản tin đã tạo, gửi email thất bại{run.emailError ? `: ${run.emailError}` : '.'}
                  </span>
                  {scheduleId ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={resendScheduleRunEmail.isPending}
                      onClick={() => void resendScheduleRunEmail.mutateAsync({ scheduleId, runId: run.id })}
                    >
                      Gửi lại email
                    </Button>
                  ) : null}
                </div>
              ) : run.emailStatus === 'sent' && run.emailSentAt ? (
                <p className="mt-1 text-muted-foreground">
                  Đã gửi email lúc {new Date(run.emailSentAt).toLocaleString('vi-VN')}.
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function PluginsView() {
  const {
    plugins,
    pluginCatalog,
    pluginActions,
    installCatalogPlugin,
    googleConnector,
    googleConnectorAudit,
    authorizeGoogle,
    disconnectGoogle,
    githubConnector,
    githubConnectorAudit,
    authorizeGitHub,
    disconnectGitHub,
  } = useWorkspace();
  const [editing, setEditing] = useState<Plugin | null | undefined>();
  const [disconnectingGoogle, setDisconnectingGoogle] = useState(false);
  const [disconnectingGitHub, setDisconnectingGitHub] = useState(false);
  const [deletingPlugin, setDeletingPlugin] = useState<Plugin | null>(null);
  const [query, setQuery] = useState('');
  const save = async (data: Pick<Plugin, 'slug' | 'name' | 'description' | 'enabled' | 'config'>) => {
    if (editing) await pluginActions.update.mutateAsync({ id: editing.id, data });
    else await pluginActions.create.mutateAsync(data);
    setEditing(undefined);
  };
  if (plugins.isLoading || pluginCatalog.isLoading) return <WorkspaceSkeleton />;
  if (plugins.error || pluginCatalog.error)
    return (
      <WorkspaceError message={(plugins.error || pluginCatalog.error)?.message || 'Không thể tải plugin.'} />
    );
  const allCatalog = pluginCatalog.data || [];
  const catalogBySlug = new Map(allCatalog.map((item) => [item.slug, item]));
  const normalizedQuery = query.trim().toLowerCase();
  const matched = allCatalog.filter((item) =>
    `${item.name} ${item.description} ${item.category}`.toLowerCase().includes(normalizedQuery),
  );
  const installed = plugins.data || [];
  const categories: Array<[string, string]> = [
    ['productivity', 'Năng suất'],
    ['creative', 'Sáng tạo'],
    ['developer', 'Công cụ dành cho nhà phát triển'],
    ['business', 'Doanh nghiệp & vận hành'],
    ['education', 'Giáo dục & nghiên cứu'],
    ['analytics', 'Dữ liệu & phân tích'],
    ['communication', 'Liên lạc'],
    ['security', 'Bảo mật'],
    ['finance', 'Tài chính'],
    ['health', 'Chăm sóc sức khỏe'],
    ['travel', 'Du lịch'],
    ['entertainment', 'Giải trí'],
    ['other', 'Khác'],
  ];
  const featured = allCatalog.filter((item) => item.featured);
  const renderRows = (items: PluginCatalogItem[]) => (
    <div className="grid divide-y divide-border/70 md:grid-cols-2 md:gap-x-10 md:divide-y-0">
      {items.map((item) => (
        <PluginDirectoryRow
          key={item.slug}
          item={item}
          busy={installCatalogPlugin.isPending}
          onInstall={() => void installCatalogPlugin.mutateAsync(item.slug)}
        />
      ))}
    </div>
  );
  return (
    <div className="mx-auto max-w-5xl py-2 sm:py-5">
      <header className="mb-8 flex flex-col gap-5 border-b border-border/60 pb-7 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <Plug size={15} /> Workspace
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Plugins</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Kết nối các công cụ bạn sử dụng để trợ lý có thêm ngữ cảnh cho công việc.
          </p>
        </div>
        <label className="flex h-10 w-full items-center gap-2 rounded-xl border border-border bg-background px-3 shadow-sm sm:w-72">
          <Search size={16} className="text-muted-foreground" />
          <input
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm plugin"
            aria-label="Tìm plugin"
          />
        </label>
      </header>

      <GoogleWorkspaceCard
        plugin={installed.find((item) => item.catalogSlug === 'google-workspace')}
        status={googleConnector.data}
        audit={googleConnectorAudit.data || []}
        busy={
          installCatalogPlugin.isPending ||
          authorizeGoogle.isPending ||
          disconnectGoogle.isPending ||
          pluginActions.update.isPending
        }
        error={
          authorizeGoogle.error?.message || disconnectGoogle.error?.message || googleConnector.error?.message
        }
        onInstall={() => void installCatalogPlugin.mutateAsync('google-workspace')}
        onConnect={async () => {
          const result = await authorizeGoogle.mutateAsync();
          window.location.assign(result.authorizationUrl);
        }}
        onDisconnect={() => setDisconnectingGoogle(true)}
        onToggle={async () => {
          const googlePlugin = installed.find((item) => item.catalogSlug === 'google-workspace');
          if (googlePlugin)
            await pluginActions.update.mutateAsync({
              id: googlePlugin.id,
              data: { enabled: !googlePlugin.enabled },
            });
        }}
      />
      <GitHubCard
        plugin={installed.find((item) => item.catalogSlug === 'github')}
        status={githubConnector.data}
        audit={githubConnectorAudit.data || []}
        busy={
          installCatalogPlugin.isPending ||
          authorizeGitHub.isPending ||
          disconnectGitHub.isPending ||
          pluginActions.update.isPending
        }
        error={
          authorizeGitHub.error?.message || disconnectGitHub.error?.message || githubConnector.error?.message
        }
        onInstall={() => void installCatalogPlugin.mutateAsync('github')}
        onConnect={async () => {
          const result = await authorizeGitHub.mutateAsync();
          window.location.assign(result.authorizationUrl);
        }}
        onDisconnect={() => setDisconnectingGitHub(true)}
        onToggle={async () => {
          const githubPlugin = installed.find((item) => item.catalogSlug === 'github');
          if (githubPlugin)
            await pluginActions.update.mutateAsync({
              id: githubPlugin.id,
              data: { enabled: !githubPlugin.enabled },
            });
        }}
      />

      {installed.length ? (
        <section className="mb-10">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold">Đã cài đặt</h2>
            <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
              <Plus /> Tùy chỉnh
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {installed.map((item) => {
              const catalogItem = item.catalogSlug ? catalogBySlug.get(item.catalogSlug) : undefined;
              return (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => setEditing(item)}
                  className="group rounded-xl border border-border bg-card p-1.5 transition-colors hover:border-foreground/25"
                  title={`Quản lý ${item.name}`}
                >
                  <PluginBrandIcon name={item.name} slug={catalogItem?.slug || item.slug} size="md" />
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      {normalizedQuery ? (
        <section>
          <h2 className="mb-3 text-base font-semibold">Kết quả tìm kiếm</h2>
          {matched.length ? (
            renderRows(matched)
          ) : (
            <p className="rounded-xl border border-dashed p-7 text-center text-sm text-muted-foreground">
              Không tìm thấy plugin phù hợp.
            </p>
          )}
        </section>
      ) : (
        <>
          <section className="mb-10">
            <h2 className="mb-3 text-base font-semibold">Nổi bật</h2>
            {renderRows(featured)}
          </section>
          {categories.map(([category, title]) => {
            const items = allCatalog.filter((item) => item.category === category);
            return items.length ? (
              <section className="mb-10" key={category}>
                <h2 className="mb-3 text-base font-semibold">{title}</h2>
                {renderRows(items)}
              </section>
            ) : null;
          })}
        </>
      )}

      <section className="border-t border-border/60 pt-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold">Plugin tùy chỉnh</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Tạo cấu hình local cho công cụ chưa có trong catalog.
            </p>
          </div>
          <Button variant="outline" onClick={() => setEditing(null)}>
            <Plus /> Thêm plugin
          </Button>
        </div>
        {installed.filter((item) => !item.catalogSlug).length ? (
          <div className="mt-4 grid divide-y divide-border/70 md:grid-cols-2 md:gap-x-10 md:divide-y-0">
            {installed
              .filter((item) => !item.catalogSlug)
              .map((item) => (
                <CustomPluginRow
                  key={item.id}
                  item={item}
                  onEdit={() => setEditing(item)}
                  onToggle={() =>
                    void pluginActions.update.mutateAsync({ id: item.id, data: { enabled: !item.enabled } })
                  }
                />
              ))}
          </div>
        ) : null}
      </section>
      {editing !== undefined ? (
        <PluginForm
          plugin={editing}
          busy={pluginActions.create.isPending || pluginActions.update.isPending}
          error={pluginActions.create.error?.message || pluginActions.update.error?.message}
          onClose={() => setEditing(undefined)}
          onSave={save}
          onDelete={editing ? async () => setDeletingPlugin(editing) : undefined}
        />
      ) : null}
      <ConfirmDialog
        open={disconnectingGoogle}
        title="Ngắt Google Workspace?"
        description="Token đã lưu cục bộ sẽ bị xóa và chat sẽ không còn đọc Drive, Gmail hoặc Calendar."
        confirmLabel="Ngắt kết nối"
        destructive
        onOpenChange={setDisconnectingGoogle}
        onConfirm={() => disconnectGoogle.mutateAsync()}
      />
      <ConfirmDialog
        open={disconnectingGitHub}
        title="Ngắt GitHub App?"
        description="Liên kết GitHub App cục bộ sẽ bị xóa và chat không còn đọc repository đã cấp quyền."
        confirmLabel="Ngắt kết nối"
        destructive
        onOpenChange={setDisconnectingGitHub}
        onConfirm={() => disconnectGitHub.mutateAsync()}
      />
      <ConfirmDialog
        open={Boolean(deletingPlugin)}
        title="Xóa plugin?"
        description={`Xóa plugin "${deletingPlugin?.name || ''}"? Thao tác này không thể hoàn tác.`}
        confirmLabel="Xóa plugin"
        destructive
        onOpenChange={(open) => {
          if (!open) setDeletingPlugin(null);
        }}
        onConfirm={async () => {
          if (!deletingPlugin) return;
          await pluginActions.remove.mutateAsync(deletingPlugin.id);
          setEditing(undefined);
        }}
      />
    </div>
  );
}

function GoogleWorkspaceCard({
  plugin,
  status,
  audit,
  busy,
  error,
  onInstall,
  onConnect,
  onDisconnect,
  onToggle,
}: {
  plugin?: Plugin;
  status?: GoogleConnectorStatus;
  audit: ConnectorAuditLog[];
  busy: boolean;
  error?: string;
  onInstall: () => void;
  onConnect: () => Promise<void>;
  onDisconnect: () => void;
  onToggle: () => Promise<void>;
}) {
  const connected = status?.status === 'connected';
  const configured = status?.configured ?? false;
  return (
    <section className="mb-10 rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <PluginBrandIcon name="Google Workspace" slug="google-workspace" size="md" />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">Google Workspace</h2>
              <Badge variant={connected ? 'default' : 'secondary'}>
                {connected ? 'Đã kết nối' : configured ? 'Chưa kết nối' : 'Chưa cấu hình'}
              </Badge>
              {connected && plugin?.enabled ? <Badge variant="outline">Đang bật cho chat</Badge> : null}
            </div>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Chỉ đọc nội dung Drive, Gmail và sự kiện Calendar. Không tạo, sửa, gửi hoặc import dữ liệu vào
              RAG.
            </p>
            {connected && status?.accountEmail ? (
              <p className="mt-2 text-xs text-muted-foreground">Tài khoản: {status.accountEmail}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!plugin ? (
            <Button size="sm" onClick={onInstall} disabled={busy}>
              Thêm Google Workspace
            </Button>
          ) : !configured ? (
            <Button size="sm" variant="outline" disabled>
              Thiếu cấu hình .env
            </Button>
          ) : !connected ? (
            <Button size="sm" onClick={() => void onConnect().catch(() => undefined)} disabled={busy}>
              Kết nối Google
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                variant={plugin.enabled ? 'secondary' : 'default'}
                onClick={() => void onToggle().catch(() => undefined)}
                disabled={busy}
              >
                {plugin.enabled ? 'Tắt trong chat' : 'Bật cho chat'}
              </Button>
              <Button size="sm" variant="outline" onClick={onDisconnect} disabled={busy}>
                Ngắt kết nối
              </Button>
            </>
          )}
        </div>
      </div>
      {!configured && plugin ? (
        <p className="mt-4 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
          Thêm GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET và CONNECTOR_ENCRYPTION_KEY vào `.env`, rồi
          restart backend.
        </p>
      ) : null}
      {error ? <FormError message={error} /> : null}
      {audit.length ? (
        <div className="mt-4 border-t border-border/60 pt-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Hoạt động gần đây
          </h3>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {audit.slice(0, 4).map((item) => (
              <li key={item.id} className="flex flex-wrap gap-x-2">
                <span>{new Date(item.createdAt).toLocaleString('vi-VN')}</span>
                <span>{item.toolName || item.eventType}</span>
                {item.summary ? <span>— {item.summary}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function GitHubCard({
  plugin,
  status,
  audit,
  busy,
  error,
  onInstall,
  onConnect,
  onDisconnect,
  onToggle,
}: {
  plugin?: Plugin;
  status?: GitHubConnectorStatus;
  audit: ConnectorAuditLog[];
  busy: boolean;
  error?: string;
  onInstall: () => void;
  onConnect: () => Promise<void>;
  onDisconnect: () => void;
  onToggle: () => Promise<void>;
}) {
  const connected = status?.status === 'connected';
  const configured = status?.configured ?? false;
  return (
    <section className="mb-10 rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <PluginBrandIcon name="GitHub" slug="github" size="md" />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">GitHub</h2>
              <Badge variant={connected ? 'default' : 'secondary'}>
                {connected ? 'Đã kết nối' : configured ? 'Chưa kết nối' : 'Chưa cấu hình'}
              </Badge>
              {connected && plugin?.enabled ? <Badge variant="outline">Đang bật cho chat</Badge> : null}
            </div>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              GitHub App chỉ đọc repository đã được cấp quyền, file, issue, pull request và workflow. Không
              tạo issue/PR hay thay đổi source code.
            </p>
            {connected && status?.accountEmail ? (
              <p className="mt-2 text-xs text-muted-foreground">Tài khoản/tổ chức: {status.accountEmail}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!plugin ? (
            <Button size="sm" onClick={onInstall} disabled={busy}>
              Thêm GitHub
            </Button>
          ) : !configured ? (
            <Button size="sm" variant="outline" disabled>
              Thiếu cấu hình .env
            </Button>
          ) : !connected ? (
            <Button size="sm" onClick={() => void onConnect().catch(() => undefined)} disabled={busy}>
              Kết nối GitHub
            </Button>
          ) : (
            <>
              <Button
                size="sm"
                variant={plugin.enabled ? 'secondary' : 'default'}
                onClick={() => void onToggle().catch(() => undefined)}
                disabled={busy}
              >
                {plugin.enabled ? 'Tắt trong chat' : 'Bật cho chat'}
              </Button>
              <Button size="sm" variant="outline" onClick={onDisconnect} disabled={busy}>
                Ngắt kết nối
              </Button>
            </>
          )}
        </div>
      </div>
      {!configured && plugin ? (
        <p className="mt-4 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
          Thêm GITHUB_APP_ID, GITHUB_APP_SLUG, GITHUB_APP_PRIVATE_KEY và CONNECTOR_ENCRYPTION_KEY vào `.env`,
          rồi restart backend.
        </p>
      ) : null}
      {error ? <FormError message={error} /> : null}
      {audit.length ? (
        <div className="mt-4 border-t border-border/60 pt-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Hoạt động gần đây
          </h3>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {audit.slice(0, 4).map((item) => (
              <li key={item.id} className="flex flex-wrap gap-x-2">
                <span>{new Date(item.createdAt).toLocaleString('vi-VN')}</span>
                <span>{item.toolName || item.eventType}</span>
                {item.summary ? <span>— {item.summary}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function PluginDirectoryRow({
  item,
  busy,
  onInstall,
}: {
  item: PluginCatalogItem;
  busy: boolean;
  onInstall: () => void;
}) {
  return (
    <div className="group flex min-h-20 items-center gap-3 border-border/70 py-3 md:border-b">
      <PluginBrandIcon name={item.name} slug={item.slug} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="truncate text-sm font-medium">{item.name}</h3>
          {item.connection_mode === 'planned' ? (
            <Badge variant="outline" className="shrink-0 text-[10px]">
              Sắp hỗ trợ kết nối
            </Badge>
          ) : null}
        </div>
        <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">{item.description}</p>
      </div>
      <div className="flex items-center">
        <a
          className="mr-1 inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100 focus:opacity-100"
          href={item.setup_url}
          target="_blank"
          rel="noreferrer"
          aria-label={`Xem hướng dẫn ${item.name}`}
        >
          <ExternalLink size={15} />
        </a>
        {item.installedPluginId ? (
          <span className="grid size-8 place-items-center text-muted-foreground" title="Đã thêm">
            <Check size={17} />
          </span>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            disabled={busy}
            onClick={onInstall}
            aria-label={`Thêm ${item.name}`}
          >
            <Plus size={18} />
          </Button>
        )}
      </div>
    </div>
  );
}

function CustomPluginRow({
  item,
  onEdit,
  onToggle,
}: {
  item: Plugin;
  onEdit: () => void;
  onToggle: () => void;
}) {
  return (
    <div className="flex min-h-20 items-center gap-3 border-border/70 py-3 md:border-b">
      <PluginBrandIcon name={item.name} />
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-medium">{item.name}</h3>
        <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">{item.description || item.slug}</p>
      </div>
      <Button size="sm" variant={item.enabled ? 'secondary' : 'ghost'} onClick={onToggle}>
        {item.enabled ? 'Đang bật' : 'Đang tắt'}
      </Button>
      <Button variant="ghost" size="icon" onClick={onEdit} aria-label={`Sửa ${item.name}`}>
        <Pencil size={16} />
      </Button>
    </div>
  );
}

function PluginForm({
  plugin,
  busy,
  error,
  onClose,
  onSave,
  onDelete,
}: {
  plugin: Plugin | null;
  busy: boolean;
  error?: string;
  onClose: () => void;
  onSave: (data: Pick<Plugin, 'slug' | 'name' | 'description' | 'enabled' | 'config'>) => Promise<void>;
  onDelete?: () => Promise<void>;
}) {
  const [slug, setSlug] = useState(plugin?.slug || '');
  const [name, setName] = useState(plugin?.name || '');
  const [description, setDescription] = useState(plugin?.description || '');
  const [enabled, setEnabled] = useState(plugin?.enabled || false);
  const [config, setConfig] = useState(plugin?.config ? JSON.stringify(plugin.config, null, 2) : '{}');
  const [jsonError, setJsonError] = useState('');
  return (
    <FormDialog title={plugin ? 'Sửa plugin' : 'Thêm plugin'} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          try {
            const parsed = config.trim() ? JSON.parse(config) : null;
            if (parsed !== null && (Array.isArray(parsed) || typeof parsed !== 'object')) throw new Error();
            setJsonError('');
            void onSave({ slug, name, description: description || null, enabled, config: parsed });
          } catch {
            setJsonError('Config phải là JSON object hợp lệ.');
          }
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tên">
            <input
              required
              maxLength={160}
              className="workspace-input"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label="Slug">
            <input
              required
              pattern="[a-z0-9-]+"
              maxLength={80}
              className="workspace-input font-mono"
              value={slug}
              onChange={(event) => setSlug(event.target.value.toLowerCase())}
            />
          </Field>
        </div>
        <Field label="Mô tả">
          <textarea
            className="workspace-input min-h-20"
            maxLength={10_000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Config JSON">
          <textarea
            className="workspace-input min-h-36 font-mono text-xs"
            value={config}
            onChange={(event) => setConfig(event.target.value)}
          />
        </Field>
        <label className="flex items-center gap-3 rounded-lg border bg-muted/30 px-3 py-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />{' '}
          Lưu plugin ở trạng thái bật
        </label>
        {jsonError ? <FormError message={jsonError} /> : null}
        {error ? <FormError message={error} /> : null}
        <div className="flex flex-wrap justify-between gap-2">
          {onDelete ? (
            <Button type="button" variant="destructive" onClick={() => void onDelete()} disabled={busy}>
              <Trash2 /> Xóa
            </Button>
          ) : (
            <span />
          )}
          <FormActions busy={busy} onClose={onClose} submit={plugin ? 'Lưu thay đổi' : 'Thêm plugin'} />
        </div>
      </form>
    </FormDialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      <span>{label}</span>
      {children}
    </label>
  );
}
function FormError({ message }: { message: string }) {
  return <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{message}</p>;
}
function FormActions({ busy, onClose, submit }: { busy: boolean; onClose: () => void; submit: string }) {
  return (
    <div className="flex justify-end gap-2">
      <Button type="button" variant="ghost" onClick={onClose}>
        Hủy
      </Button>
      <Button type="submit" disabled={busy}>
        {busy ? 'Đang lưu...' : submit}
      </Button>
    </div>
  );
}
function MembersView() {
  const { workspaceMembers, workspaceInvitations, inviteWorkspaceMember } = useWorkspace();
  const [email, setEmail] = useState('');
  const [search, setSearch] = useState('');
  const [role, setRole] = useState<'editor' | 'viewer'>('viewer');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const suggestions = useInvitableWorkspaceUsers(debouncedSearch);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  return (
    <section className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-8 lg:px-12">
      <div className="mb-6 flex items-center gap-2">
        <UserRound size={18} />
        <h1 className="text-2xl font-semibold">Thành viên workspace</h1>
      </div>
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Mời thành viên</CardTitle>
          <CardDescription>
            Người nhận đăng nhập Google bằng đúng email rồi mở link trong email để tham gia.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              if (email.trim())
                void inviteWorkspaceMember.mutateAsync({ email: email.trim(), role }).then(() => {
                  setEmail('');
                  setSearch('');
                });
            }}
          >
            <div className="relative flex-1">
              <input
                className="workspace-input w-full"
                type="email"
                required
                placeholder="name@example.com"
                value={email}
                onFocus={() => setShowSuggestions(true)}
                onChange={(event) => {
                  setEmail(event.target.value);
                  setSearch(event.target.value);
                  setShowSuggestions(true);
                }}
              />
              {showSuggestions && search.trim().length >= 2 && suggestions.data?.length ? (
                <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border bg-popover p-1 shadow-lg">
                  {suggestions.data.map((user) => (
                    <li key={user.id}>
                      <button
                        type="button"
                        className="w-full rounded px-3 py-2 text-left text-sm hover:bg-accent"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          setEmail(user.email);
                          setSearch(user.email);
                          setShowSuggestions(false);
                        }}
                      >
                        {user.displayName ? (
                          <span className="font-medium">
                            {user.displayName}{' '}
                            <span className="font-normal text-muted-foreground">{user.email}</span>
                          </span>
                        ) : (
                          user.email
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <select
              className="workspace-input"
              value={role}
              onChange={(event) => setRole(event.target.value as 'editor' | 'viewer')}
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </select>
            <Button type="submit" disabled={inviteWorkspaceMember.isPending}>
              Mời
            </Button>
          </form>
          {inviteWorkspaceMember.error ? <FormError message={inviteWorkspaceMember.error.message} /> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Thành viên</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {(workspaceMembers.data || []).map((member) => (
              <li key={member.userId} className="flex items-center justify-between border-b pb-3 text-sm">
                <span>
                  {member.displayName || member.email}
                  <span className="ml-2 text-muted-foreground">{member.email}</span>
                </span>
                <Badge variant="secondary">{member.role}</Badge>
              </li>
            ))}
          </ul>
          {workspaceInvitations.data?.length ? (
            <div className="mt-5 text-sm text-muted-foreground">
              Đang chờ: {workspaceInvitations.data.map((item) => item.email).join(', ')}
            </div>
          ) : null}
          {workspaceMembers.error ? (
            <WorkspaceError message="Bạn cần quyền owner để quản lý thành viên." />
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      <div className="h-8 w-48 rounded bg-muted" />
      <div className="h-10 w-full rounded bg-muted" />
      <div className="grid gap-3 md:grid-cols-3">
        {[1, 2, 3].map((item) => (
          <div key={item} className="h-44 rounded-xl bg-muted" />
        ))}
      </div>
    </div>
  );
}
function WorkspaceError({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive">
      Không thể tải workspace: {message}
    </div>
  );
}

export function WorkspacePanel({ view }: { view: WorkspaceView }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-8 lg:px-12">
      {view === 'projects' ? (
        <ProjectsView />
      ) : view === 'schedules' ? (
        <SchedulesView />
      ) : view === 'members' ? (
        <MembersView />
      ) : (
        <PluginsView />
      )}
    </div>
  );
}
