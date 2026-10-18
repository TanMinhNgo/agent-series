import { useEffect, useState } from 'react';

const TICK_MS = 16;

export function useTypewriter(text: string, enabled: boolean) {
  const [count, setCount] = useState(() =>
    enabled && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : Infinity,
  );
  // Code points, so emoji and combined Vietnamese characters are never split.
  const chars = Array.from(text);
  const done = count >= chars.length;

  useEffect(() => {
    if (done) return;
    // Short replies type at a natural pace; long ones still finish in about 2s.
    const step = Math.max(2, Math.ceil(chars.length / 120));
    const timer = setInterval(() => setCount((value) => value + step), TICK_MS);
    return () => clearInterval(timer);
  }, [done, chars.length]);

  return { shown: done ? text : chars.slice(0, count).join(''), done };
}
