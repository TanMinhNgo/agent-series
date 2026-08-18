export const queryKeys = {
  config: ['config'] as const,
  chats: ['chats'] as const,
  chat: (chatId: string) => ['chats', chatId] as const,
  documents: ['documents'] as const,
  projects: ['projects'] as const,
  schedules: ['schedules'] as const,
  plugins: ['plugins'] as const,
  messages: (chatId: string) => ['chats', chatId, 'messages'] as const,
  templates: (projectId?: string | null) => ['templates', projectId || 'global'] as const,
  bookmarks: (projectId?: string | null) => ['bookmarks', projectId || 'all'] as const,
  messageSearch: (query: string, projectId?: string | null) =>
    ['message-search', query, projectId || 'all'] as const,
  collectionsRoot: ['knowledge-collections'] as const,
  collections: (projectId?: string | null) => ['knowledge-collections', projectId || 'none'] as const,
};
