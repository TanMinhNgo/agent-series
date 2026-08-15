import { useEffect, useState } from 'react';
import { LoaderCircle, Search, Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { request } from '@/src/hooks/client';

type Memory = {
  id: string;
  chatId: string;
  chatTitle: string;
  role: string;
  content: string;
  createdAt: string;
};

export function MemoryLibraryDialog({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<Memory[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const load = async (term = '') => {
    setLoading(true);
    try {
      setItems(await request<Memory[]>({ url: '/memories', params: { query: term } }));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let active = true;
    void request<Memory[]>({ url: '/memories' })
      .then((result) => {
        if (active) setItems(result);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const search = (value: string) => {
    setQuery(value);
    void load(value);
  };
  const forget = async (id: string) => {
    await request<void>({ url: `/memories/${id}`, method: 'DELETE' });
    setItems((current) => current.filter((item) => item.id !== id));
  };
  const forgetAll = async () => {
    if (!window.confirm('Xóa toàn bộ memory trong Thư viện? Điều này không xóa lịch sử chat.')) return;
    await request<void>({ url: '/memories', method: 'DELETE' });
    setItems([]);
  };
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-library-title"
    >
      <section className="flex max-h-[85dvh] w-full max-w-4xl flex-col rounded-3xl border bg-card p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4 border-b pb-4">
          <div>
            <h2 id="memory-library-title" className="text-xl font-semibold sm:text-2xl">
              Thư viện cá nhân
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Memory tự lưu từ chat trên local database của bạn.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Đóng">
            <X />
          </Button>
        </div>
        <div className="my-4 flex gap-2">
          <label className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border bg-background px-3">
            <Search size={16} className="text-muted-foreground" />
            <input
              className="min-w-0 flex-1 bg-transparent py-2 outline-none"
              value={query}
              onChange={(event) => search(event.target.value)}
              placeholder="Tìm trong memory..."
            />
          </label>
          <Button variant="destructive" onClick={() => void forgetAll()} disabled={!items.length}>
            <Trash2 /> Xóa hết
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="animate-spin" size={16} /> Đang tải memory...
            </p>
          ) : items.length ? (
            <ul className="space-y-2">
              {items.map((item) => (
                <li key={item.id} className="rounded-xl border bg-background p-3">
                  <div className="flex gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-muted-foreground">
                        {item.chatTitle} · {item.role === 'user' ? 'Bạn' : 'AI'}
                      </p>
                      <p className="mt-1 line-clamp-3 text-sm">{item.content}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => void forget(item.id)}
                      aria-label="Quên memory"
                    >
                      <Trash2 size={16} />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Chưa có memory. Gửi tin nhắn để hệ thống tự lưu kiến thức liên quan.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
