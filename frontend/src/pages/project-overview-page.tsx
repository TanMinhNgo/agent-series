import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CalendarClock, FileText, FolderKanban, MessageSquare, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState, type ReactNode } from 'react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { request } from '@/src/hooks/client';
import type { Document, LibraryAsset, Project, Schedule } from '@/src/types';

type Activity = {
  id: string;
  eventType: string;
  subjectType: string;
  subjectId: string | null;
  summary: string;
  createdAt: string;
};
type Detail = {
  project: Project;
  chats: { id: string; title: string; updatedAt: string }[];
  documents: Document[];
  assets: LibraryAsset[];
  projectSources: LibraryAsset[];
  schedules: Schedule[];
  activity: Activity[];
  connectorScopes: { connectorSlug: 'google-workspace' | 'github'; config: Record<string, unknown> }[];
};

const time = (value: string) =>
  new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));

export function ProjectOverviewPage() {
  const projectId = location.pathname.split('/')[2];
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ['project-overview', projectId],
    queryFn: () => request<Detail>({ url: `/projects/${projectId}` }),
    enabled: Boolean(projectId),
  });
  const saveScope = useMutation({
    mutationFn: (data: { connectorSlug: 'google-workspace' | 'github'; config: Record<string, unknown> }) =>
      request({ url: `/projects/${projectId}/connector-scopes`, method: 'PUT', data }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-overview', projectId] }),
  });
  if (detail.isLoading)
    return (
      <main className="grid min-h-screen place-items-center text-sm text-muted-foreground">
        Đang tải Project...
      </main>
    );
  if (detail.error || !detail.data)
    return (
      <main className="grid min-h-screen place-items-center text-sm text-destructive">
        Không thể tải Project.
      </main>
    );
  const data = detail.data;
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-5 py-8 sm:px-8">
      <Link
        to="/projects"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={16} /> Dự án
      </Link>
      <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FolderKanban className="text-primary" />
            <h1 className="text-3xl font-semibold">{data.project.name}</h1>
          </div>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            {data.project.description || 'Chưa có mô tả cho Project này.'}
          </p>
        </div>
        <span className="rounded-full bg-muted px-3 py-1 text-sm capitalize">{data.project.status}</span>
      </header>
      <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={<MessageSquare size={18} />} label="Chat" value={data.chats.length} />
        <Metric icon={<FileText size={18} />} label="Artifact" value={data.assets.length} />
        <Metric icon={<Sparkles size={18} />} label="Project Sources" value={data.projectSources.length} />
        <Metric icon={<CalendarClock size={18} />} label="Lịch chạy" value={data.schedules.length} />
      </section>
      <section className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Nguồn Project</CardTitle>
            <CardDescription>File đã ghim để AI dùng làm ngữ cảnh.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.projectSources.length ? (
              data.projectSources.map((item) => (
                <a
                  key={item.id}
                  href={item.url}
                  className="flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2 text-sm hover:bg-muted"
                >
                  <span className="truncate">{item.name}</span>
                  <span>
                    v{item.version} · {item.indexStatus}
                  </span>
                </a>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Chưa có Project Source.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Chat gần đây</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.chats.length ? (
              data.chats.map((chat) => (
                <Link
                  key={chat.id}
                  to={`/chat/${chat.id}`}
                  className="block rounded-lg bg-muted/50 px-3 py-2 text-sm hover:bg-muted"
                >
                  <p className="truncate font-medium">{chat.title}</p>
                  <p className="text-xs text-muted-foreground">{time(chat.updatedAt)}</p>
                </Link>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Chưa có chat trong Project.</p>
            )}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Hoạt động gần đây</CardTitle>
            <CardDescription>Các thay đổi có thể xem lại trong Project.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.activity.length ? (
              data.activity.map((item) => (
                <div key={item.id} className="border-l-2 border-primary/40 pl-3">
                  <p className="text-sm">{item.summary}</p>
                  <time className="text-xs text-muted-foreground">{time(item.createdAt)}</time>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">Chưa có hoạt động nào.</p>
            )}
          </CardContent>
        </Card>
        <ConnectorScopes
          scopes={data.connectorScopes}
          isSaving={saveScope.isPending}
          error={saveScope.error ? 'Không thể lưu phạm vi nguồn.' : null}
          onSave={(connectorSlug, config) => saveScope.mutate({ connectorSlug, config })}
        />
      </section>
    </main>
  );
}

function ConnectorScopes({
  scopes,
  isSaving,
  error,
  onSave,
}: {
  scopes: Detail['connectorScopes'];
  isSaving: boolean;
  error: string | null;
  onSave: (slug: 'google-workspace' | 'github', config: Record<string, unknown>) => void;
}) {
  const github = scopes.find((item) => item.connectorSlug === 'github')?.config.repositories;
  const drive = scopes.find((item) => item.connectorSlug === 'google-workspace')?.config.fileIds;
  const [repositories, setRepositories] = useState(Array.isArray(github) ? github.join('\n') : '');
  const [fileIds, setFileIds] = useState(Array.isArray(drive) ? drive.join('\n') : '');
  const ids = (value: string) =>
    value
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Connector của Project</CardTitle>
        <CardDescription>
          AI chỉ được đọc đúng nguồn tại đây khi chat thuộc Project. Không tự gửi hoặc ghi dữ liệu ra ngoài.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5 md:grid-cols-2">
        <label className="grid gap-2 text-sm font-medium">
          GitHub repositories
          <textarea
            className="min-h-28 rounded-md border bg-background p-2 text-sm font-normal"
            value={repositories}
            onChange={(event) => setRepositories(event.target.value)}
            placeholder="owner/repository\nowner/another-repository"
          />
          <span className="text-xs font-normal text-muted-foreground">
            Mỗi dòng một repository được phép đọc.
          </span>
          <button
            className="w-fit rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
            disabled={isSaving}
            onClick={() => onSave('github', { repositories: ids(repositories) })}
          >
            Lưu GitHub scope
          </button>
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Google Drive file IDs
          <textarea
            className="min-h-28 rounded-md border bg-background p-2 text-sm font-normal"
            value={fileIds}
            onChange={(event) => setFileIds(event.target.value)}
            placeholder="1Abc...\n2Def..."
          />
          <span className="text-xs font-normal text-muted-foreground">
            Mỗi dòng một file Drive được phép đọc.
          </span>
          <button
            className="w-fit rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
            disabled={isSaving}
            onClick={() => onSave('google-workspace', { fileIds: ids(fileIds) })}
          >
            Lưu Drive scope
          </button>
        </label>
        {error ? <p className="text-sm text-destructive md:col-span-2">{error}</p> : null}
      </CardContent>
    </Card>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-4">
        <span className="text-primary">{icon}</span>
        <div>
          <p className="text-2xl font-semibold">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}
