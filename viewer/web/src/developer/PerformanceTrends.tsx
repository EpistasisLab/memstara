import {useEffect, useMemo, useState} from 'react';
import {Brush, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {agentNames, chartPoints, pointLabel, pointValues, type ChartPoint, type Trends} from './performanceData';
import './performance-trends.css';

type Choice = {run_tag: string; name: string};
const count = (n: number | null | undefined) => n == null ? 'Not recorded' : n.toLocaleString();
const minutes = (n: number | null | undefined) => n == null ? 'Not recorded' : `${n.toFixed(2)} min`;
const timestamp = (n: number | null) => n == null ? 'Not recorded' : new Date(n * 1000).toLocaleString();
const compact = (n: number) => Intl.NumberFormat('en', {notation: 'compact'}).format(n);

async function read<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, {signal, cache: 'no-store'});
  if (!response.headers.get('content-type')?.includes('application/json')) throw Error('The read API returned an unreadable response. Refresh to retry.');
  const body = await response.json();
  if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : `Measurements unavailable (HTTP ${response.status}).`);
  return body as T;
}

function PointTooltip({active, payload}: {active?: boolean; payload?: readonly {payload?: ChartPoint}[]}) {
  const p = payload?.[0]?.payload;
  if (!active || !p) return null;
  return <div className="trend-tooltip"><strong>#{p.order} · {pointLabel(p)}</strong>
    <p>{timestamp(p.started_at)}</p><dl>
      <dt>Agent activity</dt><dd>{minutes(p.active_minutes)}</dd>
      <dt>Elapsed / span</dt><dd>{minutes(p.elapsed_minutes)}</dd>
      <dt>Input tokens</dt><dd>{count(p.input)}</dd><dt>Output tokens</dt><dd>{count(p.output)}</dd>
      <dt>Total tokens</dt><dd>{count(p.total)}</dd><dt>Agent executions</dt><dd>{count(p.selected?.calls)}</dd>
    </dl><p>Usage: {p.selected?.tokens_status ?? 'unavailable'} · activity: {p.selected?.active_status ?? 'unavailable'}</p>
    <p>{p.attempts} recorded attempt(s) · attribution: {p.attribution}</p><code>{p.run_tag}</code>
  </div>;
}

function TrendChart({data, kind, agent}: {data: ChartPoint[]; kind: 'time' | 'tokens'; agent: string}) {
  const time = kind === 'time';
  const series = time
    ? [{key: 'active_minutes', name: 'Recorded agent activity', color: '#2563eb'},
       {key: 'elapsed_minutes', name: agent === 'all' ? 'Elapsed including waits / pauses' : 'First-to-last agent span', color: '#d97706'}]
    : [{key: 'input', name: 'Input tokens', color: '#2563eb'}, {key: 'output', name: 'Output tokens', color: '#059669'},
       {key: 'total', name: 'Total tokens', color: '#7c3aed'}];
  return <section className="trend-card" aria-label={time ? 'Execution time chart' : 'Token usage chart'}>
    <h2>{time ? 'Execution time' : 'LLM token usage'}</h2>
    <p>{time ? 'Minutes per completed replicate. Parallel agent intervals are counted once.' : 'Recorded Motoro input and output tokens, including failed attempts before completion.'}</p>
    <div className="trend-chart"><ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} syncId="developer-performance" margin={{top: 12, right: 24, left: 12, bottom: 12}} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dbe3ed"/>
        <XAxis dataKey="order" minTickGap={26} height={32}/>
        <YAxis tickFormatter={compact} width={65} domain={[0, 'auto']} label={{value: time ? 'Minutes' : 'Tokens', angle: -90, position: 'insideLeft'}}/>
        <Tooltip content={<PointTooltip/>}/><Legend verticalAlign="top" height={44}/>
        {series.map(s => <Line key={s.key} dataKey={s.key} name={s.name} stroke={s.color} type="linear" strokeWidth={2}
          dot={{r: 2.5}} activeDot={{r: 5}} connectNulls={false} isAnimationActive={false}/>)}
        {data.length > 20 && <Brush dataKey="order" height={24} stroke="#64748b" travellerWidth={10}/>}
      </LineChart>
    </ResponsiveContainer></div>
    <p className="trend-axis-caption">Replicate execution order · first recorded start</p>
  </section>;
}

export default function PerformanceTrends() {
  const [choices, setChoices] = useState<Choice[]>([]);
  const [catalogError, setCatalogError] = useState('');
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [tag, setTag] = useState('');
  const [data, setData] = useState<Trends | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [auto, setAuto] = useState(false);
  const [agent, setAgent] = useState('all');
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    const deadline = setTimeout(() => controller.abort(), 25000);
    read<{experiments: Choice[]}>('/api/developer/trends/catalog', controller.signal)
      .then(result => {if (!disposed) {setChoices(result.experiments); setCatalogError('');}})
      .catch(e => {if (!disposed) setCatalogError(e instanceof Error ? e.message : 'Experiment list unavailable');})
      .finally(() => clearTimeout(deadline));
    return () => {disposed = true; clearTimeout(deadline); controller.abort();};
  }, [catalogRevision]);
  useEffect(() => {
    if (!tag) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function load() {
      if (disposed) return;
      if (document.hidden) {timer = setTimeout(load, 30000); return;}
      controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), 25000);
      setBusy(true);
      try {
        const next = await read<Trends>(`/api/developer/trends?run_tag=${encodeURIComponent(tag)}`, controller.signal);
        if (next.run_tag !== tag || !Array.isArray(next.points)) throw Error('The measurements do not match the selected execution.');
        if (!disposed) {setData(next); setError('');}
      } catch (e) {
        if (!disposed) setError(e instanceof Error && e.name !== 'AbortError' ? e.message : 'The read request timed out. Refresh to retry.');
      } finally {
        clearTimeout(deadline);
        if (!disposed) {setBusy(false); if (auto) timer = setTimeout(load, 30000);}
      }
    }
    void load();
    return () => {disposed = true; clearTimeout(timer); controller?.abort();};
  }, [tag, revision, auto]);
  const current = data?.run_tag === tag ? data : null;
  const points = useMemo(() => chartPoints(current?.points ?? [], agent), [current, agent]);
  const agents = useMemo(() => [...new Set((current?.points ?? []).flatMap(p => Object.keys(p.agents)))].sort(), [current]);
  return <main className="performance-trends">
    <header className="trend-header"><div><p className="trend-eyebrow">MEMSTARA / DEVELOPER DIAGNOSTICS</p>
      <h1>Execution performance</h1><p>Follow time and token usage across completed pipeline replicates.</p></div><a href="/">Open workspace ↗</a></header>
    <section className="trend-controls" aria-label="Performance filters">
      <label>Experiment / continuation chain<select value={tag} onChange={e => {setTag(e.target.value); setData(null); setError(''); setAgent('all');}}>
        <option value="">Choose an experiment</option>{choices.map(c => <option key={c.run_tag} value={c.run_tag}>{c.name} · {c.run_tag}</option>)}
      </select></label>
      <label>Agent<select aria-label="Agent" value={agent} onChange={e => setAgent(e.target.value)}><option value="all">All agents</option>{agents.map(a => <option key={a} value={a}>{agentNames[a] ?? a}</option>)}</select></label>
      <button disabled={!tag || busy} onClick={() => setRevision(n => n + 1)}>{busy ? 'Loading…' : 'Refresh measurements'}</button>
      <button onClick={() => setCatalogRevision(n => n + 1)}>Reload experiment list</button>
      <label className="trend-auto"><input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)}/>Refresh every 30 seconds</label>
    </section>
    {catalogError && <p className="trend-notice" role="alert">Experiment list: {catalogError}</p>}
    {error && <p className="trend-notice" role="alert">{error} {current ? 'Previously loaded measurements are retained and may be stale.' : ''}</p>}
    {!tag && <p className="trend-empty">Choose an experiment to load measurements. No experiment is started by this page.</p>}
    {busy && !current && <p role="status" className="trend-empty">Loading recorded measurements…</p>}
    {current && <>
      <section className="trend-summary" aria-label="Measurement scope"><div><strong>{current.points.length}</strong><span>completed replicates</span></div>
        <div><strong>{current.run_tags.length}</strong><span>linked executions</span></div><div><strong>{current.excluded_replicates}</strong><span>unfinished / unknown excluded</span></div>
        <div><strong>{current.points.filter(p => p.tokens_status !== 'complete').length}</strong><span>replicates with incomplete usage</span></div>
      </section>
      <p className="trend-note"><strong>{current.name}</strong> · Updated {new Date(current.updated_at).toLocaleString()}. One point = one completed Pipeline / Replicate, including prior attempts in its explicit continuation chain. Independent fresh experiments stay separate.</p>
      {current.unknown_order_count > 0 && <p className="trend-notice">{current.unknown_order_count} completed replicates have no recorded start. They appear in the table but are omitted from the ordered charts.</p>}
      {points.length ? <div className="trend-charts"><TrendChart data={points} kind="time" agent={agent}/><TrendChart data={points} kind="tokens" agent={agent}/></div>
        : <p className="trend-empty">No completed replicates with a recorded start are available for this selection.</p>}
      <details className="trend-method"><summary>Measurement definitions and limitations</summary>
        <ul><li><strong>Recorded agent activity:</strong> union of recorded call intervals. Includes tools and waits inside an agent call; excludes gaps between calls. This is not CPU time or an exact pause-subtracted pipeline duration.</li>
          <li><strong>Elapsed:</strong> earliest recorded start to final completed attempt end, including retry gaps, waits and pauses. Agent filtering shows that agent's first-to-last recorded span instead.</li>
          <li><strong>Tokens:</strong> distinct Motoro agent-run input / output totals. Failed attempts before completion are included. Partial records are labeled; missing values create gaps, never zeroes.</li>
          <li><strong>Order:</strong> first recorded start, not Pipeline number or completion order. Resume history is linked using saved lineage, not the experiment name.</li>
          <li><strong>Unassigned activity:</strong> {current.unassigned_calls} invocation(s), including any execution-wide reporting, are excluded from replicate charts.</li>
        </ul>
      </details>
      <details className="trend-method"><summary>Recorded values and source executions</summary><div className="trend-table" tabIndex={0} role="region" aria-label="Recorded performance values">
        <table><thead><tr>{['Order', 'Pipeline / Replicate', 'First start', 'Agent activity (min)', 'Elapsed / span (min)', 'Input tokens', 'Output tokens', 'Total tokens', 'Quality', 'Source executions'].map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{current.points.map(p => {const v = pointValues(p, agent); return <tr key={p.loop}>
            <td>{p.started_at == null ? 'Unknown' : p.order}</td><th scope="row">{pointLabel(p)}</th><td>{timestamp(p.started_at)}</td>
            <td>{minutes(v.active_minutes)}</td><td>{minutes(v.elapsed_minutes)}</td><td>{count(v.input)}</td><td>{count(v.output)}</td><td>{count(v.total)}</td>
            <td>Tokens: {v.selected?.tokens_status ?? 'unavailable'}; activity: {v.selected?.active_status ?? 'unavailable'}; elapsed / span: {agent === 'all' ? p.elapsed_status : v.selected?.active_status ?? 'unavailable'}; attribution: {p.attribution}</td>
            <td>{p.run_tags.map(t => <code key={t}>{t}</code>)}</td></tr>;})}</tbody></table>
      </div></details>
    </>}
    <footer className="trend-note">Read-only diagnostic view. Hidden from workspace navigation; protected by the deployment's existing login, not a separate developer role. No prompts, dataset rows or model outputs are returned by this view.</footer>
  </main>;
}
