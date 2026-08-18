import { useEffect, useState, type ChangeEvent } from 'react';
import { Menu, Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import type { Chat, Config } from '@/src/types';

type Props = {
  chat: Chat | null;
  config: Config | null;
  busy?: boolean;
  onOpenSidebar?: () => void;
  onProviderChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  onModelChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  collections?: { id: string; name: string }[];
  onCollectionChange?: (collectionId: string | null) => void;
};

export function ChatHeader({
  chat,
  config,
  busy = false,
  onOpenSidebar,
  onProviderChange,
  onModelChange,
  collections = [],
  onCollectionChange,
}: Props) {
  const models = chat && config ? config.providers[chat.provider] || [] : [];
  const [hasScrolled, setHasScrolled] = useState(() => window.scrollY > 0);

  useEffect(() => {
    const updateScrollState = () => setHasScrolled(window.scrollY > 2);
    window.addEventListener('scroll', updateScrollState, { passive: true });
    return () => window.removeEventListener('scroll', updateScrollState);
  }, []);

  return (
    <header
      className={`sticky top-0 z-30 flex min-h-16 items-center justify-between bg-background/95 px-5 backdrop-blur transition-shadow ${
        hasScrolled ? 'shadow-sm' : ''
      }`}
    >
      <div className="flex items-center gap-2">
        {onOpenSidebar ? (
          <button
            type="button"
            className="grid size-9 place-items-center rounded-lg hover:bg-muted lg:hidden"
            onClick={onOpenSidebar}
            aria-label="Mở lịch sử chat"
          >
            <Menu size={19} />
          </button>
        ) : null}
        <div>
          <h1 className="font-semibold">Local Agent</h1>
          <p className="text-xs text-muted-foreground">
            {chat ? `${chat.provider} · ${chat.model}` : 'Đang tải...'}
          </p>
        </div>
      </div>
      {chat && config && (
        <div className="hidden items-center gap-2 sm:flex">
          <Badge variant="outline">
            <Sparkles size={12} />
            Model
          </Badge>
          <select
            value={chat.provider}
            onChange={onProviderChange}
            disabled={busy}
            className="select-control disabled:cursor-not-allowed disabled:opacity-60"
          >
            {Object.keys(config.providers).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
          {chat.projectId ? (
            <select
              value={chat.collectionId || ''}
              onChange={(event) => onCollectionChange?.(event.target.value || null)}
              disabled={busy}
              className="select-control max-w-44 disabled:cursor-not-allowed disabled:opacity-60"
              aria-label="Collection tài liệu"
            >
              <option value="">Chưa chọn tài liệu</option>
              {collections.map((collection) => (
                <option key={collection.id} value={collection.id}>
                  {collection.name}
                </option>
              ))}
            </select>
          ) : null}
          <select
            value={chat.model}
            onChange={onModelChange}
            disabled={busy}
            className="select-control disabled:cursor-not-allowed disabled:opacity-60"
          >
            {models.map((model) => (
              <option key={model}>{model}</option>
            ))}
          </select>
        </div>
      )}
      <Separator
        className={`absolute right-0 bottom-0 left-0 transition-opacity ${hasScrolled ? 'opacity-100' : 'opacity-0'}`}
      />
    </header>
  );
}
