import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
import { useAccountSettings, type AccountSettings } from '@/src/hooks/use-account-settings';
import { useGetConfig } from '@/src/hooks/use-get-config';

export function SettingsAccountPage({ navigate }: { navigate: (to: string) => void }) {
  const { settings } = useAccountSettings();
  if (settings.isLoading) return <div className="p-8">Đang tải cài đặt...</div>;
  if (!settings.data)
    return (
      <p role="alert" className="p-8 text-destructive">
        {settings.error?.message || 'Không thể tải cài đặt.'}
      </p>
    );
  return <SettingsAccountEditor initial={settings.data} navigate={navigate} />;
}

function SettingsAccountEditor({
  initial,
  navigate,
}: {
  initial: AccountSettings;
  navigate: (to: string) => void;
}) {
  const { settings, save, clearLearned } = useAccountSettings();
  const config = useGetConfig();
  const [draft, setDraft] = useState<AccountSettings>(initial);
  const [notice, setNotice] = useState('');
  const models = draft.defaultProvider ? config.data?.providers[draft.defaultProvider] || [] : [];
  const invalidDefault = !!draft.defaultModel && !models.includes(draft.defaultModel);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setNotice('');
    try {
      await save.mutateAsync(draft);
      setNotice('Đã lưu cài đặt.');
    } catch {
      // The mutation error is shown below and the form stays editable.
    }
  };
  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8 sm:px-8 lg:px-12">
      <div>
        <p className="text-sm font-medium text-primary">Tài khoản</p>
        <h1 className="mt-1 text-3xl font-semibold">Cài đặt</h1>
      </div>
      <form onSubmit={(event) => void submit(event)} className="space-y-6">
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Hồ sơ</h2>
          <div className="flex items-center gap-3">
            <span className="relative grid size-12 place-items-center overflow-hidden rounded-full bg-pink-400 font-semibold text-white">
              {(draft.displayName || draft.email).slice(0, 2).toUpperCase()}
              {draft.avatarUrl ? (
                <img
                  src={draft.avatarUrl}
                  alt="Ảnh đại diện Google"
                  className="absolute size-12 rounded-full object-cover"
                  referrerPolicy="no-referrer"
                  onError={(event) => {
                    event.currentTarget.style.display = 'none';
                  }}
                />
              ) : null}
            </span>
            <span className="text-sm text-muted-foreground">Ảnh từ tài khoản Google</span>
          </div>
          <label className="grid gap-2 text-sm">
            Tên hiển thị
            <input
              className="rounded-lg border bg-background px-3 py-2"
              required
              maxLength={160}
              value={draft.displayName}
              onChange={(event) => setDraft({ ...draft, displayName: event.target.value })}
            />
          </label>
          <label className="grid gap-2 text-sm">
            Email Google
            <input className="rounded-lg border bg-muted px-3 py-2" value={draft.email} readOnly />
          </label>
        </section>
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Giao diện</h2>
          <div className="grid gap-2 text-sm">
            <label htmlFor="settings-theme">Chủ đề</label>
            <Select
              value={draft.theme}
              onValueChange={(value) => setDraft({ ...draft, theme: value as AccountSettings['theme'] })}
            >
              <SelectTrigger id="settings-theme" className="w-full bg-background">
                {{ system: 'Theo hệ thống', light: 'Sáng', dark: 'Tối' }[draft.theme]}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">Theo hệ thống</SelectItem>
                <SelectItem value="light">Sáng</SelectItem>
                <SelectItem value="dark">Tối</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </section>
        <section className="space-y-4 rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Tùy chỉnh AI</h2>
          <label className="grid gap-2 text-sm">
            Chỉ dẫn tùy chỉnh
            <textarea
              className="min-h-32 rounded-lg border bg-background px-3 py-2"
              maxLength={10000}
              value={draft.customInstructions}
              onChange={(event) => setDraft({ ...draft, customInstructions: event.target.value })}
              placeholder="Ví dụ: Trả lời ngắn gọn, có ví dụ TypeScript khi phù hợp."
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.autoLearn}
              onChange={(event) => setDraft({ ...draft, autoLearn: event.target.checked })}
            />{' '}
            Tự học sở thích từ nội dung chat và đánh giá
          </label>
          <p className="text-xs text-muted-foreground">
            Tắt mục này sẽ ngừng ghi nhận và sử dụng sở thích đã học. Chỉ dẫn tùy chỉnh vẫn có hiệu lực.
          </p>
          <Button
            type="button"
            variant="outline"
            disabled={clearLearned.isPending}
            onClick={() => {
              if (window.confirm('Xóa toàn bộ sở thích đã học? Chỉ dẫn tùy chỉnh sẽ được giữ lại.'))
                clearLearned.mutate(undefined, { onSuccess: () => setNotice('Đã xóa sở thích đã học.') });
            }}
          >
            Xóa sở thích đã học
          </Button>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2 text-sm">
              <label htmlFor="settings-provider">Provider mặc định</label>
              <Select
                value={draft.defaultProvider || ''}
                onValueChange={(value) => {
                  const provider = value || null;
                  setDraft({
                    ...draft,
                    defaultProvider: provider,
                    defaultModel: provider ? config.data?.providers[provider]?.[0] || null : null,
                  });
                }}
              >
                <SelectTrigger id="settings-provider" className="w-full bg-background">
                  {draft.defaultProvider || 'Theo hệ thống'}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Theo hệ thống</SelectItem>
                  {Object.keys(config.data?.providers || {}).map((provider) => (
                    <SelectItem key={provider} value={provider}>
                      {provider}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 text-sm">
              <label htmlFor="settings-model">Model mặc định</label>
              <Select
                value={invalidDefault ? '' : draft.defaultModel || ''}
                disabled={!draft.defaultProvider}
                onValueChange={(value) => setDraft({ ...draft, defaultModel: value || null })}
              >
                <SelectTrigger id="settings-model" className="w-full bg-background">
                  {invalidDefault ? 'Chọn model' : draft.defaultModel || 'Chọn model'}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Chọn model</SelectItem>
                  {models.map((model) => (
                    <SelectItem key={model} value={model}>
                      {model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {invalidDefault ? (
            <p role="alert" className="text-sm text-amber-600">
              Model đã lưu không còn khả dụng. Chat mới đang dùng model hợp lệ; hãy chọn lại và lưu.
            </p>
          ) : null}
        </section>
        {settings.error || save.error || clearLearned.error ? (
          <p role="alert" className="text-sm text-destructive">
            {(settings.error || save.error || clearLearned.error)?.message}
          </p>
        ) : null}
        {notice ? <output className="block text-sm text-emerald-600">{notice}</output> : null}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={save.isPending || invalidDefault}>
            Lưu cài đặt
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate('/settings/api-keys')}>
            Quản lý API key
          </Button>
        </div>
      </form>
    </main>
  );
}
