import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AtSign, Check, Copy, Link, LoaderCircle, MessageCircle, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { request } from '@/src/hooks/client';
import { RichResponse } from '@/src/components/rich-response';
import type { Chat, Message, PublicShare } from '@/src/types';

type Props = { chat: Chat; onClose: () => void };

export function ChatShareDialog({ chat, onClose }: Props) {
  const [share, setShare] = useState<PublicShare | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    void request<Message[]>({ url: `/chats/${chat.id}/messages` })
      .then(setMessages)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [chat.id]);
  const url = share ? `${window.location.origin}/share/${share.token}` : '';
  const publish = async () => {
    setLoading(true);
    setError(null);
    try {
      setShare(await request<PublicShare>({ url: `/chats/${chat.id}/share`, method: 'POST' }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể tạo liên kết chia sẻ.');
    } finally {
      setLoading(false);
    }
  };
  const copy = async () => {
    await navigator.clipboard?.writeText(url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  const preview = useMemo(() => (share?.messages || messages).slice(-4), [messages, share]);
  const social = (site: 'x' | 'linkedin' | 'reddit') => {
    if (!url) return;
    const text = encodeURIComponent(chat.title);
    const encodedUrl = encodeURIComponent(url);
    const href =
      site === 'x'
        ? `https://x.com/intent/post?text=${text}&url=${encodedUrl}`
        : site === 'linkedin'
          ? `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`
          : `https://www.reddit.com/submit?url=${encodedUrl}&title=${text}`;
    window.open(href, '_blank', 'noopener,noreferrer');
  };
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="share-title"
    >
      <section className="w-full max-w-[min(66.666vw,1100px)] rounded-3xl border bg-card p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4 border-b pb-4">
          <div>
            <h2 id="share-title" className="text-xl font-semibold sm:text-2xl">
              {chat.title}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">Chia sẻ bản chỉ-đọc của cuộc trò chuyện này.</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
            <X />
          </Button>
        </div>
        <div className="my-4 max-h-64 overflow-y-auto rounded-2xl border bg-background p-4 text-sm">
          <div className="space-y-3">
            {loading && !preview.length ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <LoaderCircle className="animate-spin" size={16} /> Đang tải bản xem trước...
              </div>
            ) : (
              preview.map((message, index) => (
                <div
                  key={index}
                  className={
                    message.role === 'user'
                      ? 'ml-auto max-w-[85%] rounded-xl bg-primary px-3 py-2 text-primary-foreground'
                      : 'max-w-[92%]'
                  }
                >
                  {message.role === 'assistant' ? (
                    <RichResponse content={message.content} blocks={message.contentBlocks} />
                  ) : (
                    message.content
                  )}
                </div>
              ))
            )}
          </div>
        </div>
        {error ? <p className="mb-3 text-sm text-destructive">{error}</p> : null}
        {!share ? (
          <Button className="w-full" disabled={loading} onClick={() => void publish()}>
            {loading ? <LoaderCircle className="animate-spin" /> : <Link />} Tạo liên kết chia sẻ
          </Button>
        ) : (
          <>
            <div className="flex gap-2">
              <input
                className="min-w-0 flex-1 rounded-xl border bg-background px-3 text-sm"
                readOnly
                value={url}
                aria-label="Liên kết công khai"
              />
              <Button onClick={() => void copy()}>
                {copied ? <Check /> : <Copy />}
                {copied ? 'Đã sao chép' : 'Sao chép link'}
              </Button>
            </div>
            <div className="mt-5 flex justify-center gap-4">
              <ShareButton label="X" icon={<X size={18} />} onClick={() => social('x')} />
              <ShareButton
                label="LinkedIn"
                icon={<AtSign size={18} />}
                onClick={() => social('linkedin')}
              />
              <ShareButton label="Reddit" icon={<MessageCircle size={18} />} onClick={() => social('reddit')} />
            </div>
            <p className="mt-4 text-center text-xs text-muted-foreground">
              Tệp đính kèm, kết quả tool và dữ liệu knowledge base không được chia sẻ.
            </p>
          </>
        )}
      </section>
    </div>
  );
}

function ShareButton({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="grid place-items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
    >
      <span className="grid size-11 place-items-center rounded-full bg-background text-foreground">
        {icon}
      </span>
      {label}
    </button>
  );
}
