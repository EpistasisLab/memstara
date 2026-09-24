import { useId } from 'react';
import { ShieldCheck, Info } from 'lucide-react';

export default function LoopLimitSettings({value,onChange,disabled=false}:{value:number;onChange:(value:number)=>void;disabled?:boolean}) {
  const id=useId();
  const valid=Number.isInteger(value)&&value>=1&&value<=10;
  return <section className="loop-limit-card" aria-labelledby={`${id}-heading`}>
    <header className="loop-limit-heading"><ShieldCheck size={24} aria-hidden="true"/><div><span className="loop-limit-kicker">Important · Execution control</span><h4 id={`${id}-heading`}>Set when this pipeline stops</h4></div></header>
    <p className="loop-limit-intro">Limit how long the agents keep exploring, especially when you step away.</p>
    <label className="loop-limit-label" htmlFor={`${id}-input`}>Maximum Loops per execution <span>Required · 1–10</span></label>
    <div className="loop-limit-input-row"><input id={`${id}-input`} aria-label="Maximum Loops per execution" aria-describedby={`${id}-meaning ${id}-preview ${id}-cost`} aria-invalid={!valid} type="number" min={1} max={10} step={1} required disabled={disabled} value={value||''} onChange={e=>onChange(Number(e.target.value))}/><span>Loops for this pipeline</span></div>
    <p id={`${id}-meaning`} className="loop-limit-definition"><strong>One Loop</strong> is one round of research: generate a question and hypothesis, extract data, evaluate the model, interpret it and report the findings. A blocked round also counts.</p>
    <div id={`${id}-preview`} className="loop-limit-preview" aria-live="polite">{valid?<><strong>Up to {value} {value===1?'Loop':'Loops'} → finish reporting → end execution.</strong><span>Loop {value+1} will not start automatically.</span></>:<strong>Enter a whole number from 1 to 10 before continuing.</strong>}</div>
    <ul className="loop-limit-rules"><li><strong>Each pipeline has its own limit.</strong> This is not a shared total across pipelines.</li><li><strong>Resume keeps the same limit.</strong> For example, with a limit of 10, after 4 finished Loops there are at most 6 more.</li><li><strong>You can stop earlier.</strong> Stop or Stop all pipelines lets in-flight agent calls finish, then waits before the next call.</li></ul>
    <p id={`${id}-cost`} className="loop-limit-cost"><Info size={17} aria-hidden="true"/><span><strong>This is a Loop limit, not a dollar budget.</strong> Cost varies by Loop, retries and model. In-flight calls and final reporting can still incur cost.</span></p>
  </section>;
}
