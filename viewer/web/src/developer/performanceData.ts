export type Measurements = {
  calls: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  tokens_status: string;
  active_seconds: number | null;
  active_status: string;
  agent_span_seconds: number | null;
};
export type TrendPoint = Measurements & {
  order: number; loop: number; pipeline_number?: number; replicate_number?: number;
  run_tag: string; run_tags: string[]; attempts: number;
  started_at: number | null; ended_at: number | null;
  elapsed_seconds: number | null; elapsed_status: string; attribution: string;
  agents: Record<string, Measurements>;
};
export type Trends = {
  run_tag: string; run_tags: string[]; name: string; updated_at: string;
  points: TrendPoint[]; excluded_replicates: number; unassigned_calls: number; unknown_order_count: number;
};
export const agentNames: Record<string, string> = {
  question: 'Question generation', hypothesis: 'Hypothesis', data: 'Data', ml: 'ML',
  interpretation: 'Interpretation', explanation: 'Explanation', other: 'Other',
};
export const pointLabel = (p: TrendPoint) => p.pipeline_number != null && p.replicate_number != null
  ? `Pipeline ${p.pipeline_number} · Replicate ${p.replicate_number}` : `Loop ${p.loop} · identity unavailable`;
export function pointValues(point: TrendPoint, agent: string) {
    const metric = agent === 'all' ? point : point.agents[agent];
    const span = agent === 'all' ? point.elapsed_seconds : metric?.agent_span_seconds;
    return {...point,
      active_minutes: metric?.active_seconds == null ? null : metric.active_seconds / 60,
      elapsed_minutes: span == null ? null : span / 60,
      input: metric?.input_tokens ?? null, output: metric?.output_tokens ?? null,
      total: metric?.total_tokens ?? null, selected: metric,
    };
}
export function chartPoints(points: TrendPoint[], agent: string) {
  return points.filter(p => p.started_at != null).map(point => pointValues(point, agent));
}
export type ChartPoint = ReturnType<typeof chartPoints>[number];
