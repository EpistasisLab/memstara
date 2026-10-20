import { useEffect, useRef, useState } from "react";
import { Cpu, RefreshCw, X } from "lucide-react";

import { stageModelRows, type ModelConfiguration, type StageProfiles } from "../lib/stageModels";

type Connection = { provider: string; model: string; endpoint?: string; resource?: string; source?: string; error?: string };
type Active = { id: string; name: string; configuration?: ModelConfiguration; configuration_error?: string; running?: { run_tag: string; configuration?: ModelConfiguration } };

function Assignment({configuration}: {configuration?: ModelConfiguration}) {
  return <dl className="space-y-2" aria-label="Stage model assignments">{stageModelRows(configuration).map(row =>
    <div key={row.stage} className="grid min-w-0 grid-cols-1 gap-1 sm:grid-cols-[140px_minmax(0,1fr)]">
      <dt className="text-sm text-ink-soft">{row.stage}</dt>
      <dd className="min-w-0 text-sm [overflow-wrap:anywhere]">{row.model} · {row.provider}</dd>
    </div>)}</dl>;
}

export default function ModelConnectionDialog() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ llm: Connection; pipelines: Active[]; stage_models?: StageProfiles; stage_model_error?: string } | null>(null);
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
      setData({ llm: health.llm, pipelines: workspace.pipelines ?? [], stage_models: health.stage_models, stage_model_error: health.stage_model_error });
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
        <p className="text-sm text-ink-soft">Per-agent assignments and each pipeline’s saved or active assignments. Active assignments come from its frozen execution.</p>
        {loading && <p role="status">Loading connection settings…</p>}
        {error && <p role="alert" className="text-sm">{error}</p>}
        {data && <>
          {data.llm.error && <p role="alert">{data.llm.error}</p>}
          {data.stage_model_error && <p role="alert">{data.stage_model_error}</p>}
          <section className="space-y-2"><h3 className="font-semibold">Agent model assignments</h3>
            {!data.stage_model_error && <Assignment configuration={{...data.llm, stage_models: data.stage_models}}/>}
          </section>
          <section className="space-y-2">
            <h3 className="font-semibold">Pipeline assignments</h3>
            {data.pipelines.length === 0 ? <p className="text-sm text-ink-soft">No saved pipelines.</p> : data.pipelines.map(p =>
              <div key={p.id} className="rounded-lg border border-paper-line p-3">
                <p className="font-semibold [overflow-wrap:anywhere]">{p.name}</p>
                <p className="mb-2 text-sm text-ink-soft">{p.running ? "Active execution — frozen assignments" : "Next execution — saved assignments"}</p>
                {p.configuration_error && <p role="alert">{p.configuration_error}</p>}
                <Assignment configuration={p.running ? p.running.configuration : p.configuration}/>
              </div>)}
          </section>
          <p className="text-sm text-ink-soft">Designs can be saved before a model is connected. A configured assignment does not prove connection success or execution completion. New executions use project .env settings; conflicting legacy profiles must be explicitly migrated. Restart services after editing .env. Active runs retain frozen settings. Call traces record the model actually invoked; “openai” denotes OpenAI-compatible transport.</p>
        </>}
        <button type="button" disabled={loading} onClick={() => setRevision(v => v + 1)} className="flex items-center gap-2 rounded-lg border border-paper-line px-3 py-2 text-sm disabled:opacity-50"><RefreshCw size={15} /> Refresh status</button>
      </div>
    </dialog>
  </>;
}
