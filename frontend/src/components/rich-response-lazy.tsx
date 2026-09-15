import { RichResponse } from '@/src/components/rich-response';
import type { ResponseBlock } from '@/src/types';

export function RichResponseLazy({
  content,
  blocks = [],
  onScheduleProposalAction,
}: {
  content: string;
  blocks?: ResponseBlock[];
  onScheduleProposalAction?: (proposalId: string, action: 'confirm' | 'dismiss') => void;
}) {
  return <RichResponse content={content} blocks={blocks} onScheduleProposalAction={onScheduleProposalAction} />;
}
