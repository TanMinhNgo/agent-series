import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { request } from '@/src/hooks/client';
import { ProjectWorkflows } from './project-workflows';
import { previousWeek, reportPeriod, runPollInterval } from './workflow-utils';
import { WorkflowRunPage } from '@/src/pages/workflow-run-page';

const navigate = vi.hoisted(() => vi.fn());
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
  useParams: () => ({ projectId: 'p', runId: 'r' }),
}));
vi.mock('@/src/hooks/client', () => ({ request: vi.fn(), activeWorkspaceId: () => 'w' }));
vi.mock('@/src/hooks/use-get-config', () => ({
  useGetConfig: () => ({
    data: { providers: { openai: ['model'] }, defaultProvider: 'openai', defaultModel: 'model' },
  }),
}));
vi.mock('@/src/components/rich-response', () => ({
  RichResponse: ({ content }: { content: string }) => <p>{content}</p>,
}));
const workflow = {
  id: 'flow',
  name: 'Weekly',
  repository: 'org/repo',
  prompt: 'Report',
  provider: 'openai',
  model: 'model',
  notifyEmail: false,
  revision: 1,
};
function mount(element = <ProjectWorkflows projectId="p" repositories={['org/repo']} />) {
  return render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
        }
      >
        {element}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
function respond(role = 'editor') {
  vi.mocked(request).mockImplementation(async (config) => {
    if (config.url === '/workspaces') return [{ id: 'w', role }];
    if (config.method === 'POST' && config.url?.endsWith('/runs')) return { id: 'r' };
    if (config.method) return workflow;
    return [workflow];
  });
}
beforeEach(() => {
  vi.mocked(request).mockReset();
  navigate.mockReset();
});

describe('Project workflows', () => {
  it('uses Vietnam calendar boundaries and stops polling completed runs', () => {
    expect(previousWeek(new Date('2026-09-19T09:00:00Z'))).toEqual({
      start: '2026-09-07',
      end: '2026-09-13',
    });
    expect(reportPeriod('2026-09-07', '2026-09-13')).toEqual({
      startsAt: '2026-09-06T17:00:00.000Z',
      endsAt: '2026-09-13T17:00:00.000Z',
    });
    expect(runPollInterval('running')).toBe(2000);
    expect(runPollInterval('succeeded')).toBe(false);
    expect(runPollInterval('failed')).toBe(false);
  });
  it('creates and edits a configuration', async () => {
    respond();
    mount();
    fireEvent.click(await screen.findByText('Tạo workflow'));
    fireEvent.change(screen.getByLabelText('Tên workflow'), { target: { value: 'New report' } });
    fireEvent.click(screen.getByText('Lưu workflow'));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        expect.objectContaining({
          method: 'POST',
          data: expect.objectContaining({ name: 'New report', notifyEmail: false }),
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByText('Lưu workflow')).not.toBeInTheDocument());
    fireEvent.click(screen.getByText('Sửa'));
    fireEvent.change(screen.getByLabelText('Tên workflow'), { target: { value: 'Edited' } });
    fireEvent.click(screen.getByText('Lưu workflow'));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        expect.objectContaining({
          url: '/projects/p/workflows/flow',
          method: 'PATCH',
          data: expect.objectContaining({ name: 'Edited' }),
        }),
      ),
    );
  });
  it('starts a run and navigates to its detail', async () => {
    respond();
    mount();
    fireEvent.click(await screen.findByText('Chạy ngay'));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/projects/p/workflow-runs/r'));
  });
  it('hides write actions for viewers', async () => {
    respond('viewer');
    mount();
    await screen.findByText('Weekly');
    expect(screen.queryByText('Tạo workflow')).not.toBeInTheDocument();
    expect(screen.queryByText('Chạy ngay')).not.toBeInTheDocument();
    expect(screen.queryByText('Sửa')).not.toBeInTheDocument();
  });
  it('shows a source error and opens the artifact via the Library API', async () => {
    vi.mocked(request).mockImplementation(async (config) =>
      config.url?.endsWith('/preview')
        ? { content: 'Saved report', truncated: false }
        : {
            id: 'r',
            status: 'succeeded',
            artifactId: 'asset',
            snapshot: { name: 'Weekly', repository: 'org/repo' },
            startsAt: '2026-09-01T00:00:00Z',
            endsAt: '2026-09-08T00:00:00Z',
            steps: [{ id: 'notification', status: 'failed', error: 'Email failed' }],
          },
    );
    mount(<WorkflowRunPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Email failed');
    fireEvent.click(screen.getByText('Mở báo cáo trong Library'));
    expect(await screen.findByText('Saved report')).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith({ url: '/library/assets/asset/preview' });
  });
  it('shows API errors', async () => {
    vi.mocked(request).mockRejectedValue(new Error('No access'));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('No access');
  });
  it('reuses the request key when retrying a lost run response', async () => {
    const keys: string[] = [];
    vi.mocked(request).mockImplementation(async (config) => {
      if (config.url === '/workspaces') return [{ id: 'w', role: 'editor' }];
      if (config.method === 'POST') {
        keys.push(String(config.headers?.['Idempotency-Key']));
        if (keys.length === 1) throw new Error('Lost response');
        return { id: 'r' };
      }
      return [workflow];
    });
    mount();
    fireEvent.click(await screen.findByText('Chạy ngay'));
    await screen.findByText('Lost response');
    fireEvent.click(screen.getByText('Chạy ngay'));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });
  it('hides run mutations for viewers', async () => {
    vi.mocked(request).mockResolvedValue({
      id: 'r',
      status: 'running',
      canWrite: false,
      snapshot: { name: 'Weekly' },
      startsAt: '2026-09-01',
      endsAt: '2026-09-08',
      steps: [],
    });
    mount(<WorkflowRunPage />);
    await screen.findByText('Weekly');
    expect(screen.queryByText('Hủy lượt chạy')).not.toBeInTheDocument();
  });
  it('confirms unknown email resend and displays mutation failures', async () => {
    vi.mocked(request).mockImplementation(async (config) => {
      if (config.method) throw new Error('Retry denied');
      return {
        id: 'r',
        status: 'succeeded',
        canWrite: true,
        snapshot: { name: 'Weekly' },
        startsAt: '2026-09-01',
        endsAt: '2026-09-08',
        steps: [{ id: 'notification', status: 'unknown', error: null }],
      };
    });
    mount(<WorkflowRunPage />);
    fireEvent.click(await screen.findByText('Gửi lại email'));
    expect(vi.mocked(request).mock.calls.some(([config]) => config.method === 'POST')).toBe(false);
    fireEvent.click(screen.getByText('Xác nhận gửi lại'));
    expect(await screen.findByText('Retry denied')).toBeInTheDocument();
    expect(request).toHaveBeenCalledWith(
      expect.objectContaining({ method: 'POST', data: { confirmResend: true } }),
    );
  });
  it('refetches history when the status filter changes', async () => {
    respond();
    mount();
    fireEvent.click(await screen.findByText('Lịch sử'));
    fireEvent.change(screen.getByLabelText('Lọc trạng thái'), { target: { value: 'failed' } });
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith({ url: '/projects/p/workflows/flow/runs?status=failed' }),
    );
  });
});
