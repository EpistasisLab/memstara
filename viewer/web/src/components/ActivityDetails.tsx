import { useEffect, useState } from 'react';
import { SnapshotScope } from '../lib/SnapshotScope';
import type { Snapshot } from '../types';
import type { OutputEvent } from '../store/liveOutputs';
import FeedPanel from '../panels/FeedPanel';
import { clinicalRoles } from '../lib/clinicalLog';

/** Read an event's scope without changing the global pipeline selection. */
export type ActivityScope = Pick<OutputEvent, 'run_tag' | 'iteration' | 'stage' | 'pipeline_name' | 'detail'>;
export default function ActivityDetails({event}: {event: ActivityScope}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');
  const loop = event.iteration ?? null;
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;
    const poll = async () => {
      request = new AbortController();
      const deadline = setTimeout(() => request.abort(), 10000);
      try {
        const response = await fetch(`/api/telemetry?run_tag=${encodeURIComponent(event.run_tag)}${loop === null ? '' : `&loop=${loop}`}&view=Activity`, {signal: request.signal});
        const body = await response.json();
        if (response.status === 202) return;
        if (!response.ok) throw Error('Detailed activity is unavailable. Retrying automatically.');
        if (body.run_tag !== event.run_tag || body.telemetry?.loop !== loop) throw Error('The activity response did not match this execution and loop.');
        if (!disposed) {setSnapshot(body); setError(body.stale ? 'Showing previously recorded activity while updates recover.' : '');}
      } catch {
        if (!disposed) setError('Detailed activity could not be loaded for this execution and loop. Retrying automatically.');
      } finally {
        clearTimeout(deadline);
        if (!disposed) timer = setTimeout(poll, 4000);
      }
    };
    void poll();
    return () => {disposed = true; clearTimeout(timer); request?.abort();};
  }, [event.run_tag, loop]);
  return <section aria-label="Activity details">
    <h4>{event.pipeline_name} · {clinicalRoles[event.stage] ?? (event.stage || 'All activity')}</h4>
    <p>{loop === null ? 'All loops' : `Loop ${loop}`} · <code>{event.run_tag}</code></p>
    <p>Recent records within the scope shown above. These may include multiple actions; they are not proof that a particular action produced this update.</p>
    {event.detail && <details><summary>Saved output excerpt</summary><p>{event.detail}</p></details>}
    {error && <p role="status">{error}</p>}
    {!snapshot && !error && <p role="status">Loading detailed activity…</p>}
    <SnapshotScope.Provider value={snapshot}>
      {snapshot && <FeedPanel stage={event.stage || undefined}/>}
    </SnapshotScope.Provider>
  </section>;
}
