import NoveltyEvidence from './NoveltyEvidence';
import { knowledgeProvenance } from '../lib/knowledgeProvenance';

export default function KnowledgeProvenance({ value }: { value: unknown }) {
  const record = knowledgeProvenance(value);
  return <details className="mt-3" data-testid="knowledge-provenance">
    <summary>Knowledge-source provenance</summary>
    <p className="mt-2">Document annotations alone are not a novelty score or proof of a new discovery. The path panel below shows declared use and the calculated proxy when available; scientific support has not been independently verified.</p>
    <NoveltyEvidence value={value && typeof value === 'object' ? (value as Record<string, unknown>).novelty : null}/>
    {!record ? <p>No structured source provenance was recorded for this result.</p>
      : record.empty ? <p>No knowledge sources were declared. This does not mean low novelty.</p>
      : !record.sources.length ? <p>Source details are unavailable.</p>
      : <ul className="mt-2 space-y-2">{record.sources.map((source, index) => <li key={`${source.ref}-${index}`} style={{overflowWrap:'anywhere'}}>
        <strong>{source.label}</strong><br /><span>{source.ref}</span>
        {source.pathCount !== null && <p>{source.pathCount > 0
          ? `${source.pathCount} path rows identified in the full source document; use by this hypothesis and individual edge provenance are not verified.`
          : 'No supported path-instance table was identified; this does not indicate low novelty.'}</p>}
        {!!source.diagnostics.length && <p>Verification notes: {source.diagnostics.join(', ')}</p>}
        {source.fingerprint && <small>Recorded source fingerprint: {source.fingerprint}</small>}
      </li>)}</ul>}
    {record && record.total > record.sources.length && <p>Showing {record.sources.length} of {record.total} recorded sources.</p>}
  </details>;
}
