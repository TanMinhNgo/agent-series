import { FilePenLine, X } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { PromptInput } from '@/components/ui/ai-chat-input';
import type { LibraryAsset } from '@/src/types';

type Props = {
  prompt: string;
  busy: boolean;
  onPromptChange: (value: string) => void;
  onSubmit: (content: string, files: File[]) => void;
  templates?: { id: string; name: string; content: string; projectId: string | null }[];
  onSelectTemplate?: (content: string) => void;
  onSaveTemplate?: (content: string) => void;
  onEditTemplate?: (template: {
    id: string;
    name: string;
    content: string;
    projectId: string | null;
  }) => void;
  onDeleteTemplate?: (id: string) => void;
  editingArtifact?: LibraryAsset | null;
  onCancelArtifactEdit?: () => void;
  onStop?: () => void;
  mode: 'standard' | 'plan' | 'deep' | 'research' | 'image';
  onModeChange: (mode: 'standard' | 'plan' | 'deep' | 'research' | 'image') => void;
  researchWeb: boolean;
  onResearchWebChange: (value: boolean) => void;
};

export function ChatComposer({
  prompt,
  busy,
  onPromptChange,
  onSubmit,
  templates = [],
  onSelectTemplate,
  onSaveTemplate,
  onEditTemplate,
  onDeleteTemplate,
  editingArtifact,
  onCancelArtifactEdit,
  onStop,
  mode,
  onModeChange,
  researchWeb,
  onResearchWebChange,
}: Props) {
  const composerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editingArtifact) composerRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
  }, [editingArtifact]);

  return (
    <div ref={composerRef} className="shrink-0 bg-background/95 pt-3 pb-4 backdrop-blur sm:pb-5">
      <div className="mb-2 flex items-center gap-2 text-xs">
        <label className="text-muted-foreground" htmlFor="chat-mode">
          Chế độ
        </label>
        <select
          id="chat-mode"
          value={mode}
          disabled={busy}
          onChange={(event) => onModeChange(event.target.value as typeof mode)}
          className="h-7 rounded-md border bg-background px-2"
        >
          <option value="standard">Thường</option>
          <option value="plan">Lập kế hoạch</option>
          <option value="deep">Suy nghĩ sâu</option>
          <option value="research">Nghiên cứu</option>
          <option value="image">Tạo ảnh</option>
        </select>
        {mode === 'plan' || mode === 'research' ? (
          <label className="flex items-center gap-1 text-muted-foreground">
            <input
              type="checkbox"
              checked={researchWeb}
              disabled={busy}
              onChange={(event) => onResearchWebChange(event.target.checked)}
            />
            Tìm web cho tin nhắn này
          </label>
        ) : null}
      </div>
      {templates.length ? (
        <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
          {templates.map((template) => (
            <span key={template.id} className="flex shrink-0 overflow-hidden rounded-lg bg-muted/70 text-xs">
              <button
                type="button"
                className="px-3 py-1 hover:bg-muted"
                onClick={() => onSelectTemplate?.(template.content)}
              >
                {template.name}
              </button>
              <button
                type="button"
                className="border-l px-2 hover:bg-muted"
                onClick={() => onEditTemplate?.(template)}
              >
                ✎
              </button>
              <button
                type="button"
                className="border-l px-2 text-destructive hover:bg-muted"
                onClick={() => onDeleteTemplate?.(template.id)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {prompt.trim() ? (
        <button
          type="button"
          className="mb-2 text-xs text-muted-foreground hover:underline"
          onClick={() => onSaveTemplate?.(prompt)}
        >
          Lưu prompt thành template
        </button>
      ) : null}
      {editingArtifact ? (
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-xs">
          <FilePenLine size={15} className="shrink-0 text-primary" />
          <span className="min-w-0 flex-1 truncate">
            Đang sửa: <span className="font-medium">{editingArtifact.name}</span> · v{editingArtifact.version}
          </span>
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
            onClick={onCancelArtifactEdit}
            aria-label="Hủy sửa file này"
            title="Hủy sửa file này"
          >
            <X size={15} />
          </button>
        </div>
      ) : null}
      <PromptInput
        value={prompt}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        busy={busy}
        onStop={onStop}
        placeholder={
          editingArtifact
            ? 'Mô tả thay đổi bạn muốn áp dụng cho file này...'
            : 'Hỏi về tài liệu, ảnh hoặc một vấn đề bất kỳ...'
        }
      />
    </div>
  );
}
