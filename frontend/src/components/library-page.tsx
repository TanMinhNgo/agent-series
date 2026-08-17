import { useDeferredValue, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileUp, LoaderCircle, RefreshCw, Search, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { request } from '@/src/hooks/client';

type Asset = {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  source: string;
  createdAt: string;
  url: string;
};
type Memory = { id: string; chatTitle: string; role: string; content: string; createdAt: string };
type Document = {
  id: string;
  name: string;
  status: string;
  pageCount: number | null;
  error: string | null;
  jobAttempts: number;
  jobMaxAttempts: number;
  jobError: string | null;
};
type WorkerStatus = {
  online: boolean;
  lastHeartbeatAt: string | null;
  currentJobType: string | null;
  queued: number;
  running: number;
  failed: number;
  lastError: string | null;
};
type UploadResult = { items: Asset[]; errors: { name: string; message: string }[] };
const size = (value: number) =>
  value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;

export function LibraryPage() {
  const [tab, setTab] = useState<'files' | 'memory' | 'documents'>('files');
  const [query, setQuery] = useState('');
  const [uploadErrors, setUploadErrors] = useState<{ name: string; message: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const deferredQuery = useDeferredValue(query);
  const queryClient = useQueryClient();
  const assets = useQuery({
    queryKey: ['library-assets', deferredQuery],
    queryFn: () => request<Asset[]>({ url: '/library/assets', params: { query: deferredQuery } }),
  });
  const memories = useQuery({
    queryKey: ['memories', deferredQuery],
    queryFn: () => request<Memory[]>({ url: '/memories', params: { query: deferredQuery } }),
  });
  const documents = useQuery({
    queryKey: ['documents'],
    queryFn: () => request<Document[]>({ url: '/documents' }),
    refetchInterval: (queryState) =>
      queryState.state.data?.some((item) => item.status === 'queued' || item.status === 'indexing')
        ? 1500
        : false,
  });
  const worker = useQuery({
    queryKey: ['worker-status'],
    queryFn: () => request<WorkerStatus>({ url: '/worker/status' }),
    refetchInterval: 3000,
  });
  const invalidateLibrary = () => void queryClient.invalidateQueries({ queryKey: ['library-assets'] });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const data = new FormData();
      files.forEach((file) => data.append('files', file));
      return request<UploadResult>({ url: '/library/assets', method: 'POST', data });
    },
    onSuccess: (result) => {
      setUploadErrors(result.errors);
      invalidateLibrary();
    },
  });
  const deleteAsset = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/library/assets/${id}`, method: 'DELETE' }),
    onSuccess: invalidateLibrary,
  });
  const deleteMemory = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/memories/${id}`, method: 'DELETE' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['memories'] }),
  });
  const reindex = useMutation({
    mutationFn: (id: string) => request<Document>({ url: `/documents/${id}/reindex`, method: 'POST' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  const deleteDocument = useMutation({
    mutationFn: (id: string) => request<void>({ url: `/documents/${id}`, method: 'DELETE' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  const loading =
    tab === 'files' ? assets.isLoading : tab === 'memory' ? memories.isLoading : documents.isLoading;
  const error =
    assets.error ||
    memories.error ||
    documents.error ||
    upload.error ||
    deleteAsset.error ||
    deleteMemory.error ||
    reindex.error ||
    deleteDocument.error;
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-7 sm:px-8 lg:px-12">
      <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Kho cá nhân</p>
          <h1 className="text-3xl font-semibold tracking-tight">Thư viện</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Quản lý file upload, file AI tạo và memory của bạn.
          </p>
        </div>
        <>
          <input
            ref={fileInputRef}
            className="sr-only"
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx,.pptx,.md,.csv,.json,.txt,image/*"
            onChange={(event) => {
              const files = Array.from(event.target.files || []);
              if (files.length) upload.mutate(files);
              event.target.value = '';
            }}
          />
          <Button type="button" disabled={upload.isPending} onClick={() => fileInputRef.current?.click()}>
            {upload.isPending ? <LoaderCircle className="animate-spin" /> : <FileUp />}
            {upload.isPending ? 'Đang tải...' : 'Tải file lên'}
          </Button>
        </>
      </header>
      {uploadErrors.length ? (
        <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <p className="font-medium">Một số file chưa được tải lên:</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {uploadErrors.map((item) => (
              <li key={`${item.name}-${item.message}`}>
                {item.name}: {item.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <div className="flex gap-1 rounded-lg border p-1">
          <Button size="sm" variant={tab === 'files' ? 'secondary' : 'ghost'} onClick={() => setTab('files')}>
            Tệp
          </Button>
          <Button
            size="sm"
            variant={tab === 'memory' ? 'secondary' : 'ghost'}
            onClick={() => setTab('memory')}
          >
            Memory
          </Button>
          <Button
            size="sm"
            variant={tab === 'documents' ? 'secondary' : 'ghost'}
            onClick={() => setTab('documents')}
          >
            Tài liệu RAG
          </Button>
        </div>
        <label className="flex flex-1 items-center gap-2 rounded-lg border px-3">
          <Search size={16} className="text-muted-foreground" />
          <input
            className="w-full bg-transparent py-2 text-sm outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm trong Thư viện..."
          />
        </label>
      </div>
      {loading ? (
        <p className="mt-8 flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="animate-spin" size={16} />
          Đang tải...
        </p>
      ) : error ? (
        <p className="mt-8 text-sm text-destructive">{error.message}</p>
      ) : tab === 'files' ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(assets.data || []).map((item) => (
            <article key={item.id} className="rounded-xl border p-4">
              <a
                className="block truncate font-medium hover:underline"
                href={item.url}
                target="_blank"
                rel="noreferrer"
              >
                {item.name}
              </a>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.mimeType} · {size(item.sizeBytes)} ·{' '}
                {new Date(item.createdAt).toLocaleDateString('vi-VN')}
              </p>
              <div className="mt-4 flex justify-between">
                <span className="text-xs text-muted-foreground">
                  {item.source === 'generated' ? 'AI tạo' : 'Đã tải lên'}
                </span>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => deleteAsset.mutate(item.id)}
                  aria-label={`Xóa ${item.name}`}
                >
                  <Trash2 />
                </Button>
              </div>
            </article>
          ))}
          {!assets.data?.length ? (
            <p className="col-span-full py-12 text-center text-sm text-muted-foreground">
              Chưa có file. Tải lên file đầu tiên của bạn.
            </p>
          ) : null}
        </div>
      ) : tab === 'memory' ? (
        <div className="mt-5 space-y-2">
          {(memories.data || []).map((item) => (
            <article key={item.id} className="rounded-xl border p-4">
              <p className="text-xs text-muted-foreground">
                {item.chatTitle} · {new Date(item.createdAt).toLocaleDateString('vi-VN')}
              </p>
              <p className="mt-1 text-sm">{item.content}</p>
              <Button
                size="sm"
                variant="ghost"
                className="mt-2 text-destructive"
                onClick={() => deleteMemory.mutate(item.id)}
              >
                <Trash2 /> Xóa
              </Button>
            </article>
          ))}
          {!memories.data?.length ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Chưa có memory phù hợp.</p>
          ) : null}
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {worker.data ? (
            <section
              className={`rounded-xl border p-4 text-sm ${
                worker.data.online
                  ? 'border-emerald-500/30 bg-emerald-500/5'
                  : 'border-destructive/30 bg-destructive/5'
              }`}
            >
              <p className="font-medium">
                {worker.data.online ? 'Worker đang hoạt động' : 'Worker đang offline hoặc chưa khởi động'}
              </p>
              <p className="mt-1 text-muted-foreground">
                Queue: {worker.data.queued} chờ · {worker.data.running} đang chạy · {worker.data.failed} thất
                bại
                {worker.data.currentJobType ? ` · ${worker.data.currentJobType}` : ''}
              </p>
              {!worker.data.online ? (
                <p className="mt-1 text-destructive">
                  Chạy lại <code>./run.ps1</code> để khởi động worker.
                </p>
              ) : null}
              {worker.data.lastError ? (
                <p className="mt-1 text-destructive">Lỗi gần nhất: {worker.data.lastError}</p>
              ) : null}
            </section>
          ) : null}
          {(documents.data || []).map((item) => (
            <article key={item.id} className="rounded-xl border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{item.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.status === 'ready'
                      ? `${item.pageCount || 0} trang đã index`
                      : item.status === 'queued' || item.status === 'indexing'
                        ? 'Đang xử lý nền...'
                        : item.status === 'needs_ocr'
                          ? 'Cần OCR'
                          : 'Index thất bại'}
                  </p>
                  {item.error ? <p className="mt-1 text-sm text-destructive">{item.error}</p> : null}
                  {item.status !== 'ready' && item.status !== 'needs_ocr' ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Lần thử: {item.jobAttempts}/{item.jobMaxAttempts}
                      {item.jobError ? ` · ${item.jobError}` : ''}
                    </p>
                  ) : null}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={reindex.isPending}
                    onClick={() => reindex.mutate(item.id)}
                  >
                    <RefreshCw /> Index lại
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    className="text-destructive"
                    aria-label={`Xóa ${item.name}`}
                    onClick={() => deleteDocument.mutate(item.id)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            </article>
          ))}
          {!documents.data?.length ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Chưa có tài liệu RAG.</p>
          ) : null}
        </div>
      )}
      <section className="mt-10 rounded-xl border border-dashed p-5">
        <h2 className="font-semibold">Nguồn kết nối</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Google Drive, OneDrive/SharePoint và Dropbox đang cập nhật tính năng kết nối.
        </p>
      </section>
    </div>
  );
}
