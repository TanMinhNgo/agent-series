import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { request } from '@/src/hooks/client';

import { ProjectOverviewPage } from './project-overview-page';

vi.mock('@/src/hooks/client', () => ({ request: vi.fn() }));

const timestamp = '2026-09-09T09:30:00+00:00';

describe('ProjectOverviewPage', () => {
  beforeEach(() => vi.mocked(request).mockReset());

  it('shows recent Project resources and the activity actor', async () => {
    window.history.pushState({}, '', '/projects/project-1');
    vi.mocked(request).mockResolvedValue({
      project: {
        id: 'project-1',
        name: 'Roadmap 3',
        description: 'Hoàn thiện workspace',
        status: 'active',
        instructions: null,
        memoryMode: 'default',
        createdAt: timestamp,
        updatedAt: timestamp,
      },
      chats: [{ id: 'chat-1', title: 'Lập kế hoạch', updatedAt: timestamp }],
      documents: [
        { id: 'document-1', name: 'spec.pdf', status: 'ready', url: '/api/documents/document-1/file' },
      ],
      assets: [{ id: 'asset-1', name: 'brief.md', version: 2, url: '/api/library/assets/asset-1/file' }],
      projectSources: [],
      schedules: [{ id: 'schedule-1', title: 'Báo cáo tuần', nextRunAt: timestamp, status: 'active' }],
      activity: [
        {
          id: 'activity-1',
          eventType: 'artifact.deleted',
          subjectType: 'artifact',
          subjectId: 'asset-1',
          summary: 'Đã xóa file cũ.',
          actorUserId: 'user-1',
          actorDisplayName: 'Minh',
          createdAt: timestamp,
        },
      ],
      connectorScopes: [],
    });

    render(
      <MemoryRouter initialEntries={['/projects/project-1']}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ProjectOverviewPage />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Artifact mới')).toBeInTheDocument();
    expect(screen.getByText('brief.md')).toBeInTheDocument();
    expect(screen.getByText('Báo cáo tuần')).toBeInTheDocument();
    expect(screen.getByText('spec.pdf')).toBeInTheDocument();
    expect(screen.getByText('Minh')).toBeInTheDocument();
  });
});
