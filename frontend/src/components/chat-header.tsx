import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';

import { Separator } from '@/components/ui/separator';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Chat, Config } from '@/src/types';

type Props = {
  chat: Chat | null;
  config: Config | null;
  provider?: string;
  model?: string;
  busy?: boolean;
  onOpenSidebar?: () => void;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  collections?: { id: string; name: string }[];
  onCollectionChange?: (collectionId: string | null) => void;
};

export function ChatHeader({
  chat,
  config,
  provider,
  model,
  busy = false,
  onOpenSidebar,
  onProviderChange,
  onModelChange,
  collections = [],
  onCollectionChange,
}: Props) {
  const selectedProvider = chat?.provider || provider;
  const selectedModel = chat?.model || model;
  const models = config && selectedProvider ? config.providers[selectedProvider] || [] : [];
  const [hasScrolled, setHasScrolled] = useState(() => window.scrollY > 0);

  useEffect(() => {
    const updateScrollState = () => setHasScrolled(window.scrollY > 2);
    window.addEventListener('scroll', updateScrollState, { passive: true });
    return () => window.removeEventListener('scroll', updateScrollState);
  }, []);

  return (
    <header
      className={`sticky top-0 z-30 flex min-h-15 items-center justify-between border-b border-transparent bg-background/90 px-4 backdrop-blur transition-[border-color,box-shadow] sm:px-6 ${
        hasScrolled ? 'border-border/80 shadow-sm shadow-black/[0.02]' : ''
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
        <div className="min-w-0">
          <p className="mb-0.5 text-[10px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
            {chat?.projectId ? 'Dự án' : 'Workspace'}
          </p>
          <h1 className="truncate text-sm font-semibold tracking-tight">
            {chat?.title || 'Cuộc trò chuyện mới'}
          </h1>
          <p className="text-xs text-muted-foreground">
            {selectedProvider && selectedModel
              ? `${selectedProvider} · ${selectedModel}`
              : config
                ? 'Chưa có model khả dụng'
                : 'Đang tải cấu hình...'}
          </p>
          {selectedProvider === 'ollama' && config?.providerStatus?.ollama?.available === false ? (
            <p className="mt-1 text-xs text-destructive">{config.providerStatus.ollama.message}</p>
          ) : null}
        </div>
      </div>
      {config && selectedProvider && selectedModel && (
        <div className="hidden items-center gap-1.5 sm:flex">
          <Select
            value={selectedProvider}
            disabled={busy}
            onValueChange={(value) => {
              if (value) onProviderChange(value);
            }}
          >
            <SelectTrigger className="h-8 max-w-32 rounded-lg border-transparent bg-muted/60 text-xs shadow-none hover:border-border hover:bg-muted">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(config.providers).map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {chat?.projectId ? (
            <Select
              value={chat.collectionId || ''}
              disabled={busy}
              onValueChange={(value) => onCollectionChange?.(value || null)}
            >
              <SelectTrigger
                className="h-8 max-w-40 rounded-lg border-transparent bg-muted/60 text-xs shadow-none hover:border-border hover:bg-muted"
                aria-label="Collection tài liệu"
              >
                <SelectValue placeholder="Chưa chọn tài liệu" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Chưa chọn tài liệu</SelectItem>
                {collections.map((collection) => (
                  <SelectItem key={collection.id} value={collection.id}>
                    {collection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <Select
            value={selectedModel}
            disabled={busy}
            onValueChange={(value) => {
              if (value) onModelChange(value);
            }}
          >
            <SelectTrigger className="h-8 max-w-48 rounded-lg border-transparent bg-muted/60 text-xs shadow-none hover:border-border hover:bg-muted">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {models.map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <Separator
        className={`absolute right-0 bottom-0 left-0 transition-opacity ${hasScrolled ? 'opacity-100' : 'opacity-0'}`}
      />
    </header>
  );
}
