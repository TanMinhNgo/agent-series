export const queryKeys = {
  config: ['config'] as const,
  chats: ['chats'] as const,
  chat: (chatId: string) => ['chats', chatId] as const,
  documents: ['documents'] as const,
  projects: ['projects'] as const,
  schedules: ['schedules'] as const,
  plugins: ['plugins'] as const,
  messages: (chatId: string) => ['chats', chatId, 'messages'] as const,
};
