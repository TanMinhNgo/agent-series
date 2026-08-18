import { useLayoutEffect, useRef } from 'react';
import { Bookmark, Copy, Sparkles } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { RichResponseLazy } from '@/src/components/rich-response-lazy';
import type { Message } from '@/src/types';

type Props = {
  messages: Message[];
  status: string | null;
  error: string | null;
  userScrollRequest: number;
  onPin?: (message: Message) => void;
};

export function MessageList({ messages, status, error, userScrollRequest, onPin }: Props) {
  const latestUserMessageRef = useRef<HTMLElement | null>(null);

  // This intentionally reacts only to a newly queued user message. AI status,
  // tool events and completed assistant responses must not take over the scroll.
  useLayoutEffect(() => {
    if (!userScrollRequest) return;
    latestUserMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [userScrollRequest]);

  return (
    <div className="flex flex-1 flex-col space-y-6">
      {!messages.length && !error && !status && (
        <div className="flex flex-1 items-center justify-center text-center">
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
          id={message.messageId ? `message-${message.messageId}` : undefined}
          key={message.messageId || `${message.role}-${index}`}
          ref={message.role === 'user' && index === messages.length - 1 ? latestUserMessageRef : undefined}
          className={cn('group flex gap-3 leading-7', message.role === 'user' && 'flex-row-reverse')}
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
              message.role === 'user' ? 'flex flex-col items-end' : 'pt-0.5',
            )}
          >
            <div
              className={cn(
                message.role === 'user' && 'rounded-2xl bg-primary px-4 py-2 text-primary-foreground',
              )}
            >
              {message.role === 'assistant' ? (
                <RichResponseLazy content={message.content} blocks={message.contentBlocks} />
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
            {message.messageId && message.role === 'user' ? (
              <div className="mt-1 flex justify-end gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className="size-7 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                        onClick={() => void navigator.clipboard.writeText(message.content)}
                        aria-label="Sao chép đoạn chat"
                      />
                    }
                  >
                    <Copy />
                  </TooltipTrigger>
                  <TooltipContent side="bottom" sideOffset={6}>
                    Sao chép đoạn chat
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        className={cn(
                          'size-7 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground',
                          message.pinned && 'bg-muted text-foreground',
                        )}
                        onClick={() => onPin?.(message)}
                        aria-label={message.pinned ? 'Bỏ ghim đoạn chat' : 'Ghim đoạn chat'}
                      />
                    }
                  >
                    <Bookmark />
                  </TooltipTrigger>
                  <TooltipContent side="bottom" sideOffset={6}>
                    {message.pinned ? 'Bỏ ghim đoạn chat' : 'Ghim đoạn chat'}
                  </TooltipContent>
                </Tooltip>
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
