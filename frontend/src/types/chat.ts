export type Chat = {
  id: string;
  title: string;
  provider: string;
  model: string;
  updatedAt: string;
  pinned: boolean;
  archived: boolean;
  contextSourceChatId: string | null;
  projectId: string | null;
};
