import { useEffect, useMemo, useState } from 'react';
import { Menu } from 'lucide-react';

import { Separator } from '@/components/ui/separator';
import { ModelPicker, type ModelPickerProvider } from '@/components/ui/model-picker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Chat, Config } from '@/src/types';

type Props = {
  chat: Chat | null;
  config: Config | null;
  provider?: string;
  model?: string;
  busy?: boolean;
  onRefreshModels?: () => void;
  refreshingModels?: boolean;
  modelsRefreshFailed?: boolean;
  onOpenSidebar?: () => void;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  onSelectionChange?: (provider: string, model: string) => void;
  collections?: { id: string; name: string }[];
  onCollectionChange?: (collectionId: string | null) => void;
};

export function ChatHeader({
  chat,
  config,
  provider,
  model,
  busy = false,
  onRefreshModels,
  refreshingModels = false,
  modelsRefreshFailed = false,
  onOpenSidebar,
  onProviderChange,
  onModelChange,
  onSelectionChange,
  collections = [],
  onCollectionChange,
}: Props) {
  const selectedProvider = chat?.provider || provider;
  const selectedModel = chat?.model || model;
  const modeLabels = {
    standard: 'Thường',
    plan: 'Lập kế hoạch',
    deep: 'Suy nghĩ sâu',
    research: 'Nghiên cứu',
    image: 'Tạo ảnh',
  } as const;
  const pickerProviders = useMemo<ModelPickerProvider[]>(() => {
    if (!config) return [];
    return Object.entries({ ...config.providers, ollama: config.providers.ollama ?? [] }).map(([providerId, models]) => ({
      id: providerId,
      name: providerId === 'openai' ? 'OpenAI' : providerId === 'anthropic' ? 'Anthropic' : providerId === 'gemini' ? 'Google' : providerId === 'ollama' ? 'Ollama' : providerId,
      notice: providerId === 'ollama' ? (
        <div className="space-y-2" role="status">
          <p>{models.length ? 'Ollama đang kết nối.' : config.providerStatus?.ollama?.available ? 'Ollama chưa có model local. Hãy tải model trong Ollama rồi kiểm tra lại.' : 'Ollama chưa kết nối. Bạn có thể tắt để tiết kiệm RAM, mở khi cần rồi kiểm tra lại.'}</p>
          {modelsRefreshFailed && <p className="text-destructive">Không tải được cấu hình. Vui lòng thử lại.</p>}
          {onRefreshModels && <button type="button" disabled={refreshingModels} onClick={onRefreshModels} className="rounded-md border px-2.5 py-1.5 text-foreground hover:bg-muted disabled:opacity-50">{refreshingModels ? 'Đang kiểm tra…' : 'Kiểm tra lại Ollama'}</button>}
        </div>
      ) : undefined,
      models: models.map((modelId) => {
        const imageModel = modelId.toLowerCase().includes('image');
        const reasoningModel = /^(gpt-|claude-|gemini-|grok-)/i.test(modelId) && !imageModel;
        return {
          id: modelId,
          name: modelId,
          capabilities: imageModel ? ['image'] : reasoningModel ? ['reasoning'] : undefined,
          thinking: reasoningModel ? ['low', 'medium', 'high'] : undefined,
          defaultThinking: reasoningModel ? 'medium' : undefined,
        };
      }),
    }));
  }, [config, onRefreshModels, refreshingModels, modelsRefreshFailed]);
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
              ? `${selectedProvider} · ${selectedModel} · ${modeLabels[chat?.mode || 'standard']}`
              : config
                ? 'Chưa có model khả dụng'
                : 'Đang tải cấu hình...'}
          </p>
          {selectedProvider === 'ollama' && config?.providerStatus?.ollama?.available === false ? (
            <p className="mt-1 text-xs text-destructive">{config.providerStatus.ollama.message}</p>
          ) : null}
        </div>
      </div>
      {config && (
        <div className="flex items-center gap-1.5">
          <ModelPicker
            providers={pickerProviders}
            value={selectedModel}
            disabled={busy}
            onValueChange={(modelId, providerId) => {
              if (onSelectionChange) onSelectionChange(providerId, modelId);
              else {
                if (providerId !== selectedProvider) onProviderChange(providerId);
                onModelChange(modelId);
              }
            }}
          />
          {chat?.projectId ? (
            <Select value={chat.collectionId || ''} disabled={busy} onValueChange={(value) => onCollectionChange?.(value || null)}>
              <SelectTrigger className="h-9 max-w-40 rounded-lg border-transparent bg-muted/60 text-xs shadow-none hover:border-border hover:bg-muted" aria-label="Collection tài liệu"><SelectValue placeholder="Chưa chọn tài liệu" /></SelectTrigger>
              <SelectContent><SelectItem value="">Chưa chọn tài liệu</SelectItem>{collections.map((collection) => <SelectItem key={collection.id} value={collection.id}>{collection.name}</SelectItem>)}</SelectContent>
            </Select>
          ) : null}
        </div>
      )}
      <Separator
        className={`absolute right-0 bottom-0 left-0 transition-opacity ${hasScrolled ? 'opacity-100' : 'opacity-0'}`}
      />
    </header>
  );
}
