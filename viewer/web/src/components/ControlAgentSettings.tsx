import { usePipelines } from "../store/pipelines";
import { useEffect, useState } from "react";
import { Plus, Settings2, Trash2, Lightbulb, ChartNoAxesCombined, ScanText, FileText, LockKeyhole } from "lucide-react";
import { asSlots, MAX_HYPOTHESIS_AGENTS, withoutSlot, withoutInterpreterSlot } from "../lib/planned";
import { applyRunConfiguration, useControl, type RunRequest } from "../store/control";

/** Shared editor and persisted draft keep the control panel and pipeline in sync. */
export default function ControlAgentSettings({ form }: { form: RunRequest }) {
  const independent = usePipelines(s => !!s.selected);
  const catalog = useControl(s => s.catalog);
  const open = useControl(s => s.openEditor);
  const setForm = useControl(s => s.setForm);
  const running = useControl(s => s.running);
  const busy = useControl(s => s.busy);
  const [removing, setRemoving] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const displayed = running?.configuration ? applyRunConfiguration(form, running.configuration) : form;
  const locked = !!running || busy;
  useEffect(() => { setRemoving(null); }, [form, running?.run_tag]);
  const stages = [
    { id: "hypothesis", label: "Hypothesis", description: "Discover candidate explanations", icon: Lightbulb, color: "text-stage-hypothesis", count: displayed.hypothesis_agents, maximum: independent ? 1 : MAX_HYPOTHESIS_AGENTS },
    { id: "ml", label: "Machine learning", description: "Evaluate predictive evidence", icon: ChartNoAxesCombined, color: "text-stage-ml", count: 1, maximum: 1 },
    { id: "interpreter", label: "Interpreter", description: "Explain findings and limitations", icon: ScanText, color: "text-stage-interpreter", count: displayed.interpret_agents, maximum: independent ? 1 : 4 },
    { id: "report", label: "Report", description: "Compare and recommend hypotheses", icon: FileText, color: "text-stage-report", count: 1, maximum: 1 },
  ] as const;
  return <section aria-label="Agent settings" className="overflow-hidden rounded-xl border border-paper-line bg-paper-panel">
    <header className="border-b border-paper-line px-3 py-3">
      <h3 className="text-sm font-bold text-ink">Your agent team</h3>
      <p className="mt-1 text-xs leading-relaxed text-ink-soft">Give each agent a skill and a distinct perspective.</p>
    </header>
    {locked && <p className="mx-3 mt-3 flex items-start gap-2 rounded-lg bg-paper p-2 text-xs leading-relaxed text-ink-soft">
      <LockKeyhole size={14} className="mt-0.5 shrink-0" />
      {running ? "Settings are locked during exploration. Stop before making changes." : "Applying changes…"}
    </p>}
    <div className="divide-y divide-paper-line">{stages.map(stage => {
      const books = asSlots(displayed[`playbook_${stage.id}`], stage.count);
      return <div key={stage.id} className="space-y-2.5 p-3">
        <div className="flex items-start gap-2">
          <stage.icon size={17} aria-hidden="true" className={`mt-0.5 shrink-0 ${stage.color}`} />
          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-semibold text-ink">{stage.label}</h4>
            <p className="mt-0.5 text-xs leading-relaxed text-ink-faint">{stage.description}</p>
          </div>
          <span aria-label={`${stage.count} ${stage.label.toLowerCase()} agents${stage.maximum > 1 ? `, maximum ${stage.maximum}` : ""}`}
            className="shrink-0 rounded-full border border-paper-line px-2 py-0.5 text-xs tabular-nums text-ink-soft">
            {stage.maximum > 1 ? `${stage.count} / ${stage.maximum}` : "1"}
          </span>
        </div>
        <div className="space-y-2">{books.map((book, slot) => {
          const key = `${stage.id}-${slot}`;
          const name = `${stage.label}${stage.maximum > 1 ? ` ${slot + 1}` : ""}`;
          const skill = catalog.find(item => item.id === book);
          return <div key={key} className="overflow-hidden rounded-lg border border-paper-line bg-paper">
            <div className="flex items-stretch">
              <button type="button" disabled={locked} aria-label={`Configure ${stage.label.toLowerCase()} ${slot + 1}`}
                onClick={() => { setRemoving(null); open(stage.id, slot); }}
                className="group min-w-0 flex-1 p-2.5 text-left transition-colors hover:bg-paper-panel focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-[-2px] disabled:cursor-not-allowed">
                <span className="flex items-center gap-2 text-xs font-semibold text-ink-soft">{name}</span>
                <span className="mt-1 block break-words text-sm font-medium leading-snug text-ink">{skill?.title || book || "Default instructions"}</span>
                <span className="mt-2 flex items-center gap-1 text-xs text-ink-faint group-hover:text-ink"><Settings2 size={12} aria-hidden="true" />{stage.id === "ml" ? "Skill & model settings" : "Choose or upload skill"}</span>
              </button>
              {stage.maximum > 1 && <button type="button" disabled={locked || stage.count <= 1}
                aria-label={`Remove ${name.toLowerCase()}`} title={stage.count <= 1 ? `Keep at least one ${stage.label.toLowerCase()} agent` : `Remove ${name.toLowerCase()}`}
                onClick={() => setRemoving(removing === key ? null : key)}
                className="my-2 mr-1 flex w-9 shrink-0 items-center justify-center self-start rounded-md py-2 text-ink-faint transition-colors hover:bg-red-500/10 hover:text-red-600 focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-30">
                <Trash2 size={15} aria-hidden="true" />
              </button>}
            </div>
            {removing === key && <div className="border-t border-paper-line bg-paper-panel p-2.5" role="group" aria-label={`Confirm removal of ${name.toLowerCase()}`}>
              <p className="text-xs leading-relaxed text-ink-soft">Remove {name.toLowerCase()} from this setup? Its skill file stays available.</p>
              <div className="mt-2 flex flex-wrap justify-end gap-2">
                <button type="button" onClick={() => setRemoving(null)} className="rounded-md border border-paper-line px-3 py-1.5 text-xs text-ink">Keep agent</button>
                <button type="button" disabled={locked || stage.count <= 1} onClick={() => {
                  if (locked || stage.count <= 1) return;
                  setForm(f => stage.id === "hypothesis" ? withoutSlot(f, slot) : withoutInterpreterSlot(f, slot));
                  setRemoving(null); setNotice(`${name} removed from the setup.`);
                }} className="rounded-md bg-red-700 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40">Remove agent</button>
              </div>
            </div>}
          </div>;
        })}</div>
        {stage.maximum > 1 && <button type="button" disabled={locked || stage.count >= stage.maximum}
          aria-label={`Add ${stage.label.toLowerCase()} agent`}
          onClick={() => { setRemoving(null); open(stage.id, stage.count, true); }}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-paper-line px-2 py-2 text-xs font-medium text-ink-soft transition-colors hover:border-accent hover:bg-accent/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40">
          <Plus size={14} aria-hidden="true" />{stage.count >= stage.maximum ? "Agent limit reached" : `Add ${stage.label.toLowerCase()} agent`}
        </button>}
      </div>;
    })}</div>
    <footer className="border-t border-paper-line px-3 py-2.5 text-xs leading-relaxed text-ink-faint">
      Synced with the pipeline. Data extraction is managed automatically.
      <span role="status" aria-live="polite" className="mt-1 block text-ink-soft">{notice}</span>
    </footer>
  </section>;
}
