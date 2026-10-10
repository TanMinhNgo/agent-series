import * as React from 'react';
import { FileText, ImagePlus, Mic, Paperclip, Send, Square, X } from 'lucide-react';

import { cn } from '@/lib/utils';

type Attachment = { id: string; file: File; url: string };
const PASTE_CHIP_MIN_CHARS = 1500;
export const MAX_MESSAGE_CHARS = 100_000;
type Pasted = { id: string; text: string };
const isKnowledgeFile = (file: File) => /\.(pdf|docx|md)$/i.test(file.name);
type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult:
    ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>>; resultIndex: number }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

export type PromptInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string, files: File[]) => void;
  busy?: boolean;
  placeholder?: string;
  className?: string;
  maxAttachments?: number;
  onStop?: () => void;
  clearAttachmentsOnSubmit?: boolean;
};

export function PromptInput({
  value,
  onChange,
  onSubmit,
  busy = false,
  placeholder = 'Hỏi bất kỳ điều gì...',
  className,
  maxAttachments = 6,
  onStop,
  clearAttachmentsOnSubmit = true,
}: PromptInputProps) {
  const [attachments, setAttachments] = React.useState<Attachment[]>([]);
  const [pasted, setPasted] = React.useState<Pasted[]>([]);
  const [recording, setRecording] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const recognition = React.useRef<SpeechRecognitionLike | null>(null);

  React.useEffect(() => () => attachments.forEach((item) => URL.revokeObjectURL(item.url)), [attachments]);
  const stopVoice = () => {
    recognition.current?.stop();
    recognition.current = null;
    setRecording(false);
  };
  React.useEffect(() => () => stopVoice(), []);

  const chooseFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incoming = Array.from(event.target.files || []).filter(
      (file) => isKnowledgeFile(file) || file.type.startsWith('image/'),
    );
    event.target.value = '';
    setAttachments((current) => [
      ...current,
      ...incoming
        .slice(0, maxAttachments - current.length)
        .map((file) => ({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file) })),
    ]);
  };
  const remove = (id: string) =>
    setAttachments((current) => {
      const item = current.find((attachment) => attachment.id === id);
      if (item) URL.revokeObjectURL(item.url);
      return current.filter((attachment) => attachment.id !== id);
    });
  const pastedText = pasted.map((item) => item.text).join('\n\n');
  const fullContent = [value.trim(), pastedText].filter(Boolean).join('\n\n');
  const tooLong = fullContent.length > MAX_MESSAGE_CHARS;
  const hasContent = Boolean(fullContent) || attachments.length > 0;
  const submit = () => {
    if (busy || tooLong || !hasContent) return;
    onSubmit(
      fullContent,
      attachments.map((item) => item.file),
    );
    setPasted([]);
    if (clearAttachmentsOnSubmit) setAttachments([]);
  };
  const startVoice = () => {
    const ctor =
      (
        window as unknown as {
          SpeechRecognition?: SpeechRecognitionConstructor;
          webkitSpeechRecognition?: SpeechRecognitionConstructor;
        }
      ).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionConstructor })
        .webkitSpeechRecognition;
    if (!ctor) return;
    const instance = new ctor();
    instance.continuous = true;
    instance.interimResults = true;
    const baseline = value;
    instance.onresult = (event) => {
      let transcript = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1)
        transcript += event.results[index][0].transcript;
      onChange(`${baseline}${baseline && transcript ? ' ' : ''}${transcript}`);
    };
    instance.onend = () => setRecording(false);
    instance.onerror = () => setRecording(false);
    recognition.current = instance;
    instance.start();
    setRecording(true);
  };

  return (
    <div
      className={cn(
        'w-full rounded-2xl border border-border/90 bg-card/80 p-2.5 shadow-[0_12px_32px_-20px_color-mix(in_srgb,var(--foreground)_35%,transparent)] transition-shadow focus-within:border-primary/45 focus-within:shadow-[0_14px_36px_-20px_color-mix(in_srgb,var(--primary)_60%,transparent)]',
        className,
      )}
    >
      <input
        ref={fileRef}
        className="hidden"
        type="file"
        accept="image/*,.pdf,.docx,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown"
        multiple
        onChange={chooseFiles}
      />
      {attachments.length > 0 && (
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {attachments.map((item) => (
            <div key={item.id} className="relative shrink-0 overflow-hidden rounded-xl border bg-muted">
              {item.file.type.startsWith('image/') ? (
                <img src={item.url} alt={item.file.name} className="size-14 object-cover" />
              ) : (
                <div className="flex size-14 items-center justify-center text-[10px] font-bold text-muted-foreground">
                  {item.file.name.split('.').pop()?.toUpperCase() || 'FILE'}
                </div>
              )}
              <button
                type="button"
                onClick={() => remove(item.id)}
                className="absolute right-1 top-1 rounded-full bg-background p-0.5"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {pasted.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {pasted.map((item) => (
            <div
              key={item.id}
              className="flex max-w-64 items-center gap-2 rounded-xl border bg-muted px-2.5 py-1.5 text-xs"
              title={item.text.slice(0, 500)}
            >
              <FileText size={14} className="shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">Nội dung đã dán</span>
                <span className="block truncate text-muted-foreground">
                  {item.text.length.toLocaleString('vi-VN')} ký tự · {item.text.trim().slice(0, 40)}
                </span>
              </span>
              <button
                type="button"
                aria-label="Xóa nội dung đã dán"
                onClick={() => setPasted((current) => current.filter((entry) => entry.id !== item.id))}
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      <textarea
        value={value}
        onPaste={(event) => {
          const text = event.clipboardData.getData('text/plain');
          if (text.length < PASTE_CHIP_MIN_CHARS) return;
          event.preventDefault();
          setPasted((current) => [...current, { id: crypto.randomUUID(), text }]);
        }}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        disabled={busy || recording}
        className="min-h-24 w-full resize-none bg-transparent px-2.5 py-1.5 text-sm leading-6 outline-none placeholder:text-muted-foreground"
      />
      <div className="flex items-center gap-1 border-t border-border/60 pt-2">
        <button
          type="button"
          title="Đính kèm PDF, DOCX, Markdown hoặc ảnh"
          onClick={() => fileRef.current?.click()}
          className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Paperclip size={18} />
        </button>
        <button
          type="button"
          title="Chọn ảnh"
          onClick={() => fileRef.current?.click()}
          className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <ImagePlus size={18} />
        </button>
        {tooLong && (
          <span className="text-xs text-destructive">
            Quá dài: {fullContent.length.toLocaleString('vi-VN')}/{MAX_MESSAGE_CHARS.toLocaleString('vi-VN')} ký tự
          </span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {attachments.length}/{maxAttachments}
        </span>
        <button
          type="button"
          title={recording ? 'Dừng ghi âm' : 'Nhập giọng nói'}
          onClick={recording ? stopVoice : startVoice}
          className={cn(
            'rounded-full p-2',
            recording
              ? 'bg-destructive text-destructive-foreground'
              : 'rounded-lg text-muted-foreground hover:bg-muted',
          )}
        >
          {recording ? <Square size={16} /> : <Mic size={18} />}
        </button>
        <button
          type="button"
          disabled={busy ? !onStop : tooLong || !hasContent}
          onClick={busy ? onStop : submit}
          title={busy ? 'Dừng tạo phản hồi' : 'Gửi tin nhắn'}
          className="rounded-lg bg-primary p-2 text-primary-foreground shadow-sm shadow-primary/20 disabled:opacity-50"
        >
          {busy ? <Square size={16} /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}
