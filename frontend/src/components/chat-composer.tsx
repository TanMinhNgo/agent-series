import { PromptInput } from '@/components/ui/ai-chat-input';

type Props = {
  prompt: string;
  busy: boolean;
  onPromptChange: (value: string) => void;
  onSubmit: (content: string, files: File[]) => void;
};

export function ChatComposer({ prompt, busy, onPromptChange, onSubmit }: Props) {
  return (
    <div className="sticky bottom-0 mt-6 bg-background/95 pb-4 pt-4 backdrop-blur">
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
