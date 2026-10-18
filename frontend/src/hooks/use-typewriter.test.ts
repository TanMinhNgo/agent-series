import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useTypewriter } from './use-typewriter';

describe('useTypewriter', () => {
  afterEach(() => vi.useRealTimers());

  it('reveals text progressively and ends with the full text', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter('Xin chào 👋 bạn', true));
    expect(result.current).toEqual({ shown: '', done: false });

    act(() => vi.advanceTimersByTime(16));
    expect(result.current.shown).toBe('Xi');

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toEqual({ shown: 'Xin chào 👋 bạn', done: true });
  });

  it('shows the text immediately when disabled', () => {
    const { result } = renderHook(() => useTypewriter('Lịch sử', false));
    expect(result.current).toEqual({ shown: 'Lịch sử', done: true });
  });
});
