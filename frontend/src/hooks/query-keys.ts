export const queryKeys = {
  config: ['config'] as const,
  chats: ['chats'] as const,
  documents: ['documents'] as const,
  messages: (chatId: string) => ['chats', chatId, 'messages'] as const,
};
