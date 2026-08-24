import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { LoaderCircle, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void | Promise<unknown>;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Xác nhận',
  destructive = false,
  onOpenChange,
  onConfirm,
}: ConfirmDialogProps) {
  const [confirming, setConfirming] = useState(false);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !confirming) onOpenChange(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [confirming, onOpenChange, open]);

  if (!open) return null;

  const close = () => {
    if (!confirming) onOpenChange(false);
  };
  const confirm = async () => {
    setConfirming(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setConfirming(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[60] grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="w-full max-w-md rounded-2xl border bg-card p-5 shadow-2xl sm:p-6"
      >
        <div className="flex gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-destructive/10 text-destructive">
            <TriangleAlert size={19} />
          </span>
          <div className="min-w-0">
            <h2 id={titleId} className="font-semibold">
              {title}
            </h2>
            <p id={descriptionId} className="mt-1.5 text-sm text-muted-foreground">
              {description}
            </p>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={close} disabled={confirming}>
            Hủy
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            onClick={() => void confirm()}
            disabled={confirming}
          >
            {confirming ? <LoaderCircle className="animate-spin" /> : null}
            {confirming ? 'Đang xử lý...' : confirmLabel}
          </Button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
