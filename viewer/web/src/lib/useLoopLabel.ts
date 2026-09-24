import { useSnapshot } from '../store/viewer';
import { loopLabel } from './loopLabel';
/** Only use saved configuration from the execution that owns this record. */
export function useLoopLabel() {
  const snapshot = useSnapshot();
  return (record: { iteration?: number | null; trial?: number | null; run_tag?: string | null }) =>
    loopLabel(record, !record.run_tag || record.run_tag === snapshot?.run_tag ? snapshot?.run_configuration?.trials : undefined);
}
