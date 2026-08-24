function tableLineToText(line: string): string | null {
  if (!/^\s*\|.*\|\s*$/.test(line)) return null;
  const cells = line
    .trim()
    .slice(1, -1)
    .split('|')
    .map((cell) => cell.trim());
  if (cells.every((cell) => /^:?-{3,}:?$/.test(cell))) return '';
  return cells.join('\t');
}

/** Convert a Markdown chat answer into text that can be pasted into a document. */
export function markdownToPlainText(markdown: string): string {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const plainLines = lines.map((line) => {
    if (/^\s*```/.test(line)) return '';

    const tableLine = tableLineToText(line);
    if (tableLine !== null) return tableLine;

    return line
      .replace(/^\s{0,3}#{1,6}\s+/, '')
      .replace(/^\s*>\s?/, '')
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '$1 ($2)')
      .replace(/\[([^\]]+)\]\(([^\s)]+)(?:\s+['"][^'"]*['"])?\)/g, '$1 ($2)')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/(\*\*|__)(.*?)\1/g, '$2')
      .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '$1')
      .replace(/(?<!_)_([^_]+)_(?!_)/g, '$1');
  });

  return plainLines
    .join('\n')
    .replace(/^\s*(?:[-*_]\s*){3,}$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
