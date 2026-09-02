import { useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Check,
  Copy,
  GitBranch,
  Globe,
  MoreHorizontal,
  RefreshCw,
  Share2,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { request } from '@/src/hooks/client';
import { queryKeys } from '@/src/hooks/query-keys';
import type { Message } from '@/src/types';
import { markdownToPlainText } from '@/lib/markdown-to-plain-text';
import { cn } from '@/lib/utils';

type Source = { name: string; url: string; kind?: 'library' | 'external' };
type FeedbackKind = 'helpful' | 'incorrect' | 'too_long' | 'too_short' | 'unclear' | 'wrong_style';
type FeedbackState = {
  feedbackOpen: boolean;
  setFeedbackOpen: (open: boolean) => void;
  feedbackKind: FeedbackKind;
  setFeedbackKind: (kind: FeedbackKind) => void;
  note: string;
  setNote: (note: string) => void;
  busy: boolean;
  feedbackError: string | null;
  openFeedback: () => void;
  submitFeedback: (kind?: FeedbackKind, note?: string) => Promise<void>;
};

function sourcesIn(content: string): Source[] {
  const seen = new Set<string>();
  const matches = [...content.matchAll(/\[([^\]]+)\]\((\/api\/documents\/[^)#]+(?:#[^)]+)?)\)/g)];
  return matches
    .map((match) => ({ name: match[1], url: match[2], kind: 'library' as const }))
    .filter((source) => (seen.has(source.url) ? false : (seen.add(source.url), true)));
}

function useMessageFeedback(chatId: string | undefined, message: Message): FeedbackState {
  const queryClient = useQueryClient();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackKind, setFeedbackKind] = useState<FeedbackKind>('unclear');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const submitFeedback = async (kind: FeedbackKind = feedbackKind, feedbackNote = note) => {
    if (!message.messageId) return;
    setBusy(true);
    setFeedbackError(null);
    try {
      const saved = await request<{ kind: FeedbackKind }>({
        url: `/messages/${message.messageId}/feedback`,
        method: 'POST',
        data: { kind, note: feedbackNote },
      });
      if (chatId) updateCachedFeedback(queryClient, chatId, message.messageId, saved.kind);
      setFeedbackOpen(false);
    } catch (reason) {
      setFeedbackError(reason instanceof Error ? reason.message : 'Không thể lưu đánh giá.');
    } finally {
      setBusy(false);
    }
  };
  const openFeedback = () => {
    setFeedbackError(null);
    setFeedbackOpen(true);
  };
  return {
    feedbackOpen,
    setFeedbackOpen,
    feedbackKind,
    setFeedbackKind,
    note,
    setNote,
    busy,
    feedbackError,
    openFeedback,
    submitFeedback,
  };
}

function updateCachedFeedback(
  queryClient: ReturnType<typeof useQueryClient>,
  chatId: string,
  messageId: string,
  kind: FeedbackKind,
) {
  queryClient.setQueryData<Message[]>(queryKeys.messages(chatId), (items = []) =>
    items.map((item) => (item.messageId === messageId ? { ...item, feedbackKind: kind } : item)),
  );
}

export function AssistantMessageActions({
  chatId,
  message,
  isLatest,
  onBranch,
  onRegenerate,
}: {
  chatId?: string;
  message: Message;
  isLatest: boolean;
  onBranch: (message: Message) => Promise<void>;
  onRegenerate: (message: Message) => Promise<void>;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const feedback = useMessageFeedback(chatId, message);
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const sources = useMemo(
    () => message.sources || sourcesIn(message.content),
    [message.content, message.sources],
  );
  const savedFeedbackKind = message.feedbackKind || null;
  const librarySources = sources.filter(
    (source) => source.kind === 'library' || (!source.kind && source.url.startsWith('/api/documents/')),
  );
  const externalSources = sources.filter(
    (source) => source.kind === 'external' || (!source.kind && source.url.startsWith('https://')),
  );

  const copy = async () => {
    await navigator.clipboard?.writeText(markdownToPlainText(message.content));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const share = async () => {
    if (navigator.share) {
      await navigator.share({ title: 'Phản hồi AI', text: message.content });
      return;
    }
    await copy();
  };
  const speak = () => {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    if (speaking) {
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(message.content);
    utterance.lang = 'vi-VN';
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };
  const isHelpful = savedFeedbackKind === 'helpful';
  const hasNegativeFeedback = Boolean(savedFeedbackKind && !isHelpful);
  const FeedbackIcon = hasNegativeFeedback ? ThumbsDown : ThumbsUp;

  return (
    <>
      <div className="mt-2 flex items-center gap-0.5">
        <Button
          size="icon-sm"
          variant="ghost"
          className="size-7 rounded-md"
          onClick={() => void copy()}
          aria-label="Sao chép phản hồi"
        >
          {copied ? <Check /> : <Copy />}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                size="icon-sm"
                variant="ghost"
                className={cn('size-7 rounded-md', savedFeedbackKind && 'text-primary hover:text-primary')}
                aria-label={
                  savedFeedbackKind
                    ? `Đã đánh giá: ${isHelpful ? 'trả lời tốt' : 'trả lời tệ'}`
                    : 'Đánh giá phản hồi'
                }
              />
            }
          >
            <span className="relative">
              <FeedbackIcon className={savedFeedbackKind ? 'fill-current' : undefined} />
              {savedFeedbackKind ? (
                <Check className="absolute -bottom-1.5 -right-2 size-2.5 rounded-full bg-background" />
              ) : null}
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" sideOffset={8} className="w-40">
            <DropdownMenuItem onClick={() => void feedback.submitFeedback('helpful', '')}>
              <ThumbsUp className={isHelpful ? 'fill-current text-primary' : undefined} />
              Trả lời tốt
              {isHelpful ? <Check className="ml-auto size-4" /> : null}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={feedback.openFeedback}>
              <ThumbsDown className={hasNegativeFeedback ? 'fill-current text-primary' : undefined} />
              Trả lời tệ
              {hasNegativeFeedback ? <Check className="ml-auto size-4" /> : null}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          size="icon-sm"
          variant="ghost"
          className="size-7 rounded-md"
          onClick={() => void share()}
          aria-label="Chia sẻ phản hồi"
        >
          <Share2 />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          className="size-7 rounded-md"
          disabled={!isLatest}
          onClick={() => void onRegenerate(message)}
          aria-label="Tạo lại phản hồi"
        >
          <RefreshCw />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                size="icon-sm"
                variant="ghost"
                className="size-7 rounded-md"
                aria-label="Thêm thao tác"
              />
            }
          >
            <MoreHorizontal />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="bottom" className="w-52">
            <DropdownMenuItem onClick={() => setSourcesOpen(true)}>
              <BookOpen /> Xem nguồn
            </DropdownMenuItem>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <GitBranch /> Mở nhánh mới
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem disabled={!message.messageId} onClick={() => void onBranch(message)}>
                  Từ lượt hỏi và phản hồi này
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuItem onClick={speak}>
              <Volume2 /> {speaking ? 'Dừng đọc' : 'Đọc to'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {feedback.feedbackError ? (
        <p className="mt-1 text-xs text-destructive">{feedback.feedbackError}</p>
      ) : null}
      {feedback.feedbackOpen ? (
        <Modal title="Phản hồi này cần cải thiện ở đâu?" onClose={() => feedback.setFeedbackOpen(false)}>
          <div className="grid gap-2">
            {[
              ['incorrect', 'Sai hoặc chưa chính xác'],
              ['too_long', 'Quá dài'],
              ['too_short', 'Quá ngắn'],
              ['unclear', 'Khó hiểu'],
              ['wrong_style', 'Sai định dạng hoặc phong cách'],
            ].map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name={message.messageId}
                  checked={feedback.feedbackKind === value}
                  onChange={() => feedback.setFeedbackKind(value as FeedbackKind)}
                />
                {label}
              </label>
            ))}
          </div>
          <textarea
            className="mt-4 min-h-24 w-full rounded-xl border bg-background p-3 text-sm"
            value={feedback.note}
            onChange={(event) => feedback.setNote(event.target.value)}
            placeholder="Ghi chú thêm để AI cải thiện cho các lần sau (tùy chọn)"
          />
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => feedback.setFeedbackOpen(false)}>
              Hủy
            </Button>
            <Button disabled={feedback.busy} onClick={() => void feedback.submitFeedback()}>
              {feedback.busy ? 'Đang lưu...' : 'Gửi đánh giá'}
            </Button>
          </div>
          {feedback.feedbackError ? (
            <p className="mt-3 text-sm text-destructive">{feedback.feedbackError}</p>
          ) : null}
        </Modal>
      ) : null}
      {sourcesOpen ? (
        <Modal title="Nguồn của phản hồi" onClose={() => setSourcesOpen(false)}>
          {sources.length ? (
            <div className="space-y-5">
              {librarySources.length ? (
                <SourceGroup icon={<BookOpen />} title="Từ Thư viện" sources={librarySources} />
              ) : null}
              {externalSources.length ? (
                <SourceGroup icon={<Globe />} title="Từ web" sources={externalSources} />
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Phản hồi này không có nguồn được trích dẫn.</p>
          )}
        </Modal>
      ) : null}
    </>
  );
}

function SourceGroup({ icon, title, sources }: { icon: ReactNode; title: string; sources: Source[] }) {
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
        {icon}
        {title}
      </h3>
      <ul className="space-y-2">
        {sources.map((source) => (
          <li key={source.url}>
            <a
              className="text-sm text-primary underline underline-offset-4"
              href={source.url}
              target="_blank"
              rel="noreferrer"
            >
              {source.name}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
    >
      <section className="w-full max-w-lg rounded-2xl border bg-card p-5 shadow-2xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="font-semibold">{title}</h2>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Đóng">
            <X />
          </Button>
        </div>
        {children}
      </section>
    </div>
  );
}
