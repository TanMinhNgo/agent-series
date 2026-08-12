import { useLayoutEffect, useRef } from 'react';
import { Sparkles } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { RichResponse } from '@/src/components/rich-response';
import type { Message } from '@/src/types';

type Props = { messages: Message[]; status: string | null; error: string | null; userScrollRequest: number };

export function MessageList({ messages, status, error, userScrollRequest }: Props) {
  const latestUserMessageRef = useRef<HTMLElement | null>(null);

  // This intentionally reacts only to a newly queued user message. AI status,
  // tool events and completed assistant responses must not take over the scroll.
  useLayoutEffect(() => {
    if (!userScrollRequest) return;
    latestUserMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [userScrollRequest]);

  return (
    <div className="flex-1 space-y-6">
      {!messages.length && !error && (
        <div className="grid min-h-72 place-items-center text-center">
          <div>
            <h2 className="font-display text-4xl leading-none">Bạn muốn làm gì hôm nay?</h2>
            <p className="mt-3 text-muted-foreground">
              Hỏi về tài liệu đã index, phân tích một vấn đề hoặc bắt đầu ý tưởng mới.
            </p>
          </div>
        </div>
      )}
      {messages.map((message, index) => (
        <article
          key={`${message.role}-${index}`}
          ref={message.role === 'user' && index === messages.length - 1 ? latestUserMessageRef : undefined}
          className={cn('flex gap-3 leading-7', message.role === 'user' && 'flex-row-reverse')}
        >
          <span
            className={cn(
              'grid size-8 shrink-0 place-items-center rounded-lg text-xs font-semibold',
              message.role === 'assistant' ? 'bg-primary text-primary-foreground' : 'bg-muted',
            )}
          >
            {message.role === 'user' ? 'Bạn' : <Sparkles size={15} />}
          </span>
          <div
            className={cn(
              'min-w-0 max-w-[85%]',
              message.role === 'user' ? 'rounded-2xl bg-primary px-4 py-2 text-primary-foreground' : 'pt-0.5',
            )}
          >
            {message.role === 'assistant' ? (
              <RichResponse content={message.content} blocks={message.contentBlocks} />
            ) : (
              <p className="m-0 whitespace-pre-wrap text-[.95rem]">{message.content}</p>
            )}
            {message.attachments?.length ? (
              <div className={cn('mt-3 flex flex-wrap gap-2', message.role === 'user' && 'justify-end')}>
                {message.attachments.map((item) => (
                  <a
                    key={item.id}
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="overflow-hidden rounded-lg border border-white/30 bg-muted"
                  >
                    <img src={item.url} alt={item.name} className="size-20 object-cover" />
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        </article>
      ))}
      {status && (
        <article className="flex gap-3 leading-7">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles size={15} />
          </span>
          <div className="rounded-2xl bg-muted/60 px-4 py-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5" aria-label="AI đang soạn phản hồi" role="status">
              <span>Đang suy nghĩ</span>
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
                  style={{ animationDelay: `${dot * 140}ms` }}
                />
              ))}
            </div>
            {status !== 'Agent đang suy nghĩ...' && <p className="mt-1 text-xs opacity-75">{status}</p>}
          </div>
        </article>
      )}
      {error && (
        <Card size="sm" className="border border-destructive/30 bg-destructive/10">
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      )}
    </div>
  );
}
