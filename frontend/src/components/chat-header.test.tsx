import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ChatHeader } from './chat-header';
import type { Config } from '@/src/types';

it('renders provider logos instead of text while preserving accessible names and selection', () => {
  const select = vi.fn();
  render(<ChatHeader chat={null} config={{ providers: { openai: ['gpt-test'], anthropic: ['claude-test'], gemini: ['gemini-test'] }, defaultProvider: 'openai', defaultModel: 'gpt-test' }} provider="openai" model="gpt-test" onProviderChange={vi.fn()} onModelChange={vi.fn()} onSelectionChange={select} />);
  fireEvent.click(screen.getByRole('button', { name: 'gpt-test' }));
  const rail = within(screen.getByRole('group', { name: 'Nhà cung cấp model' }));
  const paths = ['OpenAI', 'Anthropic', 'Google', 'Ollama'].map((name) => {
    const button = rail.getByRole('button', { name });
    expect(button.textContent).toBe('');
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    return button.querySelector('path')?.getAttribute('d');
  });
  expect(paths.every(Boolean)).toBe(true);
  expect(new Set(paths).size).toBe(4);
  fireEvent.click(rail.getByRole('button', { name: 'Google' }));
  expect(rail.getByRole('button', { name: 'Google' })).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(screen.getByRole('button', { name: /gemini-test/ }));
  expect(select).toHaveBeenCalledWith('gemini', 'gemini-test');
});

it('keeps offline Ollama visible without a selected model and loads models after a manual refresh', async () => {
  const refresh = vi.fn();
  const select = vi.fn();
  const config: Config = {
    providers: {}, defaultProvider: 'ollama', defaultModel: '',
    providerStatus: { ollama: { available: false, message: 'Offline', models: [] } },
  };
  const props = { chat: null, config, onProviderChange: vi.fn(), onModelChange: vi.fn(), onSelectionChange: select, onRefreshModels: refresh };
  const { rerender } = render(<ChatHeader {...props} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chọn model' }));
  expect(await screen.findByRole('button', { name: 'Ollama' })).toBeInTheDocument();
  expect(screen.getByText(/Ollama chưa kết nối/)).toBeInTheDocument();
  expect(select).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra lại Ollama' }));
  expect(refresh).toHaveBeenCalledTimes(1);
  rerender(<ChatHeader {...props} refreshingModels />);
  expect(screen.getByRole('button', { name: 'Đang kiểm tra…' })).toBeDisabled();
  rerender(<ChatHeader {...props} config={{ ...config, providerStatus: { ollama: { available: true, message: null, models: [] } } }} />);
  expect(screen.getByText(/Ollama chưa có model local/)).toBeInTheDocument();
  rerender(<ChatHeader {...props} config={{ ...config, providers: { ollama: ['llama3.2:1b'] }, providerStatus: { ollama: { available: true, message: null, models: ['llama3.2:1b'] } } }} />);
  fireEvent.click(screen.getByRole('button', { name: /llama3.2:1b/ }));
  expect(select).toHaveBeenCalledWith('ollama', 'llama3.2:1b');
});
