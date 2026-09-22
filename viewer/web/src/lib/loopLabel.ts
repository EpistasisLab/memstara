/** Display iterations consistently without mistaking a task claim or HP candidate for a loop. */
export function loopLabel(record: { iteration?: number | null; trial?: number | null }, analysesPerLoop?: number | null): string {
  if (Number.isInteger(record.iteration) && record.iteration! > 0) return `Loop ${record.iteration}`;
  if (Number.isInteger(record.trial) && record.trial! >= 0 && Number.isInteger(analysesPerLoop) && analysesPerLoop! > 0)
    return `Loop ${Math.floor(record.trial! / analysesPerLoop!) + 1}`;
  return 'Loop —';
}

/** The denominator is a configured ceiling, not a promise that every Loop succeeds. */
export function executionLoopLabel(iteration: number | undefined, limit: number | null | undefined,
  started: boolean, continuous = false): string {
  const current = !started ? '0' : Number.isInteger(iteration) && iteration! > 0 ? String(iteration) : '—';
  if (continuous) return `Loop ${current} · Continuous`;
  const total = Number.isInteger(limit) && limit! > 0 ? String(limit) : '—';
  return `Loop ${current} / ${total}`;
}
