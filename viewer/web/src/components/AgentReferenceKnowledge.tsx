import { useControl } from '../store/control';

export default function AgentReferenceKnowledge() {
  const references = useControl(s => s.references);
  if (!references.length) return null;
  return <section aria-label="ML reference knowledge" className="mt-4 rounded-lg border border-paper-line bg-paper-panel p-3 text-sm">
    <h3 className="font-semibold">ML reference knowledge</h3>
    <p className="mt-1 text-ink-muted">Automatically included alongside your selected ML skill for new executions. This explains tools; it is not a skill or a model setting.</p>
    {references.filter(r => r.stage === 'ml').map(r => <details key={r.id} className="mt-3">
      <summary className="cursor-pointer font-medium break-words">{r.title}</summary>
      <p className="mt-2 text-xs text-ink-muted">{r.source} · version {r.hash.slice(0, 12)}</p>
      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words font-sans text-xs leading-relaxed">{r.content}</pre>
    </details>)}
  </section>;
}
