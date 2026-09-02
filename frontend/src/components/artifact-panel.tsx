import { type PointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import { FileText, LoaderCircle, Maximize2, Minimize2, PanelRightOpen, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import { request } from '@/src/hooks/client';
import type { LibraryAsset, LibraryAssetPreview, Message } from '@/src/types';

type ArtifactPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedArtifactId: string | null;
  onSelectedArtifactChange: (assetId: string | null) => void;
  messages: Message[];
};

const ARTIFACT_PANEL_WIDTH_KEY = 'agent-series.artifact-panel.width';
const DEFAULT_PANEL_WIDTH = 390;
const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 720;

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

export function ArtifactPanel({
  open,
  onOpenChange,
  selectedArtifactId,
  onSelectedArtifactChange,
  messages,
}: ArtifactPanelProps) {
  const [panelWidth, setPanelWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_PANEL_WIDTH;

    const storedWidth = Number(window.localStorage.getItem(ARTIFACT_PANEL_WIDTH_KEY));
    return Number.isFinite(storedWidth) && storedWidth > 0
      ? clampPanelWidth(storedWidth)
      : DEFAULT_PANEL_WIDTH;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
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
  const initialSelected = generatedArtifacts.find((asset) => asset.id === selectedArtifactId) || null;
  const versions = useQuery({
    queryKey: ['artifact-versions', selectedArtifactId],
    queryFn: () => request<LibraryAsset[]>({ url: `/library/assets/${selectedArtifactId}/versions` }),
    enabled: Boolean(selectedArtifactId),
  });
  const selected = useMemo(
    () =>
      [...generatedArtifacts, ...(versions.data || [])].find((asset) => asset.id === selectedArtifactId) ||
      null,
    [generatedArtifacts, selectedArtifactId, versions.data],
  );
  const preview = useQuery({
    queryKey: ['artifact-preview', selected?.id],
    queryFn: () => request<LibraryAssetPreview>({ url: `/library/assets/${selected?.id}/preview` }),
    enabled: Boolean(selected),
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
    onSelectedArtifactChange(assetId);
  };

  const renderPreview = (fullscreen = false) => (
    <div className={`min-h-0 ${fullscreen ? 'flex flex-1 flex-col overflow-hidden p-4 sm:p-6' : ''}`}>
      <div
        className={`min-h-48 border bg-muted/20 p-3 ${
          fullscreen
            ? 'flex min-h-0 flex-1 items-center justify-center overflow-auto rounded-xl'
            : 'rounded-lg'
        }`}
      >
        {preview.isLoading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="animate-spin" size={16} /> Đang tải preview...
          </p>
        ) : preview.data?.kind === 'image' ? (
          <img
            className={
              fullscreen ? 'max-h-full max-w-full object-contain' : 'max-h-[55dvh] max-w-full object-contain'
            }
            src={selected?.url}
            alt={selected?.name}
          />
        ) : preview.data?.kind === 'pdf' ? (
          <iframe
            className={
              fullscreen
                ? 'h-full min-h-[60dvh] w-full rounded border bg-white'
                : 'h-[52dvh] w-full rounded border bg-white'
            }
            src={selected?.url}
            title={selected ? `Preview ${selected.name}` : 'Preview file'}
          />
        ) : preview.data?.kind === 'text' ? (
          <pre
            className={
              fullscreen
                ? 'h-full w-full overflow-auto whitespace-pre-wrap text-xs leading-5'
                : 'max-h-[52dvh] overflow-auto whitespace-pre-wrap text-xs leading-5'
            }
          >
            {preview.data.content}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground">Định dạng này chưa preview trực tiếp được.</p>
        )}
      </div>
      {preview.data?.truncated ? (
        <p className="mt-2 text-xs text-muted-foreground">Preview đã được rút gọn.</p>
      ) : null}
    </div>
  );

  const startResize = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStart.current = { x: event.clientX, width: panelWidth };
    setIsResizing(true);
  };

  const resizePanel = (event: PointerEvent<HTMLDivElement>) => {
    if (!resizeStart.current) return;
    updatePanelWidth(resizeStart.current.width + resizeStart.current.x - event.clientX);
  };

  const finishResize = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    resizeStart.current = null;
    setIsResizing(false);
  };

  const body = (
    <>
      <div className="flex items-start justify-between gap-3 border-b px-4 py-3">
        <div>
          <h2 className="font-semibold">File AI tạo</h2>
          <p className="text-xs text-muted-foreground">Chọn một file để xem lại đúng nội dung đã tạo.</p>
        </div>
        <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)} aria-label="Đóng file AI tạo">
          <X size={18} />
        </Button>
      </div>
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(150px,0.8fr)_minmax(220px,1.2fr)]">
        <div className="min-h-0 overflow-y-auto border-b p-3">
          {generatedArtifacts.length ? (
            <div className="space-y-4">
              {groups.map((group) => (
                <section key={group.messageId}>
                  <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">
                    Phản hồi {group.createdAt ? formatDate(group.createdAt) : 'vừa tạo'}
                  </p>
                  <div className="space-y-2">
                    {group.artifacts.map((asset) => (
                      <button
                        key={asset.id}
                        type="button"
                        className={`w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted ${
                          selected?.id === asset.id ? 'border-primary bg-primary/5' : ''
                        }`}
                        onClick={() => selectArtifact(asset.id)}
                      >
                        <div className="flex items-start gap-2">
                          <FileText className="mt-0.5 shrink-0 text-muted-foreground" size={16} />
                          <span className="min-w-0 flex-1 truncate text-sm font-medium">{asset.name}</span>
                          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px]">
                            v{asset.version}
                          </span>
                        </div>
                        <p className="mt-1 truncate pl-6 text-xs text-muted-foreground">
                          {formatDate(asset.createdAt)} · {formatSize(asset.sizeBytes)}
                        </p>
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <p className="p-2 text-sm text-muted-foreground">Chat này chưa có file nào do AI tạo.</p>
          )}
        </div>
        <div className="min-h-0 overflow-auto p-4">
          {!selected ? (
            <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
              Chọn một file ở phía trên để xem nội dung.
            </div>
          ) : (
            <>
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate font-medium">{selected.name}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Tạo lúc {formatDate(selected.createdAt)} · version {selected.version}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setIsFullscreen(true)}
                  aria-label="Mở rộng xem nội dung"
                  title="Mở rộng xem nội dung"
                >
                  <Maximize2 size={16} />
                </Button>
              </div>
              {versions.data && versions.data.length > 1 ? (
                <div className="mb-3 flex flex-wrap gap-2" aria-label="Lịch sử phiên bản">
                  {versions.data.map((asset) => (
                    <Button
                      key={asset.id}
                      size="sm"
                      variant={asset.id === selected.id ? 'secondary' : 'outline'}
                      onClick={() => selectArtifact(asset.id)}
                    >
                      v{asset.version}
                    </Button>
                  ))}
                </div>
              ) : null}
              {renderPreview()}
              <a
                className="mt-3 inline-block text-sm text-primary hover:underline"
                href={selected.url}
                target="_blank"
                rel="noreferrer"
              >
                Mở hoặc tải file gốc
              </a>
            </>
          )}
        </div>
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
            <div
              className={`absolute inset-y-0 -left-1 z-10 hidden w-2 cursor-col-resize touch-none lg:block ${
                isResizing ? 'bg-primary/30' : 'hover:bg-primary/20'
              }`}
              role="separator"
              aria-label="Điều chỉnh độ rộng File AI tạo"
              aria-orientation="vertical"
              aria-valuemin={MIN_PANEL_WIDTH}
              aria-valuemax={MAX_PANEL_WIDTH}
              aria-valuenow={Math.round(panelWidth)}
              tabIndex={0}
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
          <div className="fixed inset-0 z-50 bg-black/50 p-3 lg:hidden" role="dialog" aria-modal="true">
            <aside className="ml-auto flex h-full w-full max-w-md flex-col rounded-2xl border bg-background shadow-2xl">
              {body}
            </aside>
          </div>
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
        <div
          className="fixed inset-0 z-[60] flex min-h-0 flex-col bg-background/95 backdrop-blur-sm"
          role="dialog"
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
          {renderPreview(true)}
        </div>
      ) : null}
    </>
  );
}
