type JsonObject = Record<string, unknown>;
type CsvScalar = string | number | boolean | null | undefined;

const CHILD_COLLECTIONS = ['agents', 'results', 'costs', 'artifacts'] as const;

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function json(value: unknown): string {
  return JSON.stringify(value ?? null);
}

function at(value: unknown, path: readonly (string | number)[]): unknown {
  let current = value;
  for (const part of path) {
    if (typeof part === 'number') {
      if (!Array.isArray(current)) return undefined;
      current = current[part];
    } else {
      if (!isObject(current)) return undefined;
      current = current[part];
    }
  }
  return current;
}

function first(value: unknown, paths: readonly (readonly (string | number)[])[]): unknown {
  for (const path of paths) {
    const found = at(value, path);
    if (found !== undefined && found !== null) return found;
  }
  return undefined;
}

/** Keep each stored top-level field once; nested values remain lossless JSON cells. */
function fields(prefix: string, value: unknown, output: Record<string, CsvScalar>) {
  if (!isObject(value)) {
    output[prefix] = Array.isArray(value) ? json(value) : value as CsvScalar;
    return;
  }
  const entries = Object.entries(value).sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) output[prefix] = '{}';
  for (const [key, child] of entries) {
    output[`${prefix}.${key}`] = isObject(child) || Array.isArray(child) ? json(child) : child as CsvScalar;
  }
}

function formulaSafe(value: CsvScalar): string {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'string' ? value : String(value);
  // Excel, Numbers and Sheets can execute cells beginning with these characters.
  return /^[\t\r ]*[=+\-@]/.test(text) ? `'${text}` : text;
}

function quote(value: CsvScalar): string {
  return `"${formulaSafe(value).replaceAll('"', '""')}"`;
}

function context(detail: JsonObject): Record<string, CsvScalar> {
  const row: Record<string, CsvScalar> = {
    schema_version: 'memstara_complete_evidence_csv_v1',
    run_tag: detail.run_tag as CsvScalar,
    experiment_id: detail.experiment_id as CsvScalar,
    combination_id: detail.combination_id as CsvScalar,
    pipeline_id: detail.pipeline_id as CsvScalar,
    execution_status: detail.status as CsvScalar,
    synced_at: detail.synced_at as CsvScalar,
  };
  return row;
}

const RESULT_PATHS = {
  seed_number: [
    ['evaluation', 'data_allocation', 'effective_plan', 'seed'],
    ['evaluation', 'data_allocation', 'plan', 'seed'],
    ['evaluation', 'data_allocation', 'seed'],
    ['evaluation', 'evaluation', 'replicates', 0, 'seed'],
    ['evaluation', 'seed'],
    ['seed'],
  ],
  replicate_seeds: [
    ['evaluation', 'evaluation', 'replicate_seeds'],
    ['evaluation', 'replicate_seeds'],
  ],
  auroc: [
    ['auc'],
    ['evaluation', 'auc'],
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'auroc'],
    ['evaluation', 'evaluation', 'replicates', 0, 'auc'],
  ],
  average_precision: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'average_precision'],
    ['evaluation', 'evaluation', 'replicates', 0, 'average_precision'],
  ],
  threshold: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'threshold'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'probability_cutoff'],
  ],
  sensitivity: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'sensitivity'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'sensitivity'],
  ],
  specificity: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'specificity'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'specificity'],
  ],
  precision: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'precision'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'precision'],
  ],
  f1: [['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'f1'], ['evaluation', 'evaluation', 'replicates', 0, 'f1']],
  true_negative: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'confusion_matrix', 'tn'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'true_negative'],
  ],
  false_positive: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'confusion_matrix', 'fp'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'false_positive'],
  ],
  false_negative: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'confusion_matrix', 'fn'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'false_negative'],
  ],
  true_positive: [
    ['evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'confusion_matrix', 'tp'],
    ['evaluation', 'evaluation', 'replicates', 0, 'operating_point', 'true_positive'],
  ],
} as const;

function rowFor(type: string, index: number, record: unknown, detail: JsonObject): Record<string, CsvScalar> {
  const row: Record<string, CsvScalar> = {...context(detail), record_type: type, record_index: index};
  if (isObject(record)) {
    for (const key of ['run_tag', 'result_uid', 'result_id', 'task_id', 'trial', 'pipeline_number', 'replicate_number', 'interpretation_status', 'explanation_status', 'hypothesis_id', 'hypothesis', 'perspective', 'y_column', 'model', 'interpretation', 'created_at', 'agent_run_id', 'stage', 'started_at', 'duration_seconds', 'path', 'sha256', 'bytes', 'kind'] as const) {
      if (record[key] !== undefined && !isObject(record[key]) && !Array.isArray(record[key])) row[key] = record[key] as CsvScalar;
    }
    if (type === 'result') {
      for (const key of ['interpretation_output_ids','explanation_output_ids']) {
        if (Array.isArray(record[key])) row[key] = json(record[key]);
      }
      for (const [key, paths] of Object.entries(RESULT_PATHS)) {
        const value = first(record, paths);
        row[key] = Array.isArray(value) || isObject(value) ? json(value) : value as CsvScalar;
      }
      const skills = first(record, [['evaluation', 'skills'], ['skills']]);
      row.skills_json = skills === undefined ? undefined : json(skills);
    }
    if (type === 'agent') {
      row.agent_skill = first(record, [['playbook'], ['skill'], ['metadata', 'playbook'], ['metadata', 'skill'], ['evidence', 'playbook'], ['evidence', 'skill']]) as CsvScalar;
    }
  }
  fields('record', record, row);
  return row;
}

/**
 * Long-form, lossless export: one execution row plus one row for every registered
 * agent, result, cost and artifact. Every stored top-level field is retained, with
 * nested objects/arrays encoded as lossless JSON cells and stable analysis aliases.
 */
export function evidenceToCsv(detail: JsonObject): string {
  return evidenceCollectionToCsv([detail]);
}

/** One header union across continued executions; original run identities survive. */
export function evidenceCollectionToCsv(details:JsonObject[]):string {
  const rows:Record<string,CsvScalar>[]=[];
  for (const detail of details) {
    const executionBase = Object.fromEntries(Object.entries(detail).filter(([key]) => !CHILD_COLLECTIONS.includes(key as typeof CHILD_COLLECTIONS[number])));
    rows.push(rowFor('execution', 0, executionBase, detail));
    for (const collection of CHILD_COLLECTIONS) {
      const values = Array.isArray(detail[collection]) ? detail[collection] : [];
      values.forEach((record, index) => rows.push(rowFor(collection.slice(0, -1), index, record, detail)));
    }
  }
  const preferred = [
    'schema_version', 'record_type', 'record_index', 'run_tag', 'experiment_id', 'combination_id', 'pipeline_id', 'execution_status', 'synced_at',
    'result_id', 'task_id', 'trial', 'hypothesis_id', 'stage', 'agent_run_id', 'agent_skill', 'skills_json', 'model', 'seed_number', 'replicate_seeds',
    'auroc', 'average_precision', 'threshold', 'sensitivity', 'specificity', 'precision', 'f1', 'true_negative', 'false_positive', 'false_negative', 'true_positive',
    'hypothesis', 'perspective', 'y_column', 'interpretation', 'created_at', 'started_at', 'duration_seconds', 'path', 'sha256', 'bytes', 'kind',
    'result_uid','pipeline_number','replicate_number','interpretation_output_ids','explanation_output_ids','interpretation_status','explanation_status',
  ];
  const keys = new Set(rows.flatMap(row => Object.keys(row)));
  const headers = [...preferred.filter(key => keys.delete(key)), ...[...keys].sort()];
  return '\uFEFF' + [headers.map(quote).join(','), ...rows.map(row => headers.map(header => quote(row[header])).join(','))].join('\r\n') + '\r\n';
}
