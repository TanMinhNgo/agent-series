import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { request, activeWorkspaceId } from '@/src/hooks/client';
import { useGetConfig } from '@/src/hooks/use-get-config';
import type { AppWorkspace, Config } from '@/src/types';

import {
  workflowStatus,
  previousWeek,
  reportPeriod,
  type Workflow,
  type WorkflowRun,
  type WorkflowRecipe,
} from './workflow-utils';
const inputClass = 'w-full rounded-md border bg-background px-3 py-2 text-sm';

function WorkflowForm({
  workflow,
  repositories,
  config,
  save,
  pending,
  recipes,
}: {
  workflow: Workflow | null;
  repositories: string[];
  config: Config;
  save: (values: Omit<Workflow, 'id' | 'revision'>) => void;
  pending: boolean;
  recipes: WorkflowRecipe[];
}) {
  const [name, setName] = useState(workflow?.name ?? 'Báo cáo GitHub tuần');
  const [repository, setRepository] = useState(workflow?.repository ?? repositories[0] ?? '');
  const [prompt, setPrompt] = useState(workflow?.prompt ?? 'Tổng hợp tiến độ và những vấn đề cần chú ý.');
  const [provider, setProvider] = useState(workflow?.provider ?? config.defaultProvider);
  const [model, setModel] = useState(workflow?.model ?? config.defaultModel);
  const [notifyEmail, setNotifyEmail] = useState(workflow?.notifyEmail ?? false);
  const [template, setTemplate] = useState<Workflow['template']>(
    workflow?.template ?? 'github-weekly-summary',
  );
  const recipe = recipes.find((item) => item.id === template);
  const requiresRepository = recipe?.requiresRepository ?? template === 'github-weekly-summary';
  return (
    <form
      className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        save({
          name,
          template,
          ...(requiresRepository ? { repository } : {}),
          prompt,
          provider,
          model,
          notifyEmail,
        });
      }}
    >
      <label className="grid gap-1 text-sm sm:col-span-2">
        Recipe
        <select
          className={inputClass}
          value={template}
          onChange={(e) => {
            const next = e.target.value as Workflow['template'];
            setTemplate(next);
            const selected = recipes.find((item) => item.id === next);
            if (selected) setPrompt(selected.prompt);
          }}
        >
          {recipes.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        Tên workflow
        <input
          required
          maxLength={160}
          className={inputClass}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="grid gap-1 text-sm">
        Repository {requiresRepository ? '' : '(không bắt buộc)'}
        <select
          required={requiresRepository}
          className={inputClass}
          value={repository}
          onChange={(e) => setRepository(e.target.value)}
        >
          <option value="">Chọn repository</option>
          {repositories.map((repo) => (
            <option key={repo}>{repo}</option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        Provider
        <select
          className={inputClass}
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value);
            setModel(config.providers[e.target.value]?.[0] ?? '');
          }}
        >
          {Object.keys(config.providers).map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        Model
        <select required className={inputClass} value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="">Chọn model</option>
          {(config.providers[provider] ?? []).map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm sm:col-span-2">
        Yêu cầu báo cáo
        <textarea
          required
          maxLength={10000}
          className={inputClass}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={notifyEmail} onChange={(e) => setNotifyEmail(e.target.checked)} />
        Gửi email cho người chạy
      </label>
      <Button type="submit" disabled={pending || (requiresRepository && !repository) || !model}>
        {pending ? 'Đang lưu...' : 'Lưu workflow'}
      </Button>
    </form>
  );
}

export function ProjectWorkflows({ projectId, repositories }: { projectId: string; repositories: string[] }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const config = useGetConfig();
  const workspaces = useQuery({
    queryKey: ['workflow-workspaces'],
    queryFn: () => request<AppWorkspace[]>({ url: '/workspaces' }),
  });
  const workspace = workspaces.data?.find((item) => item.id === activeWorkspaceId()) ?? workspaces.data?.[0];
  const canWrite = workspace?.role === 'owner' || workspace?.role === 'editor';
  const base = `/projects/${projectId}/workflows`;
  const workflows = useQuery({
    queryKey: ['workflows', projectId],
    queryFn: () => request<Workflow[]>({ url: base }),
  });
  const recipes = useQuery({
    queryKey: ['workflow-recipes'],
    queryFn: () => request<WorkflowRecipe[]>({ url: '/workflow-recipes' }),
  });
  const [editing, setEditing] = useState<Workflow | null | undefined>();
  const [historyId, setHistoryId] = useState('');
  const [historyStatus, setHistoryStatus] = useState('');
  const [period, setPeriod] = useState(previousWeek);
  const runs = useQuery({
    queryKey: ['workflow-runs', projectId, historyId, historyStatus],
    queryFn: () =>
      request<WorkflowRun[]>({
        url: `${base}/${historyId}/runs${historyStatus ? `?status=${historyStatus}` : ''}`,
      }),
    enabled: Boolean(historyId),
  });
  const save = useMutation({
    mutationFn: (data: Omit<Workflow, 'id' | 'revision'>) =>
      request({ url: editing ? `${base}/${editing.id}` : base, method: editing ? 'PATCH' : 'POST', data }),
    onSuccess: () => {
      setEditing(undefined);
      void client.invalidateQueries({ queryKey: ['workflows', projectId] });
    },
  });
  const pendingRequest = useRef<{ input: string; key: string } | null>(null);
  const run = useMutation({
    mutationFn: (id: string) => {
      const data = reportPeriod(period.start, period.end);
      const input = JSON.stringify([activeWorkspaceId(), projectId, id, data]);
      if (pendingRequest.current?.input !== input) {
        pendingRequest.current = { input, key: crypto.randomUUID() };
      }
      return request<WorkflowRun>({
        url: `${base}/${id}/runs`,
        method: 'POST',
        headers: { 'Idempotency-Key': pendingRequest.current.key },
        data,
      });
    },
    onSuccess: (result) => {
      pendingRequest.current = null;
      navigate(`/projects/${projectId}/workflow-runs/${result.id}`);
    },
  });
  const error =
    workflows.error ||
    recipes.error ||
    save.error ||
    run.error ||
    runs.error ||
    config.error ||
    workspaces.error;
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Workflows</CardTitle>
        <p className="text-sm text-muted-foreground">
          Issue/PR cập nhật trong kỳ, với trạng thái tại lúc lấy nguồn.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error.message}
          </p>
        )}
        {workflows.isLoading && <p role="status">Đang tải workflow...</p>}
        {canWrite && (
          <>
            <Button
              disabled={!repositories.length || !config.data}
              onClick={() => {
                save.reset();
                setEditing(null);
              }}
            >
              Tạo workflow
            </Button>
            {!repositories.length && (
              <p className="text-sm">Chọn repository trong nguồn GitHub của Project trước.</p>
            )}
          </>
        )}
        {canWrite && editing !== undefined && config.data && recipes.data && (
          <>
            <WorkflowForm
              key={editing?.id ?? 'new'}
              workflow={editing}
              repositories={repositories}
              config={config.data}
              recipes={recipes.data}
              save={(data) => save.mutate(data)}
              pending={save.isPending}
            />
            <Button variant="ghost" onClick={() => setEditing(undefined)}>
              Đóng cấu hình
            </Button>
          </>
        )}
        {canWrite && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm">
              Từ ngày (giờ Việt Nam)
              <input
                type="date"
                className={inputClass}
                value={period.start}
                onChange={(e) => setPeriod({ ...period, start: e.target.value })}
              />
            </label>
            <label className="grid gap-1 text-sm">
              Đến hết ngày (giờ Việt Nam)
              <input
                type="date"
                className={inputClass}
                value={period.end}
                onChange={(e) => setPeriod({ ...period, end: e.target.value })}
              />
            </label>
          </div>
        )}
        {workflows.data?.length === 0 && <p className="text-sm text-muted-foreground">Chưa có workflow.</p>}
        {workflows.data?.map((item) => (
          <div
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
          >
            <div>
              <p className="font-medium">{item.name}</p>
              <p className="text-sm text-muted-foreground">
                {item.repository} · {item.provider} / {item.model}
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setHistoryId(item.id)}>
                Lịch sử
              </Button>
              {canWrite && (
                <>
                  <Button
                    variant="outline"
                    onClick={() => {
                      save.reset();
                      setEditing(item);
                    }}
                  >
                    Sửa
                  </Button>
                  <Button
                    disabled={run.isPending || !period.start || !period.end || period.start > period.end}
                    onClick={() => run.mutate(item.id)}
                  >
                    {run.isPending ? 'Đang gửi...' : 'Chạy ngay'}
                  </Button>
                </>
              )}
            </div>
          </div>
        ))}
        {historyId && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium">Lịch sử lần chạy</p>
              <select
                aria-label="Lọc trạng thái"
                className="rounded-md border bg-background px-2 py-1 text-sm"
                value={historyStatus}
                onChange={(event) => setHistoryStatus(event.target.value)}
              >
                <option value="">Tất cả trạng thái</option>
                {['queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled'].map((status) => (
                  <option key={status} value={status}>
                    {workflowStatus[status]}
                  </option>
                ))}
              </select>
            </div>
            {runs.isLoading && <p>Đang tải...</p>}
            {runs.data?.length === 0 && <p>Chưa có lần chạy.</p>}
            {runs.data?.map((item) => (
              <Link
                className="block text-sm underline"
                key={item.id}
                to={`/projects/${projectId}/workflow-runs/${item.id}`}
              >
                {new Date(item.createdAt).toLocaleString('vi-VN')} · {workflowStatus[item.status]}
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
