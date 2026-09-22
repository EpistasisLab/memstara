import ContentOrigin from "../components/ContentOrigin";
import { useLoopLabel } from '../lib/useLoopLabel';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Orbit, Search, List, Sparkles, ArrowRight } from 'lucide-react';
import ReportBody from '../components/ReportBody';
import ExplanationEvidence from '../components/ExplanationEvidence';
import type { Result, Task, QuestionContract } from '../types';
import { FeatureAtlas, ModelLens, InterpretationVoices } from '../components/discovery/EvidenceVisuals';
import LiveOutputDock from '../components/discovery/LiveOutputDock';
import { useLiveOutputs, type OutputEvent } from '../store/liveOutputs';
import QuestionSpace from '../components/discovery/QuestionSpace';
import ScientificProvenance from '../components/ScientificProvenance';
import './discovery.css';
import './question-space.css';

interface Question {
  question_contract?: QuestionContract;
  question_id: number; text: string; okf_tags: string[]; rationale: string;
  origin_run: string; origin_wave: number; writer: string; times_used: number;
  best_auc: number | null; status: string; created_at: string;
}
interface Evidence { question: Question; tasks: Task[]; results: Result[]; record_limit: number }
interface Report { run_tag: string; report: { status: string; text: string; error?: string } | null }

/** Serial, cancellable reads. A selection change can never display another question's answer. */
function useLive<T>(url: string | null) {
  const [record, setRecord] = useState<{ url: string; data?: T; error?: string }>({ url: '' });
  useEffect(() => {
    if (!url) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      try {
        if (document.hidden) return;
        const response = await fetch(url, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]) });
        if (!response.ok) throw Error(response.status === 503 ? 'The records are temporarily unavailable.' : `Could not read records (${response.status}).`);
        const data = await response.json() as T;
        if (!disposed) setRecord({ url, data });
      } catch (error) {
        if (!disposed) setRecord(previous => ({ url, data: previous.url === url ? previous.data : undefined, error: String(error) }));
      } finally { if (!disposed) timer = setTimeout(poll, 5000); }
    };
    void poll();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [url]);
  return record.url === url ? record : { url, data: undefined, error: undefined };
}

function EvidencePanel({ question, data, error, stage, setStage, resultId, setResultId }: {
  question: Question; data?: Evidence; error?: string; stage: string; setStage: (s: string) => void;
  resultId: number | null; setResultId: (id: number) => void;
}) {
  const labelLoop = useLoopLabel();
  const result = data?.results.find(r => r.result_id === resultId) ?? data?.results[0];
  const task = data?.tasks.find(t => t.task_id === result?.task_id) ?? (!result ? data?.tasks[0] : undefined);
  const runTag = result?.run_tag || task?.run_tag || question.origin_run;
  const report = useLive<Report>(stage === 'Explanation' && runTag ? `/api/discovery/report?run_tag=${encodeURIComponent(runTag)}` : null);
  const used = result?.columns_used ?? task?.columns_used ?? [];
  const importance = Object.entries(result?.importance ?? task?.importance ?? {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 12);
  const max = Math.max(...importance.map(([, value]) => Math.abs(value)), .00001);
  const interpretation = result?.evaluation?.interpretations;
  return <aside className="universe-evidence" aria-label="Selected question evidence">
    <div className="universe-evidence-heading"><span className="universe-eyebrow">QUESTION {question.question_id}</span><span className="universe-badge">{question.status}</span></div>
    <h2>{question.text}</h2>
    <ScientificProvenance result={result} contract={data?.question.question_contract ?? question.question_contract} />
    <p className="universe-meta">{question.writer || 'Writer not recorded'} · Loop {question.origin_wave + 1}<br />{question.origin_run || 'Origin run not recorded'}</p>
    <nav className="universe-stages" aria-label="Evidence stages">{['Question', 'Hypothesis', 'Data', 'ML', 'Interpretation', 'Explanation'].map(name => <button key={name} aria-pressed={stage === name} onClick={() => setStage(name)}>{name}</button>)}</nav>
    {error && <p role="alert">{error} {data ? 'Showing the last available evidence.' : ''}</p>}
    {!data && !error && <p role="status">Reading recorded evidence…</p>}
    {data && <>
      {data.results.length > 0 && stage !== 'Question' && <label className="universe-result-select">Recorded analysis<select value={result?.result_id ?? ''} onChange={e => setResultId(Number(e.target.value))}>{data.results.map(r => <option key={r.result_id} value={r.result_id}>Result {r.result_id} · {labelLoop(r)} · {r.run_tag}</option>)}</select></label>}
      {stage === 'Question' && <div className="universe-section"><ContentOrigin kind="proposal"/><h3>Why this question?</h3><ReportBody origin={data.question.rationale ? "mixed" : undefined} text={data.question.rationale || 'No generation rationale was recorded.'} /><h3>Knowledge tags</h3><div className="universe-chips">{question.okf_tags.map(tag => <span key={tag}>{tag}</span>)}{!question.okf_tags.length && <p>No source tags recorded.</p>}</div><p className="universe-note">{data.tasks.length} task records · {data.results.length} result records linked by question ID. Up to {data.record_limit} records per kind.</p></div>}
      {stage === 'Hypothesis' && <div className="universe-section"><h3>From question to hypothesis</h3><div className="universe-origin">{question.text}</div><ArrowRight className="my-3" size={20} /><ReportBody origin="proposal" text={result?.hypothesis || task?.hypothesis || 'No linked hypothesis has been recorded yet.'} />{task?.status === 'failed' && <p role="status">Task failed: {task.error}</p>}</div>}
      {stage === 'Data' && <div className="universe-section"><h3>Features carried into analysis</h3><p className="universe-note">Target: {result?.y_column || task?.y_column || 'Not recorded'}</p>{task?.columns.length ? <details><summary>{task.columns.length} requested columns</summary><div className="universe-chips">{task.columns.map((c, i) => <span key={`${c}-${i}`}>{c}</span>)}</div></details> : <p className="universe-note">Requested columns are not available in the retained task record.</p>}<FeatureAtlas used={used} target={result?.y_column||task?.y_column||''} importance={result?.importance??task?.importance??{}}/>{(result?.columns_missing ?? task?.columns_missing ?? []).map(c => <p key={c}>Missing: {c}</p>)}</div>}
      {stage === 'ML' && <div className="universe-section"><h3>What the model found</h3><ModelLens auc={result?.auc??task?.auc??null} model={result?.model||''} spread={result?.evaluation?.auc_std}/><p className="universe-note">AUC describes discrimination. It is not a probability of correctness or a measure of clinical usefulness.</p><h3>Feature contributions</h3>{importance.map(([feature, value]) => <div className="universe-bar" key={feature}><span>{feature}</span><div><i style={{ width: `${Math.abs(value) / max * 100}%` }} /></div><code>{value.toPrecision(3)}</code></div>)}{!importance.length && <p>No feature contributions recorded yet.</p>}<p className="universe-note">Magnitude shown; values retain their sign. Contribution scales depend on the recorded model and method.</p>{result?.evaluation && <details><summary>Recorded evaluation settings</summary><pre>{JSON.stringify({ seed: result.evaluation.seed, test_size: result.evaluation.test_size, config_hash: result.evaluation.config_hash, evaluation: result.evaluation.evaluation }, null, 2)}</pre></details>}</div>}
      {stage === 'Interpretation' && <div className="universe-section"><h3>Interpretation voices</h3>{interpretation?.length ? <InterpretationVoices voices={interpretation}/> : <ReportBody origin="llm" text={result?.interpretation || task?.interpretation || 'No linked interpretation has been recorded yet.'} />}{result && <ExplanationEvidence result={result} />}</div>}
      {stage === 'Explanation' && <div className="universe-section"><h3>The resulting report</h3><p className="universe-note">Run-level report · {runTag || 'No linked run'}. This may cover several questions; it is not a question-specific conclusion.</p>{report.error && <p role="alert">{report.error}</p>}{!runTag ? <p>No run linked.</p> : !report.data && !report.error ? <p>Reading report…</p> : <><span className="universe-badge">{report.data?.report?.status || 'Not available'}</span><ReportBody report text={report.data?.report?.text || 'No report has been recorded for this run yet.'} /></>}</div>}
    </>}
  </aside>;
}

export default function DiscoveryPanel() {
  const live=useLiveOutputs();
  const [openedReport,setOpenedReport]=useState<string|null>(null);
  const [openError,setOpenError]=useState('');
  const openSequence=useRef(0);
  const [pages, setPages] = useState<number[]>([0]);
  const before = pages[pages.length - 1];
  const { data, error } = useLive<{ questions: Question[]; next_before: number | null }>(`/api/discovery/questions?before=${before}`);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Question | null>(null);
  const [list, setList] = useState(false);
  const [stage, setStage] = useState('Question');
  const [resultId, setResultId] = useState<number | null>(null);
  const studio = useRef<HTMLDivElement>(null);
  const evidence = useLive<Evidence>(selected ? `/api/discovery/questions/${selected.question_id}` : null);
  const questions = useMemo(() => {
    const records=new Map((data?.questions??[]).map(q=>[q.question_id,q]));
    if(before===0)live.questions.forEach(q=>records.set(q.question_id,q));
    return [...records.values()].sort((a,b)=>b.question_id-a.question_id).slice(0,120).filter(q=>`${q.text} ${q.rationale} ${q.okf_tags.join(' ')}`.toLowerCase().includes(search.toLowerCase()));
  },[data,live.questions,before,search]);
  const current = data?.questions.find(q => q.question_id === selected?.question_id) ?? selected;
  const result=evidence.data?.results.find(r=>r.result_id===resultId) ?? evidence.data?.results[0];
  const task=evidence.data?.tasks.find(t=>t.task_id===result?.task_id) ?? (!result?evidence.data?.tasks[0]:undefined);
  const select=(q: Question)=>{setSelected(q);setResultId(null);setStage('Question');setList(false);};
  const openOutput=async(event:OutputEvent)=>{
    const sequence=++openSequence.current;setOpenError('');
    if(event.stage==='report'){setOpenedReport(event.run_tag);return;}
    if(event.question_id===null){setOpenError('This output has no recorded question link. It remains visible in the live stream.');return;}
    try{
      let question=live.questions.find(q=>q.question_id===event.question_id)??data?.questions.find(q=>q.question_id===event.question_id);
      if(!question){const response=await fetch(`/api/discovery/questions/${event.question_id}`,{signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('Question evidence is temporarily unavailable.');question=(await response.json()).question;}
      if(sequence!==openSequence.current||!question)return;
      select(question);setOpenedReport(null);
      const names:Record<string,string>={question:'Question',hypothesis:'Hypothesis',data:'Data',ml:'ML',interpretation:'Interpretation',result:'ML'};
      setStage(names[event.stage]||'Question');if(event.result_id)setResultId(event.result_id);
    }catch(error){if(sequence===openSequence.current)setOpenError(String(error));}
  };
  const openStage=(name:string)=>{setStage(name);studio.current?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});};
  return <div className="universe-page universe-v2">
    <header className="universe-header"><div><span className="universe-eyebrow"><Sparkles size={13} /> MEMSTARA DISCOVERY</span><h1>Follow a question.<br /><span>Discover what follows.</span></h1></div><div className="space-header-note"><p>A living field of agent-generated questions,<br />with their recorded evidence one step away.</p><span className="universe-live">{error ? 'Connection interrupted' : data ? 'Live records · 5s updates' : 'Connecting…'}</span></div></header>
    <ContentOrigin kind="proposal"/><div className="universe-tools"><label><Search size={17} /><input aria-label="Search loaded questions" placeholder="Find a question, rationale, or knowledge tag…" value={search} onChange={e => setSearch(e.target.value)} /></label><button onClick={() => setList(v => !v)} aria-pressed={list}>{list ? <Orbit size={16} /> : <List size={16} />}{list ? 'Question field' : 'Question list'}</button></div>
    <div className="universe-context"><span>{questions.length} questions on this page · Across all recorded runs</span><span>Explore outputs, evidence and interpretations</span></div>
    {error && <p className="universe-alert" role="alert">{error} {data ? 'Showing the last available questions.' : 'Retrying automatically.'}</p>}
    <LiveOutputDock open={event=>{void openOutput(event);}}/>
    {openError&&<p role="alert">{openError}</p>}
    {openedReport&&<article className="universe-evidence"><button className="universe-close" onClick={()=>setOpenedReport(null)}>Close report ×</button><h2>Live run report</h2><p className="universe-note">{openedReport} · {live.reports[openedReport]?.status||'Not available'}</p><ReportBody report text={live.reports[openedReport]?.text||live.reports[openedReport]?.error||'No report text is available yet.'}/></article>}
    <section className="universe-explore" aria-label="Question exploration">
      {!data ? <p className="universe-loading" role="status">{error?'Question field is temporarily unavailable.':'Reading the question bank…'}</p> : list ? <div className="universe-list">{questions.map(q => <button key={q.question_id} aria-pressed={q.question_id === current?.question_id} onClick={() => select(q)}><span>Q{q.question_id} · {q.status}</span><strong>{q.text}</strong><small>{q.okf_tags.join(' · ') || 'No source tags recorded'}</small></button>)}{!questions.length && <p>No matching questions.</p>}</div> : <QuestionSpace questions={questions} selected={current} select={id=>{const q=questions.find(q=>q.question_id===id);if(q)select(q);}} clear={()=>setSelected(null)} openStage={openStage} activeStage={stage}
        summary={{hypothesis:result?.hypothesis||task?.hypothesis||'',features:result?result.columns_used.length:task?.columns_used.length?task.columns_used.length:null,auc:result?.auc??task?.auc??null,interpretations:result?.evaluation?.interpretations?.length??(result?.interpretation||task?.interpretation?1:null),hasRun:!!(result?.run_tag||task?.run_tag||current?.origin_run)}} />}
      <div className="universe-pagination"><button disabled={pages.length === 1} onClick={() => setPages(p => p.slice(0, -1))}>Newer questions</button><span>Page {pages.length}</span><button disabled={!data?.next_before} onClick={() => { if (data?.next_before) setPages(p => [...p, data.next_before!]); }}>Older questions</button></div>
    </section>
    {current && <div className="space-studio" ref={studio}><div className="space-studio-title"><span className="universe-eyebrow">EVIDENCE STUDIO / Q{current.question_id}</span><p>Recorded outputs, connected by question identity.</p></div><EvidencePanel key={current.question_id} question={current} data={evidence.data} error={evidence.error} stage={stage} setStage={setStage} resultId={resultId} setResultId={setResultId}/></div>}
  </div>;
}
