import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { SettingsHelpPage } from './settings-help-page';

it('shows help topics and navigates to support', () => {
  const navigate = vi.fn();
  render(<SettingsHelpPage navigate={navigate} />);
  expect(screen.getByText('File AI tạo nằm ở đâu?')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Hỗ trợ' }));
  expect(navigate).toHaveBeenCalledWith('/settings/support');
});

it('copies the report without sending it and provides a manual fallback', async () => {
  const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('denied'));
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  render(<SettingsHelpPage navigate={vi.fn()} support />);
  const copy = screen.getByRole('button', { name: 'Sao chép báo lỗi' });
  expect(copy).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Vấn đề bạn gặp phải'), {
    target: { value: 'Không tải được file' },
  });
  fireEvent.click(copy);
  expect(await screen.findByRole('status')).toHaveTextContent('Đã sao chép');
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Không tải được file'));
  expect(screen.getByRole('link', { name: 'Mở GitHub Issues' })).toHaveAttribute(
    'href',
    'https://github.com/TanMinhNgo/agent-series/issues/new',
  );
  fireEvent.click(copy);
  expect(await screen.findByRole('status')).toHaveTextContent('Không thể sao chép tự động');
  expect((screen.getByLabelText('Mẫu báo lỗi để sao chép') as HTMLTextAreaElement).value).toContain(
    'Không tải được file',
  );
});
