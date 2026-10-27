import {Check, Database, FileText, AlertCircle} from 'lucide-react';
import type {ResearchConfig} from './ResearchInputs';

export type SavedStudy = {
  id: string;
  corpus_skill_profile?: string;
  input_checks_passed: boolean;
  configuration: ResearchConfig;
  issues?: {code: string; message: string}[];
};

function filename(path?: string) {
  return path?.split(/[\\/]/).filter(Boolean).pop() || 'Not specified';
}

/** A study is selectable only after validation; incomplete records open the editor. */
export default function ResearchStudyLibrary({studies, selectedId, disabled, onSelect, onReview}: {
  studies: SavedStudy[];
  selectedId?: string;
  disabled: boolean;
  onSelect: (id: string) => void;
  onReview: (id: string) => void;
}) {
  return <section aria-label="Saved research inputs" className="research-study-library">
    <div className="flex items-baseline justify-between gap-3">
      <h4 className="text-sm font-semibold">Saved data</h4>
      <span className="text-xs text-slate-500">{studies.length} saved</span>
    </div>
    {!studies.length && <p className="rounded-xl border border-dashed border-paper-line p-4 text-sm text-slate-500">No saved data yet. Choose Upload a new CSV above to get started.</p>}
    <div className="research-study-grid">
      {studies.map(study => {
        const config = study.configuration;
        const selected = selectedId === study.id;
        const ready = study.input_checks_passed;
        const proposal = config.data_mode === 'proposal';
        return <article key={study.id} aria-label={config.name} className={`research-study-card ${selected?'is-selected':''}`} >
          <div className="flex items-start gap-2">
            <Database size={17} className="mt-0.5 shrink-0 text-slate-500" aria-hidden="true"/>
            <h5 className="min-w-0 flex-1 break-words text-sm font-semibold leading-5">{config.name}</h5>
          </div>
          <div className={`mt-2 inline-flex items-center gap-1.5 text-xs font-medium ${ready ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}`}>
            {ready ? <Check size={13} aria-hidden="true"/> : <AlertCircle size={13} aria-hidden="true"/>}
            {ready ? 'Input checks passed' : 'Needs setup'}
          </div>
          <dl className="mt-3 space-y-2 text-xs">
            <div><dt className="text-slate-500">Dataset</dt><dd className="break-words">{proposal ? 'No CSV — proposal only' : filename(config.dataset_path)}</dd></div>
            <div><dt className="text-slate-500">Prediction target</dt><dd className="break-words">{config.target.column || (proposal ? 'Research proposal' : 'Not set')}</dd></div>
            <div><dt className="text-slate-500">Knowledge</dt><dd className="break-words">{config.knowledge_mode === 'llm_only' ? 'LLM only' : config.knowledge_path?.includes('/heart-failure/okf')?'Heart failure research library':'Research documents'}</dd></div>
          </dl>
          {!ready && <p className="mt-3 break-words text-xs text-amber-700 dark:text-amber-400">{study.issues?.[0]?.message || 'Open this study to review its data and target settings.'}</p>}
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-slate-500">Study details</summary>
            <div className="mt-2 space-y-2 break-words">
              <p>{config.target.description}</p>
              <p>Positive label: {config.target.positive_label || 'Not set'}. Negative label: {config.target.negative_label || 'Not set'}.</p>
              <p>Predictor timing: {config.target.prediction_time || 'Not specified'}. Horizon: {config.target.horizon || 'Not specified'}.</p>
              {!proposal && <p className="break-all"><FileText size={12} className="mr-1 inline" aria-hidden="true"/>{config.dataset_path}</p>}
              {config.knowledge_mode !== 'llm_only' && <p className="break-all">{config.knowledge_path}</p>}
              <p className="break-all text-slate-500">Record: {study.id}</p>
            </div>
          </details>
          <button type="button" disabled={disabled} aria-pressed={ready ? selected : undefined}
            aria-label={`${ready ? 'Use' : 'Review'} ${config.name}`}
            onClick={() => ready ? onSelect(study.id) : onReview(study.id)}
            className={`mt-4 w-full rounded-lg border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${selected && ready ? 'border-sky-600 bg-sky-600 text-white' : 'border-paper-line hover:bg-slate-100 dark:hover:bg-slate-800'}`}>
            {ready ? selected ? 'Selected' : 'Use this data' : 'Review & complete setup'}
          </button>
        </article>;
      })}
    </div>
  </section>;
}
