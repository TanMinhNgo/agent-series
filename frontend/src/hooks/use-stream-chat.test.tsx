import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { readSse } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';

import { useStreamChat } from './use-stream-chat';

vi.mock('@/src/hooks/client', () => ({
  ApiError: class ApiError extends Error {},
  apiBaseUrl: '/api',
  readSse: vi.fn(),
  request: vi.fn(),
}));

describe('useStreamChat', () => {
  beforeEach(() => {
    vi.mocked(readSse).mockReset();
    vi.mocked(readSse).mockResolvedValue(undefined);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
  });

  it('cancels a pending messages query before inserting an optimistic turn', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const cancelQueries = vi.spyOn(client, 'cancelQueries');
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useStreamChat(), { wrapper });

    await result.current.mutateAsync({
      chatId: 'chat-1',
      content: 'Xin chào',
      runId: 'run-1',
      onEvent: vi.fn(),
    });

    expect(cancelQueries).toHaveBeenCalledWith({ queryKey: queryKeys.messages('chat-1') });
    expect(client.getQueryData(queryKeys.messages('chat-1'))).toMatchObject([
      { role: 'user', content: 'Xin chào', optimistic: true },
    ]);
  });
});
