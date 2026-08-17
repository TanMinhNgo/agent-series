import type { Message } from './message';

export type PublicShare = {
  token: string;
  title: string;
  provider: string;
  model: string;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
};
