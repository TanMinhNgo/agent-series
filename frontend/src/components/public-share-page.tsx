import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';

import { request } from '@/src/hooks/client';
import { RichResponse } from '@/src/components/rich-response';
import type { PublicShare } from '@/src/types';

export function PublicSharePage({ token }: { token: string }) {
  const [share, setShare] = useState<PublicShare | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void request<PublicShare>({ url: `/public/shares/${token}` })
      .then(setShare)
      .catch((reason: Error) => setError(reason.message));
  }, [token]);
  if (error)
    return (
      <main className="grid min-h-screen place-items-center bg-background p-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold">Liên kết không khả dụng</h1>
          <p className="mt-2 text-muted-foreground">{error}</p>
        </div>
      </main>
    );
  if (!share)
    return (
      <main className="grid min-h-screen place-items-center bg-background text-muted-foreground">
        Đang tải cuộc trò chuyện...
      </main>
    );
  return (
    <main className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-5 py-4">
          <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground">
            <Sparkles size={16} />
          </span>
          <div>
            <p className="font-semibold">Local Agent</p>
            <p className="text-xs text-muted-foreground">
              Chia sẻ bởi người dùng · {share.provider} / {share.model}
            </p>
          </div>
        </div>
      </header>
      <article className="mx-auto max-w-3xl space-y-7 px-5 py-8">
        <h1 className="text-2xl font-semibold sm:text-3xl">{share.title}</h1>
        {share.messages.map((message, index) => (
          <section
            key={index}
            className={
              message.role === 'user'
                ? 'ml-auto max-w-[85%] rounded-2xl bg-primary px-4 py-2 text-primary-foreground'
                : 'max-w-full'
            }
          >
            {message.role === 'assistant' ? (
              <RichResponse content={message.content} blocks={message.contentBlocks} />
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )}
          </section>
        ))}
      </article>
    </main>
  );
}
