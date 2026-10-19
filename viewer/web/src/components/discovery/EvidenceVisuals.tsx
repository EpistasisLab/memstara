import AucAssessment from '../AucAssessment';
import { useState } from 'react';
import { ArrowRight, ScanSearch } from 'lucide-react';
import ReportBody from '../ReportBody';
import type { Result } from '../../types';

export function FeatureAtlas({ used, target, importance }: { used: string[]; target: string; importance: Record<string, number> }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const features = all ? used : used.slice(0, 12);
  if (!used.length) return <p>No extracted feature list has been recorded yet.</p>;
  return <div className="feature-atlas">
    <div className="atlas-header"><span>EXTRACTED INPUTS <b>{used.length}</b></span><span>PREDICTION TARGET</span></div>
    <div className="atlas-map"><div className="atlas-inputs">{features.map((feature,i)=><button key={`${feature}-${i}`} aria-pressed={selected===feature} onClick={()=>setSelected(feature)}><i>{String(i+1).padStart(2,'0')}</i><span>{feature}</span><ArrowRight size={14}/></button>)}</div><div className="atlas-bridge" aria-hidden="true"><span/></div><div className="atlas-target"><span>Y</span><strong>{target||'Not recorded'}</strong><small>Fixed prediction target</small></div></div>
    {used.length>12 && <button className="atlas-more" onClick={()=>setAll(v=>!v)}>{all?'Show fewer features':`Show all ${used.length} features`}</button>}
    {selected && <div className="atlas-inspection"><span>SELECTED INPUT</span><strong>{selected}</strong><p>{Object.hasOwn(importance,selected)?`Recorded contribution: ${importance[selected].toPrecision(4)}. Interpret using the model's contribution method.`:'No contribution value was recorded for this input.'}</p></div>}
    <p className="universe-note">Connections identify model inputs and their prediction target; they do not establish a causal relationship.</p>
  </div>;
}
export function ModelLens({ auc, model, spread }: { auc: number | null; model: string; spread?: number | null }) {
  const finite=auc!==null && Number.isFinite(auc) && auc>=0 && auc<=1;
  const theta = Math.PI * (1-(finite?auc:0));
  const x=150+110*Math.cos(theta), y=135-110*Math.sin(theta);
  return <div className="model-lens"><div><span className="universe-eyebrow">PREDICTIVE DISCRIMINATION</span><h3>{model || 'Model not recorded'}</h3><p>A measured result, not a validation of the hypothesis.</p><AucAssessment auc={auc}/>{typeof spread === 'number' && Number.isFinite(spread) && <span className="model-spread">Recorded AUC standard deviation · {spread.toFixed(4)}</span>}</div><div className="model-dial"><svg viewBox="0 0 300 176" role="img" aria-label={finite?`Recorded AUC ${auc.toFixed(4)} on a zero to one scale`:'AUC not yet recorded'}><path d="M40 135 A110 110 0 0 1 260 135" fill="none" stroke="currentColor" opacity=".12" strokeWidth="10" strokeLinecap="round"/><path d="M40 135 A110 110 0 0 1 260 135" fill="none" stroke="#769bc8" opacity=".8" strokeWidth="3" strokeLinecap="round"/><line x1="150" y1="18" x2="150" y2="35" stroke="currentColor" opacity=".5"/><text x="150" y="12" textAnchor="middle">0.5 reference</text>{finite&&<><circle cx={x} cy={y} r="12" fill="#769bc8" opacity=".14"/><circle cx={x} cy={y} r="5" fill="#769bc8"/></>}<text x="150" y="119" textAnchor="middle" className="dial-value">{finite?auc.toFixed(4):'—'}</text><text x="150" y="145" textAnchor="middle">RECORDED AUC</text><text x="40" y="165" textAnchor="middle">0</text><text x="260" y="165" textAnchor="middle">1</text></svg></div></div>;
}
export function InterpretationVoices({ voices }: { voices: NonNullable<NonNullable<Result['evaluation']>['interpretations']> }) {
  const [selected,setSelected]=useState<number | null>(null);
  const voice=voices.find(v=>v.slot===selected)??voices[0];
  return <div className="interpretation-voices"><div className="voices-grid">{voices.map(v=><button key={v.slot} aria-pressed={v.slot===voice?.slot} onClick={()=>setSelected(v.slot)}><ScanSearch size={20}/><span>VOICE {v.slot}</span><h4>{v.worker||`Interpreter ${v.slot}`}</h4><p>{v.skill||'Skill not recorded'}</p><small>{v.status}</small></button>)}</div>{voice&&<article><header><ScanSearch size={18}/><strong>{voice.worker||`Interpreter ${voice.slot}`}</strong></header><ReportBody origin={voice.text ? "llm" : undefined} text={voice.text||voice.error||'No interpretation text recorded yet.'}/></article>}<p className="universe-note">Each voice is a recorded interpretation. Agreement or disagreement has not been inferred automatically.</p></div>;
}
