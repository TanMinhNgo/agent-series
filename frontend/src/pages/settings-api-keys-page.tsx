import { KeyRound, LoaderCircle, ShieldCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { ApiError } from '@/src/hooks/client';
import { useApiKeys } from '@/src/hooks/use-api-keys';

const providers = [
  { id: 'gemini', name: 'Google Gemini', hint: 'Lấy key từ Google AI Studio.' },
  { id: 'openai', name: 'OpenAI', hint: 'Lấy key từ OpenAI Platform.' },
  { id: 'anthropic', name: 'Anthropic Claude', hint: 'Lấy key từ Anthropic Console.' },
] as const;

export function SettingsApiKeysPage() {
  const [provider, setProvider] = useState<(typeof providers)[number]['id']>('gemini');
  const [apiKey, setApiKey] = useState('');
  const { keys, save, remove } = useApiKeys();
  const selected = providers.find((item) => item.id === provider)!;
  const error = keys.error || save.error || remove.error;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-8 lg:px-12">
      <div className="mb-8">
        <p className="text-sm font-medium text-primary">Cài đặt</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Thêm API key của bạn</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          API key chỉ được dùng cho các cuộc chat của bạn. Hệ thống kiểm tra, mã hóa và không bao giờ hiển thị
          lại key đầy đủ.
        </p>
      </div>
      {error ? (
        <div
          role="alert"
          className="mb-5 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
        >
          {error instanceof ApiError ? error.message : 'Không thể xử lý API key.'}
        </div>
      ) : null}
      <section className="rounded-2xl border bg-card shadow-sm">
        <div className="border-b p-5">
          <h2 className="font-semibold">Kết nối provider</h2>
          <p className="mt-1 text-sm text-muted-foreground">Chọn provider rồi dán API key của chính bạn.</p>
        </div>
        <form
          className="space-y-5 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (apiKey.trim()) save.mutate({ provider, apiKey });
          }}
        >
          <label className="grid gap-2 text-sm font-medium">
            Provider
            <select
              className="workspace-input"
              value={provider}
              onChange={(event) => setProvider(event.target.value as typeof provider)}
            >
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium">
            API key
            <input
              className="workspace-input font-mono"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="Dán API key tại đây"
            />
          </label>
          <p className="text-xs text-muted-foreground">{selected.hint} Key sẽ được kiểm tra trước khi lưu.</p>
          <Button type="submit" disabled={!apiKey.trim() || save.isPending}>
            {save.isPending ? (
              <>
                <LoaderCircle className="animate-spin" /> Đang xác minh...
              </>
            ) : (
              <>
                <ShieldCheck /> Xác minh và lưu
              </>
            )}
          </Button>
        </form>
      </section>
      <section className="mt-6 rounded-2xl border bg-card shadow-sm">
        <div className="border-b p-5">
          <h2 className="font-semibold">API key đã lưu</h2>
          <p className="mt-1 text-sm text-muted-foreground">Chỉ hiển thị 4 ký tự cuối để nhận diện key.</p>
        </div>
        <div className="divide-y">
          {keys.isLoading ? (
            <p className="p-5 text-sm text-muted-foreground">Đang tải...</p>
          ) : keys.data?.items.length ? (
            keys.data.items.map((item) => (
              <div key={item.provider} className="flex flex-wrap items-center gap-3 p-5">
                <span className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary">
                  <KeyRound size={17} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {providers.find((providerItem) => providerItem.id === item.provider)?.name}
                  </p>
                  <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                    {item.keyHint} · Xác minh {new Date(item.validatedAt).toLocaleDateString('vi-VN')}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Xóa API key ${item.provider}? Bạn sẽ không thể hoàn tác.`))
                      remove.mutate(item.provider);
                  }}
                >
                  <Trash2 /> Xóa
                </Button>
              </div>
            ))
          ) : (
            <p className="p-5 text-sm text-muted-foreground">Bạn chưa thêm API key nào.</p>
          )}
        </div>
      </section>
    </div>
  );
}
