import { Brain, FilePenLine, ImageIcon, ListChecks, Search, Sparkles, X } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { PromptInput } from '@/components/ui/ai-chat-input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
  const modeOptions = [
    { value: 'standard', label: 'Thường', description: 'Trả lời cân bằng', icon: Sparkles },
    { value: 'plan', label: 'Lập kế hoạch', description: 'Chỉ lập kế hoạch', icon: ListChecks },
    { value: 'deep', label: 'Suy nghĩ sâu', description: 'Phân tích kỹ hơn', icon: Brain },
    { value: 'research', label: 'Nghiên cứu', description: 'Ưu tiên nguồn kiểm chứng', icon: Search },
    { value: 'image', label: 'Tạo ảnh', description: 'Tạo hoặc chỉnh sửa ảnh', icon: ImageIcon },
  ] as const;
  const selectedMode = modeOptions.find((item) => item.value === mode) ?? modeOptions[0];

  useEffect(() => {
    if (editingArtifact) composerRef.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
  }, [editingArtifact]);

  return (
    <div ref={composerRef} className="shrink-0 bg-background/95 pt-3 pb-4 backdrop-blur sm:pb-5">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">Chế độ</span>
        <Select value={mode} disabled={busy} onValueChange={(value) => onModeChange(value as typeof mode)}>
          <SelectTrigger id="chat-mode" className="h-9 w-auto min-w-36 gap-2 rounded-full border-border/80 bg-background px-3 text-xs shadow-sm hover:bg-muted/60">
            <selectedMode.icon className="size-3.5 text-primary" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent side="right" align="start" sideOffset={8} alignItemWithTrigger={false} className="w-64 rounded-xl p-1.5">
            {modeOptions.map((item) => {
              const Icon = item.icon;
              return (
                <SelectItem key={item.value} value={item.value} className="rounded-lg py-2.5 pl-9 pr-2">
                  <span className="flex items-center gap-2">
                    <Icon className="size-4 text-primary" />
                    <span className="flex flex-col text-left">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className="text-[11px] text-muted-foreground">{item.description}</span>
                    </span>
                  </span>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {mode === 'plan' || mode === 'research' ? (
          <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border border-border/80 bg-background px-3 text-xs text-muted-foreground shadow-sm transition-colors hover:bg-muted/60 has-[:checked]:border-primary/40 has-[:checked]:bg-primary/5 has-[:checked]:text-foreground">
            <input
              className="size-3.5 accent-primary"
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
