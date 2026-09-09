import { describe, expect, it } from 'vitest';

import { statusForStreamEvent } from './chat-stream-status';

describe('statusForStreamEvent', () => {
  it('clears the stream status after completion or cancellation', () => {
    expect(statusForStreamEvent('done', {})).toBeNull();
    expect(statusForStreamEvent('cancelled', {})).toBeNull();
  });

  it('formats status and tool events without changing unrelated events', () => {
    expect(statusForStreamEvent('status', { message: 'Đang xử lý' })).toBe('Đang xử lý');
    expect(statusForStreamEvent('tool_call', { name: 'search_web' })).toBe('Đang dùng search_web...');
    expect(statusForStreamEvent('tool_result', { name: 'search_web' })).toBe(
      'Đã nhận kết quả từ search_web.',
    );
    expect(statusForStreamEvent('message', {})).toBeUndefined();
  });
});
