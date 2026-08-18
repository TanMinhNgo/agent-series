import { PromptInput } from '@/components/ui/ai-chat-input';

type Props = {
  prompt: string;
  busy: boolean;
  onPromptChange: (value: string) => void;
  onSubmit: (content: string, files: File[]) => void;
  templates?: { id: string; name: string; content: string; projectId: string | null }[];
  onSelectTemplate?: (content: string) => void;
  onSaveTemplate?: (name: string, content: string) => void;
  onEditTemplate?: (template: {
    id: string;
    name: string;
    content: string;
    projectId: string | null;
  }) => void;
  onDeleteTemplate?: (id: string) => void;
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
}: Props) {
  return (
    <div className="sticky bottom-0 mt-6 bg-background/95 pb-4 pt-4 backdrop-blur">
      {templates.length ? (
        <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
          {templates.map((template) => (
            <span key={template.id} className="flex shrink-0 overflow-hidden rounded-full border text-xs">
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
          onClick={() => {
            const name = window.prompt('Tên template');
            if (name?.trim()) onSaveTemplate?.(name.trim(), prompt);
          }}
        >
          Lưu prompt thành template
        </button>
      ) : null}
      <PromptInput
        value={prompt}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        busy={busy}
        placeholder="Hỏi về tài liệu, ảnh hoặc một vấn đề bất kỳ..."
      />
    </div>
  );
}
