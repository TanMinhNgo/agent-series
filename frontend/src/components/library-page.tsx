import { useDeferredValue, useRef, useState } from 'react';
import {
  Eye,
  FilePlus2,
  FileUp,
  FolderKanban,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/src/hooks/use-workspace';
import { useLibraryData } from '@/src/hooks/use-library-data';
import { useUploadDocuments } from '@/src/hooks/use-upload-documents';
import type { LibraryAsset } from '@/src/types';
const size = (value: number) =>
  value < 1024 * 1024 ? `${Math.ceil(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`;

export function LibraryPage() {
  const [tab, setTab] = useState<'files' | 'memory' | 'documents'>('files');
  const [query, setQuery] = useState('');
  const [assetScope, setAssetScope] = useState<'all' | 'global' | 'project'>('all');
  const [assetProjectId, setAssetProjectId] = useState('');
  const [pinningAssetId, setPinningAssetId] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState<LibraryAsset | null>(null);
  const [renamingAsset, setRenamingAsset] = useState<LibraryAsset | null>(null);
  const [assetName, setAssetName] = useState('');
  const [versioningId, setVersioningId] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<{ name: string; message: string }[]>([]);
  const [collectionProjectId, setCollectionProjectId] = useState('');
  const [collectionName, setCollectionName] = useState('');
  const [editingCollectionId, setEditingCollectionId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const versionInputRef = useRef<HTMLInputElement>(null);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const deferredQuery = useDeferredValue(query);
  const { projects } = useWorkspace();
  const uploadDocuments = useUploadDocuments();
  const {
    assets,
    memories,
    documents,
    worker,
    collections,
    preview,
    versions,
    upload,
    deleteAsset,
    updateAsset,
    createVersion,
    reindexArtifact,
    deleteMemory,
    reindex,
    deleteDocument,
    createCollection,
    saveCollectionDocuments,
    deleteCollection,
  } = useLibraryData({
    query: deferredQuery,
    scope: assetScope,
    projectId: assetProjectId,
    collectionProjectId,
    previewId: previewing?.id,
    onUpload: setUploadErrors,
    onCollectionCreated: () => setCollectionName(''),
  });
  const loading =
    tab === 'files' ? assets.isLoading : tab === 'memory' ? memories.isLoading : documents.isLoading;
  const error =
    assets.error ||
    memories.error ||
    documents.error ||
    upload.error ||
    uploadDocuments.error ||
    deleteAsset.error ||
    updateAsset.error ||
    createVersion.error ||
    reindexArtifact.error ||
    deleteMemory.error ||
    reindex.error ||
    deleteDocument.error;
  const openRenameAsset = (asset: LibraryAsset) => {
    updateAsset.reset();
    setAssetName(asset.name);
    setRenamingAsset(asset);
  };
  const saveAssetName = () => {
    if (!renamingAsset || !assetName.trim() || assetName.trim() === renamingAsset.name) return;
    updateAsset.mutate(
      { id: renamingAsset.id, data: { name: assetName.trim() } },
      { onSuccess: () => setRenamingAsset(null) },
    );
  };
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
          <input
            ref={versionInputRef}
            className="sr-only"
            type="file"
            accept=".pdf,.docx,.xlsx,.pptx,.md,.csv,.json,.txt,image/*"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file && versioningId) createVersion.mutate({ id: versioningId, file });
              event.target.value = '';
              setVersioningId(null);
            }}
          />
          <input
            ref={documentInputRef}
            className="sr-only"
            type="file"
            multiple
            accept=".pdf,.docx,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown"
            onChange={(event) => {
              const files = Array.from(event.target.files || []);
              if (files.length) uploadDocuments.mutate({ files });
              event.target.value = '';
            }}
          />
          <Button
            type="button"
            disabled={tab === 'documents' ? uploadDocuments.isPending : upload.isPending}
            onClick={() =>
              tab === 'documents' ? documentInputRef.current?.click() : fileInputRef.current?.click()
            }
          >
            {(tab === 'documents' ? uploadDocuments.isPending : upload.isPending) ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <FileUp />
            )}
            {tab === 'documents'
              ? uploadDocuments.isPending
                ? 'Đang tải...'
                : 'Thêm tài liệu RAG'
              : upload.isPending
                ? 'Đang tải...'
                : 'Tải file lên'}
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
        {tab === 'files' ? (
          <div className="flex gap-2">
            <select
              className="min-w-40 rounded-lg border bg-background px-3 py-2 text-sm"
              value={assetScope === 'project' ? `project:${assetProjectId}` : assetScope}
              onChange={(event) => {
                const value = event.target.value;
                if (value.startsWith('project:')) {
                  setAssetScope('project');
                  setAssetProjectId(value.slice('project:'.length));
                } else {
                  setAssetScope(value as 'all' | 'global');
                  setAssetProjectId('');
                }
              }}
              aria-label="Lọc file theo Project"
            >
              <option value="all">Tất cả file</option>
              <option value="global">Không thuộc Project</option>
              {(projects.data || []).map((project) => (
                <option key={project.id} value={`project:${project.id}`}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
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
              <button
                className="block max-w-full truncate text-left font-medium hover:underline"
                onClick={() => setPreviewing(item)}
              >
                {item.name}
              </button>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.mimeType} · {size(item.sizeBytes)} ·{' '}
                {new Date(item.createdAt).toLocaleDateString('vi-VN')}
              </p>
              <div className="mt-2 flex flex-wrap gap-1 text-xs">
                <span className="rounded bg-muted px-2 py-1">v{item.version}</span>
                {item.isProjectSource ? (
                  <span className="rounded bg-emerald-500/10 px-2 py-1 text-emerald-700">Project source</span>
                ) : null}
                {item.isProjectSource && item.indexStatus !== 'ready' ? (
                  <span className="rounded bg-amber-500/10 px-2 py-1 text-amber-700">
                    {item.indexStatus === 'failed' ? 'Index lỗi' : 'Đang index'}
                  </span>
                ) : null}
              </div>
              {item.indexError ? <p className="mt-2 text-xs text-destructive">{item.indexError}</p> : null}
              <div className="mt-4 flex justify-between">
                <span className="text-xs text-muted-foreground">
                  {item.source === 'generated' ? 'AI tạo' : 'Đã tải lên'}
                  {item.projectId
                    ? ` · ${(projects.data || []).find((project) => project.id === item.projectId)?.name || 'Project'}`
                    : ' · Thư viện chung'}
                </span>
                <div className="flex gap-1">
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => setPreviewing(item)}
                    aria-label={`Xem ${item.name}`}
                  >
                    <Eye />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => openRenameAsset(item)}
                    aria-label={`Đổi tên ${item.name}`}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => {
                      setVersioningId(item.id);
                      versionInputRef.current?.click();
                    }}
                    aria-label={`Tạo version mới cho ${item.name}`}
                  >
                    <FilePlus2 />
                  </Button>
                  {item.isProjectSource && item.indexStatus === 'failed' ? (
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => reindexArtifact.mutate(item.id)}
                      aria-label={`Index lại ${item.name}`}
                    >
                      <RefreshCw />
                    </Button>
                  ) : null}
                  <Button
                    size="icon-sm"
                    variant={item.isProjectSource ? 'secondary' : 'ghost'}
                    onClick={() => {
                      if (item.isProjectSource)
                        updateAsset.mutate({ id: item.id, data: { isProjectSource: false } });
                      else if (item.projectId)
                        updateAsset.mutate({ id: item.id, data: { isProjectSource: true } });
                      else setPinningAssetId(item.id);
                    }}
                    aria-label={`Ghim ${item.name} vào Project`}
                  >
                    <FolderKanban />
                  </Button>
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
              </div>
              {pinningAssetId === item.id ? (
                <select
                  className="mt-3 w-full rounded-md border bg-background px-2 py-1 text-xs"
                  autoFocus
                  defaultValue=""
                  onChange={(event) => {
                    if (event.target.value)
                      updateAsset.mutate({
                        id: item.id,
                        data: { projectId: event.target.value, isProjectSource: true },
                      });
                    setPinningAssetId(null);
                  }}
                >
                  <option value="">Chọn Project để ghim…</option>
                  {(projects.data || []).map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              ) : null}
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
          <section className="rounded-xl border p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold">Knowledge collections</h2>
                <p className="text-sm text-muted-foreground">
                  Tải PDF, DOCX hoặc Markdown; chọn theo từng Project để chat chỉ tìm đúng bộ nguồn.
                </p>
              </div>
              <select
                className="rounded-lg border bg-background px-3 py-2 text-sm"
                value={collectionProjectId}
                onChange={(event) => {
                  setCollectionProjectId(event.target.value);
                  setEditingCollectionId(null);
                }}
              >
                <option value="">Chọn Project…</option>
                {(projects.data || []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            {collectionProjectId ? (
              <>
                <form
                  className="mt-3 flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (collectionName.trim()) createCollection.mutate(collectionName.trim());
                  }}
                >
                  <input
                    className="min-w-0 flex-1 rounded-lg border bg-background px-3 py-2 text-sm"
                    value={collectionName}
                    onChange={(event) => setCollectionName(event.target.value)}
                    placeholder="Tên collection, ví dụ: Báo cáo quý"
                  />
                  <Button size="sm" disabled={createCollection.isPending}>
                    Tạo collection
                  </Button>
                </form>
                <div className="mt-3 space-y-2">
                  {(collections.data || []).map((collection) => (
                    <article key={collection.id} className="rounded-lg border p-3">
                      <div className="flex items-center justify-between gap-3">
                        <button
                          className="text-left font-medium hover:underline"
                          onClick={() =>
                            setEditingCollectionId(
                              editingCollectionId === collection.id ? null : collection.id,
                            )
                          }
                        >
                          {collection.name}{' '}
                          <span className="text-xs font-normal text-muted-foreground">
                            · {collection.documentIds.length} tài liệu
                          </span>
                        </button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive"
                          onClick={() => deleteCollection.mutate(collection.id)}
                        >
                          <Trash2 /> Xóa
                        </Button>
                      </div>
                      {editingCollectionId === collection.id ? (
                        <div className="mt-3 space-y-2">
                          {(documents.data || [])
                            .filter((document) => document.projectId === collectionProjectId)
                            .map((document) => (
                              <label key={document.id} className="flex items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={collection.documentIds.includes(document.id)}
                                  onChange={(event) => {
                                    const documentIds = event.target.checked
                                      ? [...collection.documentIds, document.id]
                                      : collection.documentIds.filter((id: string) => id !== document.id);
                                    saveCollectionDocuments.mutate({ id: collection.id, documentIds });
                                  }}
                                />
                                {document.name}
                              </label>
                            ))}
                          {!(documents.data || []).some(
                            (document) => document.projectId === collectionProjectId,
                          ) ? (
                            <p className="text-sm text-muted-foreground">Project này chưa có tài liệu RAG.</p>
                          ) : null}
                        </div>
                      ) : null}
                    </article>
                  ))}
                  {!collections.isLoading && !collections.data?.length ? (
                    <p className="text-sm text-muted-foreground">Chưa có collection nào cho Project này.</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </section>
          {(documents.data || []).map((item) => (
            <article key={item.id} className="rounded-xl border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{item.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {item.status === 'ready'
                      ? item.name.toLowerCase().endsWith('.pdf')
                        ? `${item.pageCount || 0} trang đã index`
                        : `${item.pageCount || 0} đoạn đã index`
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
      {previewing ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
        >
          <section className="max-h-[94dvh] w-[96vw] max-w-[1280px] overflow-auto rounded-2xl border bg-card p-5 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold">
                  {previewing.name} · v{previewing.version}
                </h2>
                <p className="text-sm text-muted-foreground">Preview và lịch sử version</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setPreviewing(null)}>
                Đóng
              </Button>
            </div>
            <div className="mt-4 rounded-lg border bg-muted/20 p-3">
              {preview.isLoading ? (
                <p className="text-sm text-muted-foreground">Đang tải preview…</p>
              ) : preview.data?.kind === 'image' ? (
                <img
                  className="max-h-96 max-w-full object-contain"
                  src={previewing.url}
                  alt={previewing.name}
                />
              ) : preview.data?.kind === 'pdf' ? (
                <iframe
                  className="h-[76dvh] w-full rounded border bg-white"
                  src={previewing.url}
                  title={`Preview ${previewing.name}`}
                />
              ) : preview.data?.kind === 'text' ? (
                <pre className="max-h-[70dvh] overflow-auto whitespace-pre-wrap text-xs">
                  {preview.data.content}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Không thể preview trực tiếp; hãy tải file để xem.
                </p>
              )}
              {preview.data?.truncated ? (
                <p className="mt-2 text-xs text-muted-foreground">Preview đã được rút gọn.</p>
              ) : null}
            </div>
            <div className="mt-4">
              <a
                className="text-sm text-primary hover:underline"
                href={previewing.url}
                target="_blank"
                rel="noreferrer"
              >
                Mở hoặc tải file gốc
              </a>
              <h3 className="mt-4 text-sm font-medium">Lịch sử version</h3>
              <div className="mt-2 space-y-2">
                {(versions.data || []).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
                  >
                    <span>
                      v{item.version} · {new Date(item.createdAt).toLocaleDateString('vi-VN')}
                    </span>
                    <a
                      className="text-primary hover:underline"
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Mở file
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      ) : null}
      {renamingAsset ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rename-asset-title"
        >
          <form
            className="w-full max-w-md rounded-2xl border bg-card p-5 shadow-2xl"
            onSubmit={(event) => {
              event.preventDefault();
              saveAssetName();
            }}
          >
            <h2 id="rename-asset-title" className="font-semibold">
              Đổi tên tài liệu
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">Tên mới sẽ áp dụng cho file trong Thư viện.</p>
            <label className="mt-4 block text-sm font-medium" htmlFor="asset-name">
              Tên tài liệu
            </label>
            <input
              id="asset-name"
              autoFocus
              className="mt-2 w-full rounded-lg border bg-background px-3 py-2 text-sm"
              value={assetName}
              onChange={(event) => setAssetName(event.target.value)}
              maxLength={255}
              required
            />
            {updateAsset.error ? (
              <p className="mt-2 text-sm text-destructive">{updateAsset.error.message}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setRenamingAsset(null)}
                disabled={updateAsset.isPending}
              >
                Hủy
              </Button>
              <Button
                type="submit"
                disabled={
                  updateAsset.isPending || !assetName.trim() || assetName.trim() === renamingAsset.name
                }
              >
                {updateAsset.isPending ? 'Đang lưu...' : 'Lưu tên'}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
