import axios, { AxiosError, type AxiosRequestConfig } from 'axios';

export class ApiError extends Error {}

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
});

export const request = async <T>(config: AxiosRequestConfig): Promise<T> => {
  try {
    const response = await apiClient.request<T>({
      ...config,
      headers: config.data instanceof FormData ? { Accept: 'application/json' } : config.headers,
    });
    return response.data;
  } catch (error) {
    if (error instanceof AxiosError) {
      const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
      throw new ApiError(detail || 'Không thể kết nối API.');
    }
    throw error;
  }
};

export const readSse = async (
  response: Response,
  onEvent: (event: string, data: Record<string, unknown>) => void,
) => {
  if (!response.body) throw new ApiError('Server không trả stream.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const next = await reader.read();
    if (next.done) break;
    buffer += decoder.decode(next.value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    blocks.forEach((block) => {
      const event = block.match(/^event: (.+)$/m)?.[1];
      const raw = block.match(/^data: (.+)$/m)?.[1];
      if (event && raw) onEvent(event, JSON.parse(raw) as Record<string, unknown>);
    });
  }
};
