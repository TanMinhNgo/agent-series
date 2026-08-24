import { Fragment, useRef, type RefObject } from 'react';
import { useGSAP } from '@gsap/react';
import { gsap } from 'gsap';
import { ScrollToPlugin } from 'gsap/ScrollToPlugin';
import { Bookmark, Copy, Sparkles } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { RichResponseLazy } from '@/src/components/rich-response-lazy';
import { AssistantMessageActions } from '@/src/components/assistant-message-actions';
import type { Message } from '@/src/types';

gsap.registerPlugin(useGSAP, ScrollToPlugin);

const TIME_SEPARATOR_GAP_MS = 5 * 60 * 60 * 1000;

function timestampOf(message?: Message) {
  if (!message?.createdAt) return null;
  const value = new Date(message.createdAt);
  return Number.isNaN(value.getTime()) ? null : value;
}

function formatTimeSeparator(timestamp: Date) {
  const time = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(timestamp);
  const today = new Date();
  if (timestamp.toDateString() === today.toDateString()) return `Hôm nay lúc ${time}`;
  return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'full', timeStyle: 'short' }).format(timestamp);
}

type Props = {
  chatId?: string;
  messages: Message[];
  status: string | null;
  error: string | null;
  userScrollRequest: number;
  isRunwayRequested: boolean;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  onRunwayRelease: () => void;
  onPin?: (message: Message) => void;
  onBranch?: (message: Message) => Promise<void>;
  onRegenerate?: (message: Message) => Promise<void>;
};

export function MessageList({
  chatId,
  messages,
  status,
  error,
  userScrollRequest,
  isRunwayRequested,
  scrollContainerRef,
  onRunwayRelease,
  onPin,
  onBranch,
  onRegenerate,
}: Props) {
  const latestUserMessageRef = useRef<HTMLElement | null>(null);
  const previousAssistantRef = useRef<HTMLElement | null>(null);
  const latestAssistantResponseRef = useRef<HTMLElement | null>(null);
  const pendingAssistantRef = useRef<HTMLElement | null>(null);
  const responseRunwayRef = useRef<HTMLDivElement | null>(null);
  const latestUserIndex = messages.reduce(
    (latestIndex, message, index) => (message.role === 'user' ? index : latestIndex),
    -1,
  );
  const previousAssistantIndex = messages.reduce(
    (latestIndex, message, index) =>
      index < latestUserIndex && message.role === 'assistant' ? index : latestIndex,
    -1,
  );
  const latestAssistantResponseIndex = messages.reduce(
    (latestIndex, message, index) =>
      index > latestUserIndex && message.role === 'assistant' ? index : latestIndex,
    -1,
  );

  // The runway survives the loading state and the completed assistant message.
  // It is released only after an intentional upward user scroll, so the new
  // exchange stays anchored in the reading position established on send.
  useGSAP(
    () => {
      const runway = responseRunwayRef.current;
      const scrollContainer = scrollContainerRef.current;
      if (!isRunwayRequested || !runway || !scrollContainer) return;

      let scrollTween: gsap.core.Tween | undefined;
      let secondFrame: number | undefined;
      let thirdFrame: number | undefined;
      let releaseFrame: number | undefined;
      let touchStartY: number | undefined;

      const releaseRunway = () => {
        if (releaseFrame !== undefined) cancelAnimationFrame(releaseFrame);
        releaseFrame = requestAnimationFrame(() => {
          const currentHeight = runway.offsetHeight;
          if (currentHeight <= 1) {
            onRunwayRelease();
            return;
          }

          // Only collapse the portion that now sits below the viewport. This
          // prevents a manual upward scroll from being followed by a jump.
          const roomBelowViewport = Math.max(
            0,
            scrollContainer.scrollHeight - scrollContainer.clientHeight - scrollContainer.scrollTop,
          );
          const releasedHeight = Math.min(currentHeight, roomBelowViewport);
          if (releasedHeight <= 1) return;

          const nextHeight = currentHeight - releasedHeight;
          if (nextHeight <= 1) onRunwayRelease();
          else runway.style.height = `${Math.round(nextHeight)}px`;
        });
      };

      const onWheel = (event: WheelEvent) => {
        if (event.deltaY < -2) releaseRunway();
      };
      const onTouchStart = (event: TouchEvent) => {
        touchStartY = event.touches[0]?.clientY;
      };
      const onTouchMove = (event: TouchEvent) => {
        const nextY = event.touches[0]?.clientY;
        if (touchStartY !== undefined && nextY !== undefined && nextY - touchStartY > 4) releaseRunway();
        touchStartY = nextY;
      };

      scrollContainer.addEventListener('wheel', onWheel, { passive: true });
      scrollContainer.addEventListener('touchstart', onTouchStart, { passive: true });
      scrollContainer.addEventListener('touchmove', onTouchMove, { passive: true });

      const animateAfterLayout = () => {
        // Keep the response area in view: first the pending "thinking" state,
        // then the new assistant reply, and only then the outgoing user turn.
        // Preferring the previous assistant reply makes long replies pull the
        // viewport back up when the user sends the next message.
        const target =
          pendingAssistantRef.current ||
          latestAssistantResponseRef.current ||
          latestUserMessageRef.current ||
          previousAssistantRef.current;
        if (!target) return;

        // First measure without the runway. This guarantees that short chats
        // never gain an artificial scrollbar or a large empty region.
        runway.style.removeProperty('height');
        const baseMaxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;
        if (baseMaxScroll > 1) {
          runway.style.height = `${Math.round(scrollContainer.clientHeight * 0.45)}px`;
        }

        thirdFrame = requestAnimationFrame(() => {
          const maxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;
          if (maxScroll <= 1) return;

          const targetBounds = target.getBoundingClientRect();
          const containerBounds = scrollContainer.getBoundingClientRect();
          const targetY = Math.min(
            Math.max(
              0,
              scrollContainer.scrollTop +
                targetBounds.top -
                containerBounds.top -
                scrollContainer.clientHeight * (target === latestUserMessageRef.current ? 0.32 : 0.2),
            ),
            maxScroll,
          );
          if (Math.abs(targetY - scrollContainer.scrollTop) < 4) return;

          const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          scrollTween = gsap.to(scrollContainer, {
            duration: reduceMotion ? 0 : 0.58,
            ease: 'power3.out',
            overwrite: 'auto',
            scrollTo: { y: targetY, autoKill: true },
          });
        });
      };

      const firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(animateAfterLayout);
      });
      return () => {
        cancelAnimationFrame(firstFrame);
        if (secondFrame !== undefined) cancelAnimationFrame(secondFrame);
        if (thirdFrame !== undefined) cancelAnimationFrame(thirdFrame);
        if (releaseFrame !== undefined) cancelAnimationFrame(releaseFrame);
        scrollTween?.kill();
        scrollContainer.removeEventListener('wheel', onWheel);
        scrollContainer.removeEventListener('touchstart', onTouchStart);
        scrollContainer.removeEventListener('touchmove', onTouchMove);
      };
    },
    {
      dependencies: [userScrollRequest, status, messages.length, isRunwayRequested],
      scope: scrollContainerRef,
      revertOnUpdate: true,
    },
  );

  return (
    <div className="flex min-h-full flex-col space-y-6 py-5">
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
      {messages.map((message, index) => {
        const timestamp = timestampOf(message);
        const previousTimestamp = timestampOf(messages[index - 1]);
        const showTimeSeparator = Boolean(
          timestamp &&
          (!previousTimestamp || timestamp.getTime() - previousTimestamp.getTime() >= TIME_SEPARATOR_GAP_MS),
        );

        return (
          <Fragment key={message.messageId || `${message.role}-${index}`}>
            {showTimeSeparator && timestamp ? (
              <div className="flex items-center gap-3 py-1 text-xs text-muted-foreground" role="separator">
                <span className="h-px flex-1 bg-border" />
                <time dateTime={timestamp.toISOString()}>{formatTimeSeparator(timestamp)}</time>
                <span className="h-px flex-1 bg-border" />
              </div>
            ) : null}
            <article
              id={message.messageId ? `message-${message.messageId}` : undefined}
              ref={
                index === latestAssistantResponseIndex
                  ? latestAssistantResponseRef
                  : index === previousAssistantIndex
                    ? previousAssistantRef
                    : index === latestUserIndex
                      ? latestUserMessageRef
                      : undefined
              }
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
                    <div
                      className={cn('mt-3 flex flex-wrap gap-2', message.role === 'user' && 'justify-end')}
                    >
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
                {message.messageId && message.role === 'assistant' && onBranch && onRegenerate ? (
                  <AssistantMessageActions
                    chatId={chatId}
                    message={message}
                    isLatest={index === latestAssistantResponseIndex}
                    onBranch={onBranch}
                    onRegenerate={onRegenerate}
                  />
                ) : null}
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
          </Fragment>
        );
      })}
      {status && (
        <article ref={pendingAssistantRef} className="flex min-h-0 flex-1 gap-3 leading-7">
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
      {isRunwayRequested && <div ref={responseRunwayRef} aria-hidden="true" className="shrink-0" />}
      {error && (
        <Card size="sm" className="border border-destructive/30 bg-destructive/10">
          <CardContent className="text-sm text-destructive">{error}</CardContent>
        </Card>
      )}
    </div>
  );
}
