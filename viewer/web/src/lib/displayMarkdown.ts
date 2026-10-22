import type { Root, RootContent } from 'mdast';
import { displayText } from './displayText.ts';

/** Format rendered text without modifying source Markdown or link destinations. */
export function displayMarkdown() {
  return (tree: Root) => {
    const visit = (node: Root | RootContent) => {
      if (node.type === 'text' || node.type === 'inlineCode' || node.type === 'code') {
        node.value = displayText(node.value);
      }
      if ('title' in node && node.title) node.title = displayText(node.title);
      if ('alt' in node && node.alt) node.alt = displayText(node.alt);
      if ('children' in node) for (const child of node.children) visit(child as RootContent);
    };
    visit(tree);
  };
}
