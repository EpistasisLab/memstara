import { useEffect, useRef, useState } from "react";
import { Cpu, RefreshCw, X } from "lucide-react";

type Connection = { provider: string; model: string; endpoint?: string; resource?: string; source?: string; error?: string };
type Active = { name: string; running?: { run_tag: string; configuration?: { provider?: string; model?: string } } };

export default function ModelConnectionDialog() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ llm: Connection; pipelines: Active[] } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    setLoading(true); setError(""); setData(null);
    async function read(path: string) {
      const response = await fetch(path, { signal: controller.signal });
      if (!response.ok) throw new Error("Connection settings could not be loaded. Please retry.");
      return response.json();
    }
    Promise.all([read("/control/health"), read("/control/pipelines")]).then(([health, workspace]) => {
      if (controller.signal.aborted) return;
      if (!health.llm) throw new Error("Model settings are unavailable. Refresh the control service.");
      setData({ llm: health.llm, pipelines: (workspace.pipelines ?? []).filter((p: Active) => p.running) });
    }).catch(e => { if (dialog.current?.open) setError(e.name === "AbortError" ? "The service did not respond in time. Please retry." : e.message); })
      .finally(() => { clearTimeout(timeout); if (!controller.signal.aborted || dialog.current?.open) setLoading(false); });
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [open, revision]);
  return <>
    <button type="button" className="workspace-action flex items-center gap-2" onClick={() => { dialog.current?.showModal(); setOpen(true); }}>
      <Cpu size={16} /> Model connection
    </button>
    <dialog ref={dialog} aria-labelledby="model-connection-heading" onClose={() => setOpen(false)}
      className="m-auto max-h-[85dvh] w-[min(640px,calc(100vw-24px))] overflow-auto rounded-2xl border border-paper-line bg-panel p-0 text-ink shadow-2xl backdrop:bg-black/50"
      style={{ background: "rgb(var(--panel))", color: "rgb(var(--ink))" }}>
      <header className="flex items-center justify-between gap-3 border-b border-paper-line p-5">
        <h2 id="model-connection-heading" className="text-lg font-bold">Model connection</h2>
        <button type="button" aria-label="Close model connection" onClick={() => dialog.current?.close()} className="rounded-lg p-2"><X size={20} /></button>
      </header>
      <div className="space-y-5 p-5" aria-busy={loading}>
        <p className="text-sm text-ink-soft">Server configuration used for new executions.</p>
        {loading && <p role="status">Loading connection settings…</p>}
        {error && <p role="alert" className="text-sm">{error}</p>}
        {data && <>
          {data.llm.error && <p role="alert">{data.llm.error}</p>}
          <dl className="space-y-3">
            {[["Deployment model", data.llm.model], ["Connection provider", data.llm.provider], ["Azure resource", data.llm.resource],
              ["Endpoint", data.llm.endpoint], ["Configuration source", data.llm.source]].map(([label, value]) =>
              <div key={label} className="grid grid-cols-1 gap-1 border-b border-paper-line pb-3 sm:grid-cols-[150px_minmax(0,1fr)]">
                <dt className="text-sm text-ink-soft">{label}</dt><dd className="min-w-0 break-words text-sm font-semibold [overflow-wrap:anywhere]">{value || "Not configured"}</dd>
              </div>)}
          </dl>
          <section className="space-y-2">
            <h3 className="font-semibold">Running pipelines</h3>
            {data.pipelines.length === 0 ? <p className="text-sm text-ink-soft">No pipelines are running.</p> : data.pipelines.map(p =>
              <div key={p.running!.run_tag} className="rounded-lg border border-paper-line p-3">
                <p className="font-semibold [overflow-wrap:anywhere]">{p.name}</p>
                <p className="text-sm text-ink-soft">{p.running?.configuration?.model || "Model not recorded"} · {p.running?.configuration?.provider || "Provider not recorded"}</p>
              </div>)}
          </section>
          <p className="text-sm text-ink-soft">The provider “openai” denotes OpenAI-compatible transport. The endpoint determines whether requests go to Azure. Editing .env requires a service restart; running pipelines retain their existing settings.</p>
        </>}
        <button type="button" disabled={loading} onClick={() => setRevision(v => v + 1)} className="flex items-center gap-2 rounded-lg border border-paper-line px-3 py-2 text-sm disabled:opacity-50"><RefreshCw size={15} /> Refresh status</button>
      </div>
    </dialog>
  </>;
}
