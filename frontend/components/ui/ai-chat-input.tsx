import * as React from 'react';
import { ImagePlus, Mic, Paperclip, Send, Square, X } from 'lucide-react';

import { cn } from '@/lib/utils';

type Attachment = { id: string; file: File; url: string };
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
};

export function PromptInput({
  value,
  onChange,
  onSubmit,
  busy = false,
  placeholder = 'Hỏi bất kỳ điều gì...',
  className,
  maxAttachments = 6,
}: PromptInputProps) {
  const [attachments, setAttachments] = React.useState<Attachment[]>([]);
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
      (file) => file.type === 'application/pdf' || file.type.startsWith('image/'),
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
  const submit = () => {
    if (busy || (!value.trim() && !attachments.length)) return;
    onSubmit(
      value.trim(),
      attachments.map((item) => item.file),
    );
    attachments.forEach((item) => URL.revokeObjectURL(item.url));
    setAttachments([]);
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
    <div className={cn('w-full rounded-3xl border bg-card p-3 shadow-lg shadow-primary/5', className)}>
      <input
        ref={fileRef}
        className="hidden"
        type="file"
        accept="image/*,application/pdf"
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
                  PDF
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
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        disabled={busy || recording}
        className="min-h-28 w-full resize-none bg-transparent px-2 py-1 text-sm outline-none placeholder:text-muted-foreground"
      />
      <div className="flex items-center gap-1 pt-2">
        <button
          type="button"
          title="Đính kèm PDF hoặc ảnh"
          onClick={() => fileRef.current?.click()}
          className="rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <Paperclip size={18} />
        </button>
        <button
          type="button"
          title="Chọn ảnh"
          onClick={() => fileRef.current?.click()}
          className="rounded-full p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <ImagePlus size={18} />
        </button>
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
              : 'text-muted-foreground hover:bg-accent',
          )}
        >
          {recording ? <Square size={16} /> : <Mic size={18} />}
        </button>
        <button
          type="button"
          disabled={busy || (!value.trim() && !attachments.length)}
          onClick={submit}
          className="rounded-full bg-primary p-2 text-primary-foreground disabled:opacity-50"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
