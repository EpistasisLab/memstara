import Help from "./Help";
import { useControl } from "../store/control";

export default function KnowledgeSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const skills = useControl((s) => s.skills);
  const documents = useControl((s) => s.bundle?.documents);

  return (
    <label className="block">
      <span className="text-[12px] font-bold uppercase tracking-wider text-ink-faint">Knowledge sources <Help topic="Skill" /></span>
      <select
        aria-label="Knowledge sources"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-paper-line bg-white px-2 py-1
                   text-xs focus:border-ink focus:outline-hidden"
      >
        <option value="">All available knowledge{documents != null ? ` · ${documents} documents` : ""}</option>
        {skills.map((s) => (
          <option key={s.skill} value={s.skill}>
            {s.label} · {s.documents} documents
          </option>
        ))}
      </select>
      <span className="mt-1 block text-[12px] font-normal leading-relaxed text-ink-faint">Choose the evidence agents can explore. Configure their instructions in Agent settings or the pipeline.</span>
    </label>
  );
}

