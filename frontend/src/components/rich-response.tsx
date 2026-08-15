import { useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import { Check, Copy } from 'lucide-react';
import 'katex/dist/katex.min.css';

import { ResponseBlocks } from '@/src/components/response-blocks';
import type { ResponseBlock } from '@/src/types';

function CodeBlock({ children, className }: { children?: ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, '');
  const copy = async () => {
    await navigator.clipboard?.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  if (!className)
    return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[.88em]">{children}</code>;
  return (
    <span className="relative my-4 block overflow-hidden rounded-xl border bg-background">
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute right-2 top-2 rounded-md border bg-card p-1.5 text-muted-foreground hover:text-foreground"
        aria-label="Sao chép mã"
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
      </button>
      <code className={`${className} block overflow-x-auto p-4 pr-12 font-mono text-sm leading-6`}>
        {children}
      </code>
    </span>
  );
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-4 mt-7 text-2xl font-semibold tracking-tight first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-3 mt-6 text-xl font-semibold tracking-tight first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold first:mt-0">{children}</h3>,
  p: ({ children }) => <p className="my-3 first:mt-0 last:mb-0">{children}</p>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-primary underline underline-offset-4 hover:opacity-80"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-2 border-primary pl-4 text-muted-foreground">{children}</blockquote>
  ),
  hr: () => <hr className="my-5 border-border" />,
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-xl border">
      <table className="w-full min-w-max text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/60 text-left">{children}</thead>,
  th: ({ children }) => <th className="border-b px-3 py-2 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b px-3 py-2 last:border-b-0">{children}</td>,
  pre: ({ children }) => <>{children}</>,
  code: ({ children, className }) => <CodeBlock className={className}>{children}</CodeBlock>,
};

export function RichResponse({ content, blocks = [] }: { content: string; blocks?: ResponseBlock[] }) {
  // KaTeX's inline fractions are deliberately compact.  The chat uses a display-style
  // fraction so labels such as "Cạnh đối" and "Cạnh kề" have readable clearance.
  const spaciousFractions = content.replace(/\\frac(?=\s*\{)/g, '\\dfrac');
  return (
    <div className="rich-response min-w-0 text-[.95rem] leading-7">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={components}
      >
        {spaciousFractions}
      </ReactMarkdown>
      {blocks.length ? <ResponseBlocks blocks={blocks} /> : null}
    </div>
  );
}
