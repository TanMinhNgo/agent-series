import { useEffect, useState } from 'react';
import { Download, ExternalLink, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

type LightboxImage = { url: string; name: string };

async function downloadImage({ url, name }: LightboxImage) {
  try {
    const response = await fetch(url, { credentials: 'include' });
    if (!response.ok) throw new Error(String(response.status));
    const href = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement('a'), { href, download: name });
    link.click();
    URL.revokeObjectURL(href);
  } catch {
    // ponytail: storage redirects without CORS can't be fetched; open the file so it can be saved manually.
    window.open(url, '_blank', 'noopener');
  }
}

/** Thumbnail that opens the full image in an overlay, with download and open-in-tab actions. */
export function ImageLightbox({ image, className }: { image: LightboxImage; className?: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <>
      <span className="group relative inline-block overflow-hidden rounded-lg border bg-muted">
        <button
          type="button"
          className="block cursor-zoom-in"
          onClick={() => setOpen(true)}
          aria-label={`Xem lớn ${image.name}`}
        >
          <img src={image.url} alt={image.name} className={className} />
        </button>
        <Button
          variant="secondary"
          size="icon-sm"
          className="absolute top-2 right-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
          onClick={() => void downloadImage(image)}
          aria-label={`Tải ${image.name}`}
          title="Tải ảnh về"
        >
          <Download size={16} />
        </Button>
      </span>
      {open ? (
        <div
          className="fixed inset-0 z-[70] flex flex-col bg-black/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={image.name}
          onClick={() => setOpen(false)}
        >
          <div className="flex items-center justify-between gap-3 px-4 py-3 text-white">
            <span className="min-w-0 truncate text-sm">{image.name}</span>
            <div className="flex shrink-0 gap-1" onClick={(event) => event.stopPropagation()}>
              <Button
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/15"
                onClick={() => void downloadImage(image)}
                aria-label="Tải ảnh về"
                title="Tải ảnh về"
              >
                <Download size={18} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/15"
                nativeButton={false}
                render={<a href={image.url} target="_blank" rel="noreferrer" />}
                aria-label="Mở ảnh trong tab mới"
                title="Mở trong tab mới"
              >
                <ExternalLink size={18} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/15"
                onClick={() => setOpen(false)}
                aria-label="Đóng"
                title="Đóng (Esc)"
              >
                <X size={18} />
              </Button>
            </div>
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center p-4">
            <img
              src={image.url}
              alt={image.name}
              className="max-h-full max-w-full object-contain"
              onClick={(event) => event.stopPropagation()}
            />
          </div>
        </div>
      ) : null}
    </>
  );
}
