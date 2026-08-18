import axios, { AxiosError, type AxiosRequestConfig } from 'axios';

export class ApiError extends Error {}

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: { Accept: 'application/json' },
  // Frontend (5173) and API (8000) are distinct origins in development.
  // Keep the HTTP-only session cookie on every auth and workspace request.
  withCredentials: true,
});

export const request = async <T>(config: AxiosRequestConfig): Promise<T> => {
  try {
    const isFormData = typeof FormData !== 'undefined' && config.data instanceof FormData;
    const response = await apiClient.request<T>({
      ...config,
      headers: {
        Accept: 'application/json',
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...config.headers,
      },
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
