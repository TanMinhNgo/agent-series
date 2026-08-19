import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ADMIN_PAGE_SIZE } from '@/src/features/admin/types/admin';

export function AdminEmpty({ children }: { children: ReactNode }) {
  return <p className="py-10 text-center text-sm text-muted-foreground">{children}</p>;
}
export function AdminPanel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn('rounded-2xl border bg-card shadow-sm', className)}>{children}</section>;
}
export function AdminPager({
  page,
  total,
  onChange,
}: {
  page: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / ADMIN_PAGE_SIZE));
  return (
    <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
      <span>
        Trang {page} / {pages} · {total} mục
      </span>
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={page === 1}
          onClick={() => onChange(page - 1)}
          aria-label="Trang trước"
        >
          <ChevronLeft />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={page === pages}
          onClick={() => onChange(page + 1)}
          aria-label="Trang sau"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
