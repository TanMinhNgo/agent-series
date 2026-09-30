import { type PointerEvent, type ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  Download,
  FilePenLine,
  FileText,
  GitCompareArrows,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PanelRightOpen,
  RotateCcw,
  X,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { request } from '@/src/hooks/client';
import type { LibraryAsset, LibraryAssetDiff, LibraryAssetPreview, Message } from '@/src/types';

type ArtifactPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedArtifactId: string | null;
  onSelectedArtifactChange: (assetId: string | null) => void;
  messages: Message[];
  canEditArtifacts: boolean;
  onEditArtifact: (asset: LibraryAsset) => void;
};

const ARTIFACT_PANEL_WIDTH_KEY = 'agent-series.artifact-panel.width';
const DEFAULT_PANEL_WIDTH = 390;
const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 720;
const EDITABLE_ARTIFACT_EXTENSIONS = ['.md', '.txt', '.json', '.py', '.ts', '.tsx'];

function isEditableArtifact(asset: LibraryAsset) {
  return EDITABLE_ARTIFACT_EXTENSIONS.some((extension) => asset.name.toLowerCase().endsWith(extension));
}

function clampPanelWidth(width: number) {
  if (typeof window === 'undefined') {
    return DEFAULT_PANEL_WIDTH;
  }

  return Math.max(
    MIN_PANEL_WIDTH,
    Math.min(width, MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, window.innerWidth - 360)),
  );
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.ceil(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

type ArtifactPreviewProps = {
  preview: { isLoading: boolean; data?: LibraryAssetPreview };
  selected: LibraryAsset;
  fullscreen?: boolean;
};

function ArtifactPreview({ preview, selected, fullscreen = false }: ArtifactPreviewProps) {
  let content: ReactNode;
  if (preview.isLoading) {
    content = (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="animate-spin" size={16} /> Đang tải preview...
      </p>
    );
  } else if (preview.data?.kind === 'image') {
    content = (
      <img
        className={fullscreen ? 'max-h-full max-w-full object-contain' : 'mx-auto max-w-full object-contain'}
        src={selected.url}
        alt={selected.name}
      />
    );
  } else if (preview.data?.kind === 'pdf') {
    content = (
      <iframe
        className={
          fullscreen ? 'h-full min-h-[60dvh] w-full rounded border bg-white' : 'h-full w-full bg-white'
        }
        src={selected.url}
        title={`Preview ${selected.name}`}
      />
    );
  } else if (preview.data?.kind === 'text') {
    content = (
      <pre
        className={
          fullscreen
            ? 'h-full w-full overflow-auto whitespace-pre-wrap text-xs leading-5'
            : 'whitespace-pre-wrap break-words text-xs leading-5'
        }
      >
        {preview.data.content}
      </pre>
    );
  } else {
    content = <p className="text-sm text-muted-foreground">Định dạng này chưa preview trực tiếp được.</p>;
  }
  const truncated = preview.data?.truncated ? (
    <p className="mt-2 text-xs text-muted-foreground">Preview đã được rút gọn.</p>
  ) : null;
  if (!fullscreen) {
    return (
      <div className={preview.data?.kind === 'pdf' ? 'h-full' : ''}>
        {content}
        {truncated}
      </div>
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4 sm:p-6">
      <div className="flex min-h-48 min-h-0 flex-1 items-center justify-center overflow-auto rounded-xl border bg-muted/20 p-3">
        {content}
      </div>
      {truncated}
    </div>
  );
}

type ArtifactGroup = { messageId: string; createdAt?: string; artifacts: LibraryAsset[] };

type ArtifactDetailsProps = {
  selected: LibraryAsset;
  latestVersion: number;
  preview: { isLoading: boolean; data?: LibraryAssetPreview };
  diff: { isLoading: boolean; data?: LibraryAssetDiff; error?: unknown };
  restorePending: boolean;
  restoreError: unknown;
  showDiff: boolean;
  onRestore: (id: string) => void;
};

function ArtifactDetails({
  selected,
  latestVersion,
  preview,
  diff,
  restorePending,
  restoreError,
  showDiff,
  onRestore,
}: ArtifactDetailsProps) {
  return (
    <>
      {selected.version < latestVersion ? (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-xs">
          <span className="text-muted-foreground">Đang xem version cũ (v{selected.version}).</span>
          <Button
            size="sm"
            variant="outline"
            disabled={restorePending}
            onClick={() => onRestore(selected.id)}
          >
            <RotateCcw size={14} />
            {restorePending ? 'Đang khôi phục...' : `Khôi phục v${selected.version}`}
          </Button>
        </div>
      ) : null}
      {restoreError ? (
        <p className="mb-3 text-sm text-destructive">Không thể khôi phục version này.</p>
      ) : null}
      <ArtifactBody showDiff={showDiff} diff={diff} preview={preview} selected={selected} />
    </>
  );
}

function ArtifactBody({
  showDiff,
  diff,
  preview,
  selected,
}: Pick<ArtifactDetailsProps, 'showDiff' | 'diff' | 'preview' | 'selected'>) {
  if (!showDiff) return <ArtifactPreview preview={preview} selected={selected} />;
  return (
    <div>
      <DiffContent diff={diff} />
      {diff.error ? <p className="mt-2 text-sm text-destructive">Không thể tải diff.</p> : null}
    </div>
  );
}

function DiffContent({ diff }: Pick<ArtifactDetailsProps, 'diff'>) {
  if (diff.isLoading) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="animate-spin" size={16} /> Đang tạo diff...
      </p>
    );
  }
  if (diff.data?.diff) return <pre className="whitespace-pre-wrap text-xs leading-5">{diff.data.diff}</pre>;
  return <p className="text-sm text-muted-foreground">Không có thay đổi giữa hai version.</p>;
}

type ArtifactHeaderProps = {
  groups: ArtifactGroup[];
  selected: LibraryAsset | null;
  versions: LibraryAsset[] | undefined;
  showDiff: boolean;
  canEditArtifacts: boolean;
  onSelect: (id: string) => void;
  onEdit: (asset: LibraryAsset) => void;
  onToggleDiff: () => void;
  onOpenFullscreen: () => void;
  onClose: () => void;
};

function ArtifactPicker({
  groups,
  selected,
  title,
  onSelect,
}: Pick<ArtifactHeaderProps, 'groups' | 'selected' | 'onSelect'> & { title: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="min-w-0 max-w-full gap-1.5 px-2"
            aria-label="Chọn file"
          />
        }
      >
        {title}
        <ChevronDown className="shrink-0 text-muted-foreground" size={14} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-72 overflow-y-auto">
        <DropdownMenuRadioGroup value={selected?.id ?? ''} onValueChange={onSelect}>
          {groups.map((group) => (
            <DropdownMenuGroup key={group.messageId}>
              <DropdownMenuLabel>
                Phản hồi {group.createdAt ? formatDate(group.createdAt) : 'vừa tạo'}
              </DropdownMenuLabel>
              {group.artifacts.map((asset) => (
                <DropdownMenuRadioItem key={asset.id} value={asset.id}>
                  <FileText className="text-muted-foreground" size={14} />
                  <span className="min-w-0 flex-1 truncate">{asset.name}</span>
                  <span className="text-xs text-muted-foreground">v{asset.version}</span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuGroup>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ArtifactHeader({
  groups,
  selected,
  versions,
  showDiff,
  canEditArtifacts,
  onSelect,
  onEdit,
  onToggleDiff,
  onOpenFullscreen,
  onClose,
}: ArtifactHeaderProps) {
  const fileCount = groups.reduce((total, group) => total + group.artifacts.length, 0);
  const title = (
    <>
      <FileText className="shrink-0 text-muted-foreground" size={16} />
      <span className="min-w-0 truncate text-sm font-medium">{selected?.name ?? 'File AI tạo'}</span>
    </>
  );
  return (
    <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
      <div className="flex min-w-0 items-center gap-1">
        {fileCount > 1 ? (
          <ArtifactPicker groups={groups} selected={selected} title={title} onSelect={onSelect} />
        ) : (
          <div className="flex min-w-0 items-center gap-1.5 px-2">{title}</div>
        )}
        {selected && versions && versions.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0 gap-1"
                  aria-label="Lịch sử phiên bản"
                />
              }
            >
              v{selected.version}
              <ChevronDown size={12} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-44">
              <DropdownMenuRadioGroup value={selected.id} onValueChange={onSelect}>
                {versions.map((asset) => (
                  <DropdownMenuRadioItem key={asset.id} value={asset.id}>
                    v{asset.version}
                    <span className="text-xs text-muted-foreground">{formatDate(asset.createdAt)}</span>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        {selected && isEditableArtifact(selected) ? (
          <>
            {selected.version > 1 ? (
              <Button
                variant={showDiff ? 'secondary' : 'ghost'}
                size="icon-sm"
                onClick={onToggleDiff}
                aria-label={showDiff ? 'Xem nội dung' : 'Xem thay đổi'}
                title={showDiff ? 'Xem nội dung' : 'Xem thay đổi'}
              >
                <GitCompareArrows size={16} />
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={!canEditArtifacts}
              onClick={() => onEdit(selected)}
              aria-label="Sửa file này"
              title={canEditArtifacts ? 'Sửa file này bằng AI' : 'Ollama local chưa hỗ trợ sửa file'}
            >
              <FilePenLine size={16} />
            </Button>
          </>
        ) : null}
        {selected ? (
          <>
            <Button
              variant="ghost"
              size="icon-sm"
              nativeButton={false}
              render={<a href={selected.url} target="_blank" rel="noreferrer" />}
              aria-label="Mở hoặc tải file gốc"
              title="Mở hoặc tải file gốc"
            >
              <Download size={16} />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onOpenFullscreen}
              aria-label="Mở rộng xem nội dung"
              title="Mở rộng xem nội dung"
            >
              <Maximize2 size={16} />
            </Button>
          </>
        ) : null}
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Đóng file AI tạo">
          <X size={16} />
        </Button>
      </div>
    </div>
  );
}

export function ArtifactPanel({
  open,
  onOpenChange,
  selectedArtifactId,
  onSelectedArtifactChange,
  messages,
  canEditArtifacts,
  onEditArtifact,
}: ArtifactPanelProps) {
  const queryClient = useQueryClient();
  const [panelWidth, setPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_PANEL_WIDTH;

    const storedWidth = Number(window.localStorage.getItem(ARTIFACT_PANEL_WIDTH_KEY));
    return Number.isFinite(storedWidth) && storedWidth > 0
      ? clampPanelWidth(storedWidth)
      : DEFAULT_PANEL_WIDTH;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const resizeStart = useRef<{ x: number; width: number } | null>(null);
  const groups = useMemo(
    () =>
      messages.flatMap((message) =>
        message.role === 'assistant' && message.artifacts?.length
          ? [
              {
                messageId: message.messageId || message.createdAt || message.content,
                createdAt: message.createdAt,
                artifacts: message.artifacts,
              },
            ]
          : [],
      ),
    [messages],
  );
  const generatedArtifacts = useMemo(() => groups.flatMap((group) => group.artifacts), [groups]);
  const initialSelected = generatedArtifacts.find((asset) => asset.id === selectedArtifactId) ?? null;
  const activeId = selectedArtifactId ?? generatedArtifacts.at(-1)?.id ?? null;
  const versions = useQuery({
    queryKey: ['artifact-versions', activeId],
    queryFn: () => request<LibraryAsset[]>({ url: `/library/assets/${activeId}/versions` }),
    enabled: Boolean(activeId),
  });
  const selected = useMemo(
    () => [...generatedArtifacts, ...(versions.data ?? [])].find((asset) => asset.id === activeId) ?? null,
    [generatedArtifacts, activeId, versions.data],
  );
  const preview = useQuery({
    queryKey: ['artifact-preview', selected?.id],
    queryFn: () => request<LibraryAssetPreview>({ url: `/library/assets/${selected?.id}/preview` }),
    enabled: Boolean(selected),
  });
  const diff = useQuery({
    queryKey: ['artifact-diff', selected?.id],
    queryFn: () => request<LibraryAssetDiff>({ url: `/library/assets/${selected?.id}/diff` }),
    enabled: Boolean(selected && selected.version > 1 && showDiff),
  });
  const restoreVersion = useMutation({
    mutationFn: (assetId: string) =>
      request<LibraryAsset>({ url: `/library/assets/${assetId}/restore`, method: 'POST' }),
    onSuccess: (asset) => {
      void queryClient.invalidateQueries({ queryKey: ['artifact-versions'] });
      void queryClient.invalidateQueries({ queryKey: ['generated-artifacts'] });
      selectArtifact(asset.id);
    },
  });

  useEffect(() => {
    if (
      selectedArtifactId &&
      generatedArtifacts.length &&
      !initialSelected &&
      !versions.isLoading &&
      !selected
    ) {
      onSelectedArtifactChange(null);
    }
  }, [
    generatedArtifacts.length,
    initialSelected,
    onSelectedArtifactChange,
    selected,
    selectedArtifactId,
    versions.isLoading,
  ]);

  useEffect(() => {
    const handleWindowResize = () => setPanelWidth((width) => clampPanelWidth(width));
    window.addEventListener('resize', handleWindowResize);
    return () => window.removeEventListener('resize', handleWindowResize);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ARTIFACT_PANEL_WIDTH_KEY, String(panelWidth));
  }, [panelWidth]);

  useEffect(() => {
    if (!isFullscreen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  const updatePanelWidth = (width: number) => setPanelWidth(clampPanelWidth(width));
  const selectArtifact = (assetId: string | null) => {
    setIsFullscreen(false);
    setShowDiff(false);
    onSelectedArtifactChange(assetId);
  };
  const latestVersion = Math.max(
    selected?.version ?? 1,
    ...(versions.data ?? []).map((asset) => asset.version),
  );

  const startResize = (event: PointerEvent<HTMLButtonElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStart.current = { x: event.clientX, width: panelWidth };
    setIsResizing(true);
  };

  const resizePanel = (event: PointerEvent<HTMLButtonElement>) => {
    if (!resizeStart.current) return;
    updatePanelWidth(resizeStart.current.width + resizeStart.current.x - event.clientX);
  };

  const finishResize = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    resizeStart.current = null;
    setIsResizing(false);
  };

  const body = (
    <>
      <ArtifactHeader
        groups={groups}
        selected={selected}
        versions={versions.data}
        showDiff={showDiff}
        canEditArtifacts={canEditArtifacts}
        onSelect={selectArtifact}
        onEdit={onEditArtifact}
        onToggleDiff={() => setShowDiff((value) => !value)}
        onOpenFullscreen={() => setIsFullscreen(true)}
        onClose={() => onOpenChange(false)}
      />
      <div
        className={`min-h-0 flex-1 ${selected && preview.data?.kind === 'pdf' && !showDiff ? 'overflow-hidden' : 'overflow-auto p-4'}`}
      >
        {!selected ? (
          <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
            Chat này chưa có file nào do AI tạo.
          </div>
        ) : (
          <ArtifactDetails
            selected={selected}
            latestVersion={latestVersion}
            preview={preview}
            diff={diff}
            restorePending={restoreVersion.isPending}
            restoreError={restoreVersion.error}
            showDiff={showDiff}
            onRestore={(assetId) => restoreVersion.mutate(assetId)}
          />
        )}
      </div>
    </>
  );

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="fixed right-4 bottom-4 z-30 shadow-lg lg:hidden"
        onClick={() => onOpenChange(true)}
        aria-label="Mở file AI tạo"
      >
        <PanelRightOpen size={16} /> File AI
      </Button>
      {open ? (
        <>
          <aside
            className="relative hidden shrink-0 border-l bg-background lg:flex lg:min-h-0 lg:flex-col"
            style={{ width: panelWidth }}
          >
            <button
              type="button"
              className={`absolute inset-y-0 -left-1 z-10 hidden w-2 cursor-col-resize touch-none lg:block ${
                isResizing ? 'bg-primary/30' : 'hover:bg-primary/20'
              }`}
              aria-label="Điều chỉnh độ rộng File AI tạo"
              onPointerDown={startResize}
              onPointerMove={resizePanel}
              onPointerUp={finishResize}
              onPointerCancel={finishResize}
              onKeyDown={(event) => {
                if (event.key === 'ArrowLeft') {
                  event.preventDefault();
                  updatePanelWidth(panelWidth - 20);
                }
                if (event.key === 'ArrowRight') {
                  event.preventDefault();
                  updatePanelWidth(panelWidth + 20);
                }
              }}
            />
            {body}
          </aside>
          <dialog
            open
            aria-modal="true"
            className="fixed inset-0 z-50 m-0 h-full max-h-none w-full max-w-none border-0 bg-black/50 p-3 lg:hidden"
          >
            <aside className="ml-auto flex h-full w-full max-w-md flex-col rounded-2xl border bg-background shadow-2xl">
              {body}
            </aside>
          </dialog>
        </>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="fixed right-4 top-20 z-30 hidden shadow-lg lg:flex"
          onClick={() => onOpenChange(true)}
        >
          <PanelRightOpen size={16} /> File AI
        </Button>
      )}
      {isFullscreen && selected ? (
        <dialog
          open
          className="fixed inset-0 z-[60] m-0 flex h-full max-h-none w-full max-w-none min-h-0 flex-col border-0 bg-background/95 p-0 text-foreground backdrop-blur-sm"
          aria-modal="true"
          aria-label={`Xem toàn màn hình ${selected.name}`}
        >
          <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3 sm:px-6">
            <div className="flex min-w-0 items-center gap-2.5">
              <FileText className="shrink-0 text-muted-foreground" size={18} />
              <div className="min-w-0">
                <h2 className="truncate font-medium">{selected.name}</h2>
                <p className="text-xs text-muted-foreground">
                  Version {selected.version} · {formatSize(selected.sizeBytes)}
                </p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsFullscreen(false)}
              aria-label="Thu gọn xem nội dung"
              title="Thu gọn (Esc)"
            >
              <Minimize2 size={18} />
            </Button>
          </div>
          <ArtifactPreview preview={preview} selected={selected} fullscreen />
        </dialog>
      ) : null}
    </>
  );
}
