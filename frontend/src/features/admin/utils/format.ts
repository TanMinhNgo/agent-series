export const formatAdminDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : 'Chưa có';
