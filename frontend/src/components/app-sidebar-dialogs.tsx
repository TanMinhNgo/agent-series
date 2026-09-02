import { createPortal } from 'react-dom';

import { Button } from '@/components/ui/button';
import type { Chat } from '@/src/types';

type RenameChatDialogProps = {
  chat: Chat | null;
  title: string;
  onTitleChange: (title: string) => void;
  onClose: () => void;
  onRename: (chat: Chat, title: string) => void;
};

export function RenameChatDialog({ chat, title, onTitleChange, onClose, onRename }: RenameChatDialogProps) {
  if (!chat) return null;

  return createPortal(
    <dialog
      open
      className="fixed inset-0 z-100 grid place-items-center bg-black/60 p-4"
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <form
        className="w-full max-w-sm rounded-2xl border bg-card p-5"
        onSubmit={(event) => {
          event.preventDefault();
          const nextTitle = title.trim();
          if (nextTitle) onRename(chat, nextTitle);
          onClose();
        }}
      >
        <h2 className="text-lg font-semibold">Đổi tên cuộc trò chuyện</h2>
        <input
          autoFocus
          maxLength={160}
          className="mt-4 w-full rounded-xl border bg-background px-3 py-2"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
        />
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit">Lưu</Button>
        </div>
      </form>
    </dialog>,
    document.body,
  );
}

export function DeleteChatDialog({
  chat,
  onClose,
  onDelete,
}: {
  chat: Chat | null;
  onClose: () => void;
  onDelete: (chat: Chat) => void;
}) {
  if (!chat) return null;

  return createPortal(
    <dialog
      open
      className="fixed inset-0 z-100 grid place-items-center bg-black/60 p-4"
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <section className="w-full max-w-sm rounded-2xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Xóa cuộc trò chuyện?</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Toàn bộ lịch sử và liên kết chia sẻ công khai sẽ bị thu hồi.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              onDelete(chat);
              onClose();
            }}
          >
            Xóa
          </Button>
        </div>
      </section>
    </dialog>,
    document.body,
  );
}
