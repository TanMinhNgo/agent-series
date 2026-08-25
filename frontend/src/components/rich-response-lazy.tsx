import { lazy, Suspense } from 'react';

import type { ResponseBlock } from '@/src/types';

const RichResponse = lazy(() =>
  import('@/src/components/rich-response').then(({ RichResponse: Component }) => ({ default: Component })),
);

function RichResponseFallback({ content }: { content: string }) {
  return <p className="whitespace-pre-wrap text-[.95rem] leading-7">{content}</p>;
}

export function RichResponseLazy({
  content,
  blocks = [],
  onScheduleProposalAction,
}: {
  content: string;
  blocks?: ResponseBlock[];
  onScheduleProposalAction?: (proposalId: string, action: 'confirm' | 'dismiss') => void;
}) {
  return (
    <Suspense fallback={<RichResponseFallback content={content} />}>
      <RichResponse content={content} blocks={blocks} onScheduleProposalAction={onScheduleProposalAction} />
    </Suspense>
  );
}
