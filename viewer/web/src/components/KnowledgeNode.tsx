import { useRef } from "react";
import { createPortal } from "react-dom";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BookOpen, Lock, X } from "lucide-react";
import KnowledgeSelect from "./KnowledgeSelect";
import { useControl } from "../store/control";

export default function KnowledgeNode({ data }: NodeProps) {
  const { value, locked, saved, onChange, description, compact, researchId, knowledgeMode } = data as {
    value: string | null; locked: boolean; saved: boolean; description?: string; compact?: boolean; researchId?:string; knowledgeMode?:string; onChange: (value: string) => void;
  };
  const dialog = useRef<HTMLDialogElement>(null);
  const skills = useControl(s => s.skills);
  const bundle = useControl(s => s.bundle);
  const selected = skills.find(s => s.skill === value);
  const modelOnly = knowledgeMode === 'llm_only';
  const label = modelOnly ? 'Model knowledge · no retrieval' : researchId ? `Research corpus · ${researchId.slice(0,8)}` : value === null ? "Not recorded for this run" : value === "" ? "All available knowledge" : selected?.label ?? value;
  const documents = modelOnly || researchId ? undefined : value === "" ? bundle?.documents : selected?.documents;
  return <>
    <button type="button" onClick={() => dialog.current?.showModal()}
      aria-label={`Knowledge sources: ${label}. ${locked ? "View details" : "Choose sources"}`}
      className={compact ? "floor-resource nodrag nopan h-[108px] w-[184px] rounded-xl border border-paper-line bg-white p-3 text-left text-ink" : "nodrag nopan w-[280px] rounded-2xl border border-paper-line bg-white p-4 text-left text-ink shadow-xs transition-shadow hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"}>
      <div className={compact?"mb-2 flex items-center gap-2 text-ink-soft":"mb-3 flex items-center gap-2 text-ink-soft"}><BookOpen size={20} /><span className={compact?"text-sm font-bold":"text-base font-bold"}>Knowledge sources</span></div>
      <p title={label} className={compact?"truncate text-xs font-semibold":"break-words text-sm font-semibold"}>{label}</p>
      {!compact && documents != null && <p className="mt-1 text-xs text-ink-faint">{documents} documents in the current catalog</p>}
      {!compact&&<p className="mt-3 text-xs leading-relaxed text-ink-soft">{description ?? "Evidence shared by all hypothesis agents."}</p>}
      <span className={compact?"mt-2 flex items-center gap-1 text-xs font-semibold":"mt-4 flex items-center gap-1 text-xs font-semibold"}>{locked ? <><Lock size={12} />View sources</> : "Choose sources →"}</span>
    </button>
    <Handle type="source" position={Position.Right} isConnectable={false} className="!border-paper-line !bg-ink-faint" />
    {createPortal(<dialog ref={dialog} aria-labelledby="knowledge-dialog-title"
      className="w-[min(480px,calc(100vw-32px))] max-h-[90dvh] overflow-auto rounded-2xl border border-paper-line bg-white p-6 text-ink shadow-xl backdrop:bg-black/40"
      onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <div className="mb-4 flex items-center justify-between gap-3"><h2 id="knowledge-dialog-title" className="text-lg font-bold">Knowledge sources</h2>
        <button type="button" aria-label="Close knowledge sources" onClick={() => dialog.current?.close()} className="rounded p-2 hover:bg-paper"><X size={18} /></button></div>
      <p className="mb-4 text-sm text-ink-soft">Choose the evidence your hypothesis agents can use. Agent skills separately define how they analyze that evidence.</p>
      {modelOnly ? <p>No external corpus is attached. Claims rely on model knowledge and require independent verification. Change the knowledge mode in pipeline settings to attach a corpus.</p> : locked ? <div className="rounded-lg border border-paper-line bg-paper p-4"><p className="font-semibold">{label}</p><p className="mt-2 text-sm text-ink-soft">Change research inputs in pipeline settings after execution stops.</p></div>
        : <>{saved && <p className="mb-3 text-sm text-ink-soft">Changing the source prepares a new analysis. This saved run stays unchanged.</p>}<KnowledgeSelect value={value ?? ""} onChange={onChange} /><p role="status" className="mt-3 text-sm text-ink-soft">Selected: {label}</p></>}
      <button type="button" onClick={() => dialog.current?.close()} className="mt-5 rounded-lg border border-paper-line px-4 py-2 text-sm font-semibold hover:bg-paper">Done</button>
    </dialog>, document.body)}
  </>;
}
