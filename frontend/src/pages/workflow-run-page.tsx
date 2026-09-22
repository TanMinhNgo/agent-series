import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { request } from '@/src/hooks/client';
import { RichResponse } from '@/src/components/rich-response';
import { workflowStatus, runPollInterval, type WorkflowRun } from '@/src/components/workflow-utils';

type Source = { id: string; title: string; url: string; bodyTruncated: boolean };
type Detail = WorkflowRun & {
  canWrite: boolean;
  snapshot: { name: string; repository: string };
  steps: {
    id: string;
    status: string;
    error: string | null;
    attempt?: number;
    retryAt?: string | null;
    startedAt: string | null;
    finishedAt: string | null;
    output: { sources?: Source[]; reason?: string } | null;
  }[];
};
const labels: Record<string, string> = {
  source: 'Lấy nguồn GitHub',
  agent: 'AI tổng hợp',
  artifact: 'Lưu báo cáo',
  notification: 'Thông báo',
};
export function WorkflowRunPage() {
  const { projectId, runId } = useParams();
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const run = useQuery({
    queryKey: ['workflow-run', projectId, runId],
    queryFn: () => request<Detail>({ url: `/projects/${projectId}/workflow-runs/${runId}` }),
    refetchInterval: (query) => runPollInterval(query.state.data?.status),
  });
  const cancel = useMutation({
    mutationFn: () =>
      request({ url: `/projects/${projectId}/workflow-runs/${runId}/cancel`, method: 'POST' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['workflow-run', projectId, runId] }),
  });
  const retry = useMutation({
    mutationFn: (confirmResend: boolean) =>
      request({
        url: `/projects/${projectId}/workflow-runs/${runId}/retry`,
        method: 'POST',
        data: { confirmResend },
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['workflow-run', projectId, runId] }),
  });
  const preview = useQuery({
    queryKey: ['workflow-artifact', run.data?.artifactId],
    queryFn: () =>
      request<{ content: string; truncated: boolean }>({
        url: `/library/assets/${run.data?.artifactId}/preview`,
      }),
    enabled: open && Boolean(run.data?.artifactId),
  });
  const [confirmEmail, setConfirmEmail] = useState(false);
  const notification = run.data?.steps.find((step) => step.id === 'notification');
  const emailNeedsRetry = notification && ['failed', 'unknown'].includes(notification.status);
  const actionError = cancel.error || retry.error;
  return (
    <main className="mx-auto min-h-screen max-w-5xl space-y-6 px-5 py-8">
      <Link className="text-sm underline" to={`/projects/${projectId}`}>
        ← Project
      </Link>
      {run.isLoading && <p role="status">Đang tải lần chạy...</p>}
      {run.error && <p role="alert">{run.error.message}</p>}
      {actionError && <p role="alert">{actionError.message}</p>}
      {run.data && (
        <>
          <header>
            <h1 className="text-2xl font-semibold">{run.data.snapshot.name}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {run.data.snapshot.repository} · {workflowStatus[run.data.status]}
            </p>
            <p className="text-sm">
              {new Date(run.data.startsAt).toLocaleString('vi-VN')} →{' '}
              {new Date(run.data.endsAt).toLocaleString('vi-VN')} (không gồm mốc kết thúc)
            </p>
          </header>
          {run.data.error && (
            <p role="alert" className="text-destructive">
              {run.data.error}
            </p>
          )}
          {['queued', 'running', 'retrying'].includes(run.data.status) && (
            <p className="text-sm text-muted-foreground">
              Worker sẽ tiếp tục từ checkpoint sau khi khởi động lại.
            </p>
          )}
          {run.data.canWrite && ['queued', 'running', 'retrying'].includes(run.data.status) && (
            <Button
              variant="outline"
              onClick={() => cancel.mutate()}
              disabled={cancel.isPending || run.data.cancelRequested}
            >
              {run.data.cancelRequested ? 'Đã yêu cầu hủy' : 'Hủy lượt chạy'}
            </Button>
          )}
          {run.data.canWrite &&
            (['failed', 'cancelled'].includes(run.data.status) ||
              (run.data.status === 'succeeded' && emailNeedsRetry)) && (
              <Button
                variant="outline"
                onClick={() =>
                  notification?.status === 'unknown' ? setConfirmEmail(true) : retry.mutate(false)
                }
                disabled={retry.isPending}
              >
                {emailNeedsRetry ? 'Gửi lại email' : 'Tiếp tục từ bước chưa hoàn tất'}
              </Button>
            )}
          {confirmEmail && run.data.canWrite && (
            <div role="alert" className="space-y-2 rounded-lg border p-3">
              <p>Email trước có thể đã được gửi. Gửi lại có thể tạo email trùng.</p>
              <Button
                disabled={retry.isPending}
                onClick={() => {
                  retry.mutate(true);
                  setConfirmEmail(false);
                }}
              >
                Xác nhận gửi lại
              </Button>
              <Button variant="ghost" onClick={() => setConfirmEmail(false)}>
                Đóng
              </Button>
            </div>
          )}
          <ol className="grid gap-3">
            {run.data.steps.map((step) => (
              <li key={step.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>
                      {labels[step.id]} · {workflowStatus[step.status]}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {step.startedAt && (
                      <p>
                        Bắt đầu: {new Date(step.startedAt).toLocaleString('vi-VN')}
                        {step.finishedAt &&
                          ` · Kết thúc: ${new Date(step.finishedAt).toLocaleString('vi-VN')}`}
                      </p>
                    )}
                    {step.attempt && step.attempt > 1 && <p>Lần thử: {step.attempt}</p>}
                    {step.retryAt && <p>Retry lúc: {new Date(step.retryAt).toLocaleString('vi-VN')}</p>}
                    {step.error && (
                      <p role="alert" className="text-destructive">
                        {step.error}
                      </p>
                    )}
                    {step.output?.reason && <p>{step.output.reason}</p>}
                    {step.output?.sources?.map((source) => (
                      <p key={source.id}>
                        <a className="underline" href={source.url} target="_blank" rel="noreferrer">
                          [{source.id}] {source.title}
                        </a>
                        {source.bodyTruncated && ' · Mô tả được rút gọn'}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
          {run.data.artifactId && (
            <Button onClick={() => setOpen(!open)}>
              {open ? 'Đóng báo cáo' : 'Mở báo cáo trong Library'}
            </Button>
          )}
          {open && (
            <Card>
              <CardContent className="pt-5">
                {preview.isLoading && <p>Đang mở báo cáo...</p>}
                {preview.error && <p role="alert">{preview.error.message}</p>}
                {preview.data && (
                  <>
                    <RichResponse content={preview.data.content} />
                    {preview.data.truncated && (
                      <p className="mt-4 text-sm">
                        Bản xem trước được rút gọn. Xem file đầy đủ trong{' '}
                        <Link className="underline" to="/library">
                          Library
                        </Link>
                        .
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </main>
  );
}
