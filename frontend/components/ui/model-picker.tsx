'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { Brain, Check, ChevronDown, ImageIcon, Search, X } from 'lucide-react';
import { Popover, Tooltip } from 'radix-ui';
import { cn } from '@/lib/utils';
import { ProviderLogo } from './provider-logo';

export type ModelCapability = 'reasoning' | 'image';
export type ThinkingEffort = 'none' | 'low' | 'medium' | 'high' | 'max';

export type ModelPickerModel = {
  id: string;
  name: string;
  description?: string;
  available?: boolean;
  capabilities?: readonly ModelCapability[];
  thinking?: readonly ThinkingEffort[];
  defaultThinking?: ThinkingEffort;
};

export type ModelPickerProvider = {
  id: string;
  name: string;
  icon?: ReactNode;
  notice?: ReactNode;
  models: ModelPickerModel[];
};

export type ModelPickerProps = {
  providers: readonly ModelPickerProvider[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (modelId: string, providerId: string, thinking?: ThinkingEffort) => void;
  thinking?: ThinkingEffort;
  defaultThinking?: ThinkingEffort;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
};

const effortLabels: Record<ThinkingEffort, string> = {
  none: 'Off',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  max: 'Max',
};

function ProviderIcon({ provider }: { provider: ModelPickerProvider }) {
  if (provider.icon)
    return (
      <span aria-hidden="true" className="inline-flex size-5 items-center justify-center [&>svg]:size-full">
        {provider.icon}
      </span>
    );
  return <ProviderLogo provider={provider.id} />;
}

function CapabilityChips({ capabilities }: { capabilities?: readonly ModelCapability[] }) {
  if (!capabilities?.length) return null;
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      {capabilities.includes('reasoning') ? (
        <Brain aria-label="Reasoning" className="size-3.5 text-violet-500" />
      ) : null}
      {capabilities.includes('image') ? (
        <ImageIcon aria-label="Image" className="size-3.5 text-teal-500" />
      ) : null}
    </span>
  );
}

export function ModelPicker({
  providers,
  value,
  defaultValue,
  onValueChange,
  thinking,
  defaultThinking,
  disabled,
  placeholder = 'Chọn model',
  className,
}: ModelPickerProps) {
  const availableProviders = useMemo(
    () => providers.filter((item) => item.notice || item.models.some((model) => model.available !== false)),
    [providers],
  );
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(defaultValue ?? value);
  const [selectedThinking, setSelectedThinking] = useState<ThinkingEffort | undefined>(
    defaultThinking ?? thinking,
  );
  const selected = useMemo(
    () =>
      availableProviders
        .flatMap((provider) => provider.models.map((model) => ({ provider, model })))
        .find((item) => item.model.id === (value ?? selectedId)),
    [availableProviders, selectedId, value],
  );
  const [activeProviderId, setActiveProvider] = useState(
    selected?.provider.id ?? availableProviders[0]?.id ?? '',
  );
  const activeProvider =
    availableProviders.find((provider) => provider.id === activeProviderId)?.id ?? availableProviders[0]?.id;
  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return availableProviders.flatMap((provider) =>
      provider.models
        .filter(
          (model) =>
            model.available !== false &&
            (!normalized ||
              [model.id, model.name, model.description ?? '', provider.name].some((field) =>
                field.toLowerCase().includes(normalized),
              )) &&
            (normalized || provider.id === activeProvider),
        )
        .map((model) => ({ provider, model })),
    );
  }, [activeProvider, availableProviders, query]);
  const selectModel = (model: ModelPickerModel, provider: ModelPickerProvider) => {
    const effort = model.defaultThinking ?? model.thinking?.[0];
    setActiveProvider(provider.id);
    setSelectedId(model.id);
    setSelectedThinking(effort);
    onValueChange?.(model.id, provider.id, effort);
  };
  const levels = selected?.model.thinking?.length ? selected.model.thinking : [];
  const currentThinking = thinking ?? selectedThinking;
  return (
    <Tooltip.Provider delayDuration={250}>
      <Popover.Root
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery('');
        }}
      >
        <Popover.Trigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-label={selected?.model.name ?? placeholder}
            className={cn(
              'inline-flex h-9 max-w-full items-center gap-2 rounded-lg bg-muted/60 px-3 text-xs font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50',
              className,
            )}
          >
            {selected ? <ProviderIcon provider={selected.provider} /> : null}
            <span className="truncate">{selected?.model.name ?? placeholder}</span>
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            side="bottom"
            align="end"
            sideOffset={8}
            className="z-50 flex h-[26rem] max-h-[min(calc(100dvh-1rem),var(--radix-popover-content-available-height))] w-[min(28rem,calc(100vw-1rem))] flex-col overflow-hidden rounded-xl border bg-popover p-2 text-popover-foreground shadow-lg"
            onOpenAutoFocus={(event) => event.preventDefault()}
          >
            <div className="flex shrink-0 items-center gap-2 rounded-lg bg-muted/60 px-2.5 py-2">
              <Search className="size-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm model"
                aria-label="Tìm model"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              />
              {query ? (
                <button type="button" aria-label="Xóa tìm kiếm" onClick={() => setQuery('')}>
                  <X className="size-3.5" />
                </button>
              ) : null}
            </div>
            {!query ? (
              <div
                className="mt-2 flex h-11 shrink-0 gap-1 overflow-x-auto"
                role="group"
                aria-label="Nhà cung cấp model"
              >
                {availableProviders.map((provider) => (
                  <Tooltip.Root key={provider.id}>
                    <Tooltip.Trigger asChild>
                      <button
                        type="button"
                        aria-label={provider.name}
                        aria-pressed={provider.id === activeProvider}
                        onClick={() => setActiveProvider(provider.id)}
                        className={cn(
                          'inline-flex size-10 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                          provider.id === activeProvider
                            ? 'bg-muted ring-1 ring-inset ring-border'
                            : 'hover:bg-muted/70',
                        )}
                      >
                        <ProviderIcon provider={provider} />
                      </button>
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        side="top"
                        sideOffset={6}
                        className="z-50 rounded-md bg-foreground px-2 py-1 text-xs text-background"
                      >
                        {provider.name}
                        <Tooltip.Arrow className="fill-foreground" />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                ))}
              </div>
            ) : null}
            <div className="mt-2 min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
              <div className="space-y-0.5">
                {rows.length ? (
                  rows.map(({ model, provider }) => (
                    <button
                      key={`${provider.id}:${model.id}`}
                      type="button"
                      onClick={() => selectModel(model, provider)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-muted',
                        selected?.model.id === model.id && 'bg-muted',
                      )}
                    >
                      <ProviderIcon provider={provider} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 text-sm font-medium">
                          <span className="min-w-0 truncate" title={model.name}>
                            {model.name}
                          </span>
                          {selected?.model.id === model.id ? <Check className="size-3.5" /> : null}
                        </span>
                        {model.description ? (
                          <span className="block truncate text-[11px] text-muted-foreground">
                            {model.description}
                          </span>
                        ) : null}
                      </span>
                      <CapabilityChips capabilities={model.capabilities} />
                    </button>
                  ))
                ) : (
                  <p className="px-2 py-6 text-center text-xs text-muted-foreground">Không tìm thấy model</p>
                )}
              </div>
              {availableProviders
                .filter((provider) =>
                  query.trim()
                    ? provider.name.toLowerCase().includes(query.trim().toLowerCase())
                    : provider.id === activeProvider,
                )
                .map((provider) =>
                  provider.notice ? (
                    <div
                      key={provider.id}
                      className="mt-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground"
                    >
                      {provider.notice}
                    </div>
                  ) : null,
                )}
            </div>
            <div className="mt-2 flex h-12 shrink-0 items-center gap-2 border-t pt-2">
              <span className="text-[11px] text-muted-foreground">Thinking</span>
              {levels.length ? (
                <div className="flex flex-1 gap-1 rounded-full bg-muted p-1">
                  {levels.map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => {
                        setSelectedThinking(level);
                        if (selected) onValueChange?.(selected.model.id, selected.provider.id, level);
                      }}
                      className={cn(
                        'flex-1 rounded-full px-1.5 py-1 text-[11px]',
                        currentThinking === level && 'bg-popover font-medium shadow-sm',
                      )}
                    >
                      {effortLabels[level]}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="text-[11px] text-muted-foreground">Model này không có thinking control</span>
              )}
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </Tooltip.Provider>
  );
}
