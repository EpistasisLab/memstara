/** Reject incomplete responses; never replace missing usage with zero. */
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function metric(value: unknown): boolean {
  return record(value) && Number.isFinite(value.calls) && Number.isFinite(value.tokens)
    && record(value.cost) && Number.isFinite(value.cost.usd)
    && typeof value.cost.status === 'string' && Number.isFinite(value.cost.missing_costs);
}

export function validateTelemetryResponse(value: unknown): void {
  if (!record(value) || !metric(value.total)
    || !Array.isArray(value.pipelines) || !value.pipelines.every(row =>
      metric(row) && typeof row.id === 'string' && typeof row.name === 'string')
    || !Array.isArray(value.executions) || !value.executions.every(row =>
      metric(row) && typeof row.run_tag === 'string'
      && Array.isArray(row.loops) && row.loops.every(metric))) {
    throw new Error('Usage response is incomplete. Waiting for valid measurements.');
  }
}
