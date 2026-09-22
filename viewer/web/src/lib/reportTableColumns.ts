import type { Root, RootContent, Table } from 'mdast';

/** Hide retired assessment columns in historical as well as newly generated tables. */
export function reportTableColumns() {
  return (tree: Root) => {
    const text = (node: { value?: string; children?: unknown[] }): string =>
      node.value ?? (node.children ?? []).map(child => text(child as Parameters<typeof text>[0])).join('');
    const visit = (node: Root | RootContent) => {
      if (node.type === 'table') {
        const table = node as Table;
        const remove = new Set(table.children[0]?.children.flatMap((cell, index) =>
          /\b(reproducibility|robustness)\b|재현성|재현 가능성/i.test(text(cell))
          || /^(?:recommendation\s+)?confidence$/i.test(text(cell).trim()) ? [index] : []) ?? []);
        if (remove.size) {
          for (const row of table.children) row.children = row.children.filter((_, index) => !remove.has(index));
          if (table.align) table.align = table.align.filter((_, index) => !remove.has(index));
        }
        table.children[0]?.children.forEach((cell, index) => {
          const label = text(cell).trim();
          const kind = /\b(novelty|rank|ranking|priority|prioritization|decision|recommendation|actionability|assessment|interpretation|rationale|plausibility)\b|evidence\s+(strength|quality)|next\s+(experiment|step)/i.test(label)
            ? 'judgment' : /^hypothes[ie]s$/i.test(label) ? 'proposal'
            : /^(?:roc[- ]?)?auc$/i.test(label) ? 'measured' : null;
          const note = /novelty/i.test(label) ? 'LLM judgment within consulted sources; not a systematic literature novelty check.'
            : /rank|priority|decision|recommendation/i.test(label) ? 'LLM research recommendation; not a calculated score or clinical approval.'
            : kind === 'proposal' ? 'Proposed by an agent; not an established finding.' : null;
          if (kind) for (const row of table.children) {
            const value = row.children[index];
            if (value) value.data = { ...value.data, hProperties: {
              ...value.data?.hProperties, 'data-assessment-kind': kind,
              ...(note ? { 'data-assessment-note': note } : {}),
            } };
          }
        });
      }
      if ('children' in node) for (const child of node.children) visit(child as RootContent);
    };
    visit(tree);
  };
}
