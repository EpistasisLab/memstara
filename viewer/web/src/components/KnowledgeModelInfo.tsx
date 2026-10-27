import {useEffect, useState} from 'react';
import {stageModelRows, type ModelConfiguration} from '../lib/stageModels';

/** Display configured model names only; never expose connection URLs or credentials. */
export default function KnowledgeModelInfo() {
  const [label, setLabel] = useState('Loading model…');
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    async function load() {
      try {
        const response = await fetch('/control/health', {signal: controller.signal});
        if (!response.ok) throw Error('Unavailable');
        const health = await response.json();
        if (!health.llm || health.llm.error || health.stage_model_error) throw Error('Unavailable');
        const configuration: ModelConfiguration = {...health.llm, stage_models: health.stage_models};
        const rows = stageModelRows(configuration);
        if (rows.some(row => row.model === 'Not recorded' || row.provider === 'Not recorded')) throw Error('Unavailable');
        const names = [...new Set(rows.map(row => `${row.model} (${row.provider.replace(/_/g, ' ')})`))];
        if (active) setLabel(`${names.length === 1 ? 'Model' : 'Models'}: ${names.join(' · ')}`);
      } catch {
        if (active) setLabel('Model information unavailable');
      } finally { clearTimeout(timeout); }
    }
    void load();
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, []);
  return <span className="research-llm-model" role="status" aria-label="Configured language model">{label}</span>;
}
