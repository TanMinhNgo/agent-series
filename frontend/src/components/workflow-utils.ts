export type Workflow = {
  id: string;
  name: string;
  repository?: string;
  prompt: string;
  provider: string;
  model: string;
  notifyEmail: boolean;
  revision: number;
  template?: 'github-weekly-summary' | 'daily-ai-digest' | 'project-report';
};
export type WorkflowRecipe = {
  id: Workflow['template'];
  title: string;
  description: string;
  prompt: string;
  sourceType: string;
  requiresRepository: boolean;
};
export type WorkflowRun = {
  id: string;
  projectId: string;
  status: string;
  artifactId: string | null;
  error: string | null;
  createdAt: string;
  startsAt: string;
  endsAt: string;
  cancelRequested?: boolean;
};
export const workflowStatus: Record<string, string> = {
  queued: 'Đang chờ worker',
  pending: 'Chưa chạy',
  running: 'Đang chạy',
  succeeded: 'Hoàn tất',
  failed: 'Thất bại',
  retrying: 'Đang chờ retry',
  cancelled: 'Đã hủy',
  sending: 'Đang gửi email',
  unknown: 'Chưa xác định đã gửi',
  skipped: 'Bỏ qua',
};

export function previousWeek(now = new Date()) {
  const local = new Date(now.getTime() + 7 * 3600000);
  local.setUTCHours(0, 0, 0, 0);
  local.setUTCDate(local.getUTCDate() - ((local.getUTCDay() + 6) % 7));
  return {
    start: new Date(local.getTime() - 7 * 86400000).toISOString().slice(0, 10),
    end: new Date(local.getTime() - 86400000).toISOString().slice(0, 10),
  };
}
export function reportPeriod(start: string, end: string) {
  return {
    startsAt: new Date(`${start}T00:00:00+07:00`).toISOString(),
    endsAt: new Date(new Date(`${end}T00:00:00+07:00`).getTime() + 86400000).toISOString(),
  };
}

export const runPollInterval = (status?: string) =>
  status === 'queued' || status === 'running' || status === 'retrying' ? 2000 : false;
