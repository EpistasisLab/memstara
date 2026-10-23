/** Display-only migration of explicit legacy analysis references. Stored records,
 * code, citations, clinical trials and optimizer/retry terminology remain intact. */
export function reportLoopText(text: string, analysesPerLoop?: number): string {
  const known = Number.isInteger(analysesPerLoop) && analysesPerLoop! > 0;
  const words = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
  return text.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`|\[[^\]]*\]\([^)]*\)|https?:\/\/\S+)/g)
    .map((part, index) => index % 2 ? part : part.split('\n').map(line => {
      // These terms have distinct scientific/operational meanings, not pipeline loops.
      if (/clinical trial|randomi[sz]ed trial|search trial|hyperparameter|optimizer|retry|retries|task claim/i.test(line)) return line;
      return line.replace(/\btrial\s+#?(\d+|zero|one|two|three|four|five|six|seven|eight|nine)\b/gi, (_, raw: string) => {
        const id = /^\d+$/.test(raw) ? Number(raw) : words.indexOf(raw.toLowerCase());
        return known ? `Recorded analysis ${id} (schedule position ${Math.floor(id / analysesPerLoop!) + 1})` : `Analysis ID ${id} (replicate identity not recorded)`;
      }).replace(/\biteration\s+(\d+)\b/gi, (_, raw: string) => Number(raw) > 0 ? `Recorded schedule position ${raw}` : 'replicate identity not recorded');
    }).join('\n')).join('');
}
