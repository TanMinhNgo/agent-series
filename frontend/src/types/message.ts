import type { MediaAttachment } from './media';

export type ResponseBlock =
  | { type: 'trig-circle'; config: { angle?: number; radius?: number; title?: string } }
  | {
      type: 'chart';
      config: {
        title?: string;
        kind?: 'line' | 'bar';
        labels?: string[];
        series?: { label?: string; values?: number[]; color?: string }[];
      };
    }
  | { type: 'data-table'; config: { title?: string; columns?: string[]; rows?: (string | number)[][] } };

export type Message = {
  messageId?: string;
  position?: number;
  createdAt?: string;
  role: 'user' | 'assistant';
  content: string;
  attachments?: MediaAttachment[];
  contentBlocks?: ResponseBlock[];
  sources?: { name: string; url: string }[];
  feedbackKind?: 'helpful' | 'incorrect' | 'too_long' | 'too_short' | 'unclear' | 'wrong_style';
  pinned?: boolean;
  /** Present only while a locally queued turn has not been confirmed by the API. */
  optimistic?: boolean;
};
