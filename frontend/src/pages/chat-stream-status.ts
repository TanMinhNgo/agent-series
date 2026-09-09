export function statusForStreamEvent(name: string, data: Record<string, unknown>): string | null | undefined {
  if (name === 'status') return String(data.message);
  if (name === 'done' || name === 'cancelled') return null;
  if (name === 'tool_call') return `Đang dùng ${String(data.name)}...`;
  if (name === 'tool_result') return `Đã nhận kết quả từ ${String(data.name)}.`;
  return undefined;
}
