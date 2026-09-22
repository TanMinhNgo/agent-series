import { expect, it } from 'vitest';
import { markdownToPlainText } from './markdown-to-plain-text';

it('keeps link text and removes horizontal rules without changing nearby lines', () => {
  expect(markdownToPlainText('Đọc [tài liệu](https://example.com "Mô tả")\n\n- - -\n\nTiếp tục')).toBe(
    'Đọc tài liệu (https://example.com)\n\nTiếp tục',
  );
});
