/** Some agents wrap the entire document in a Markdown fence. Unwrap only that
 * transport wrapper; leave code examples and inline backticks untouched. */
export function reportMarkdown(text: string): string {
  const trimmed = text.trim();
  const fenced = /^```(?:markdown|md)\s*\r?\n([\s\S]*?)\r?\n```$/i.exec(trimmed);
  return fenced ? fenced[1] : text;
}
