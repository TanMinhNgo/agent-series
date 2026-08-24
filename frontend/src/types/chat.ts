export type Chat = {
  id: string;
  title: string;
  provider: string;
  model: string;
  updatedAt: string;
  pinned: boolean;
  archived: boolean;
  isUnread: boolean;
  contextSourceChatId: string | null;
  projectId: string | null;
  parentChatId: string | null;
  branchFromPosition: number | null;
  collectionId: string | null;
};
