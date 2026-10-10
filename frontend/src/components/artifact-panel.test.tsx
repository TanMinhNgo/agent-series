import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ArtifactPanel } from './artifact-panel';
import type { LibraryAsset, Message } from '@/src/types';

vi.mock('@/src/hooks/client', () => ({
  request: vi.fn(async ({ url }: { url: string }) => {
    if (url.endsWith('/versions')) return [];
    if (url.endsWith('/preview')) return { kind: 'text', content: 'nội dung file', truncated: false };
    return {};
  }),
}));

const asset = (id: string, name: string): LibraryAsset => ({
  id,
  name,
  mimeType: 'text/plain',
  sizeBytes: 1200,
  source: 'ai',
  projectId: null,
  artifactId: `art-${id}`,
  version: 1,
  isProjectSource: false,
  indexStatus: 'ready',
  indexError: null,
  createdAt: '2026-09-29T11:55:00Z',
  url: `/files/${id}`,
});

const messages: Message[] = [
  { messageId: 'm1', role: 'assistant', content: '', artifacts: [asset('a1', 'first.json')] },
  { messageId: 'm2', role: 'assistant', content: '', artifacts: [asset('a2', 'second.md')] },
];

function renderPanel(
  onSelectedArtifactChange = vi.fn(),
  selectedArtifactId: string | null = 'a1',
  panelMessages = messages,
  open = true,
  onOpenChange = vi.fn(),
) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ArtifactPanel
        open={open}
        onOpenChange={onOpenChange}
        selectedArtifactId={selectedArtifactId}
        onSelectedArtifactChange={onSelectedArtifactChange}
        messages={panelMessages}
        canEditArtifacts
        onEditArtifact={vi.fn()}
      />
    </QueryClientProvider>,
  );
  return onSelectedArtifactChange;
}

beforeEach(() => window.localStorage.clear());

it('hides the buttons and panel when the chat has no AI files, even if open', () => {
  renderPanel(vi.fn(), null, []);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByText('Chat này chưa có file nào do AI tạo.')).not.toBeInTheDocument();
});

it('offers an open button when AI files exist and waits for a click', () => {
  const onOpenChange = vi.fn();
  renderPanel(vi.fn(), null, messages, false, onOpenChange);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Chọn file' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'File AI' }));
  expect(onOpenChange).toHaveBeenCalledWith(true);
});

it('shows the selected file in the header and its content without a file list', async () => {
  renderPanel();
  expect(await screen.findAllByText('nội dung file')).not.toHaveLength(0);
  expect(screen.getAllByRole('button', { name: 'Chọn file' })[0]).toHaveTextContent('first.json');
  expect(screen.queryByText('second.md')).not.toBeInTheDocument();
});

it('switches files from the header menu', async () => {
  const onChange = renderPanel();
  fireEvent.click(screen.getAllByRole('button', { name: 'Chọn file' })[0]);
  fireEvent.click(await screen.findByRole('menuitemradio', { name: /second\.md/ }));
  expect(onChange).toHaveBeenCalledWith('a2');
});

it('falls back to the latest file when nothing is selected', async () => {
  renderPanel(vi.fn(), null);
  expect(await screen.findAllByRole('button', { name: 'Chọn file' })).not.toHaveLength(0);
  expect(screen.getAllByRole('button', { name: 'Chọn file' })[0]).toHaveTextContent('second.md');
});
