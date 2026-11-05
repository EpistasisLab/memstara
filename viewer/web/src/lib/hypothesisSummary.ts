type UnknownRecord = Record<string, unknown>;

export interface HypothesisSummaryRow {
  runTag: string;
  pipeline: string;
  hypothesisSkill: string;
  scheduledReplicate: number | null;
  evaluationReplicate: number;
  resultId: number | null;
  taskId: number | null;
  trial: number | null;
  subjects: number | null;
  nTrain: number | null;
  nTest: number | null;
  seed: number | null;
  model: string;
  auroc: number | null;
  averagePrecision: number | null;
  f1: number | null;
  threshold: number | null;
  sensitivity: number | null;
  specificity: number | null;
  precision: number | null;
  trueNegative: number | null;
  falsePositive: number | null;
  falseNegative: number | null;
  truePositive: number | null;
  hypothesis: string;
  resultUid: string;
  pipelineNumber: number | null;
  replicateNumber: number | null;
  interpretationOutputIds: string[];
  explanationOutputIds: string[];
  interpretationStatus: string;
  explanationStatus: string;
}

const object = (value: unknown): UnknownRecord => value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};
const number = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null;
const text = (value: unknown): string => typeof value === 'string' ? value : '';

/** Use measured fit metadata only; agent-written labels are not model evidence. */
function modelLabel(measured: UnknownRecord, replicate: UnknownRecord, threshold: number | null): string {
  const name = text(measured.model) || 'Model not recorded';
  const parameters = object(replicate.parameters);
  const preferred = ['penalty', 'solver', 'C', 'class_weight', 'n_estimators', 'max_depth', 'learning_rate'];
  const keys = [...preferred.filter(key => key in parameters),
    ...Object.keys(parameters).filter(key => !preferred.includes(key)).sort()];
  const parts = keys.map(key => `${key}=${JSON.stringify(parameters[key])}`);
  if (!keys.length) parts.push('parameters not recorded');
  if (threshold !== null) parts.push(`threshold=${threshold}`);
  return `${name} (${parts.join('; ')})`;
}

export function hypothesisSummaryRows(results: readonly unknown[]): HypothesisSummaryRow[] {
  const rows = results.flatMap(raw => {
    const result = object(raw), measured = object(result.evaluation), evaluation = object(measured.evaluation);
    const skills = object(measured.skills), hypotheses = Array.isArray(skills.hypothesis) ? skills.hypothesis : [];
    const hypothesisSkill = hypotheses.map(text).filter(Boolean).join(', ') || text(result.hypothesis_id) || 'Not recorded';
    const recorded = Array.isArray(evaluation.replicates) ? evaluation.replicates : [];
    const replicates = recorded.length ? recorded : [{auc: result.auc, seed: measured.seed, n_train: measured.n_train, n_test: measured.n_test}];
    return replicates.map((rawReplicate, index) => {
      const replicate = object(rawReplicate), performance = object(object(replicate.performance).test);
      const metrics = object(performance.metrics), matrix = object(performance.confusion_matrix), point = object(replicate.operating_point);
      const nTrain = number(replicate.n_train), nTest = number(replicate.n_test);
      const threshold = number(performance.threshold) ?? number(point.probability_cutoff);
      return {
        runTag: text(result.run_tag), pipeline: text(result.pipeline_name) || text(result.run_tag) || 'Analysis',
        hypothesisSkill, scheduledReplicate: number(result.iteration), evaluationReplicate: index + 1,
        resultId: number(result.result_id), taskId: number(result.task_id), trial: number(result.trial),
        subjects: nTrain !== null && nTest !== null ? nTrain + nTest : null, nTrain, nTest,
        seed: number(replicate.seed) ?? number(measured.seed), model: modelLabel(measured, replicate, threshold),
        auroc: number(metrics.auroc) ?? number(replicate.auc) ?? number(result.auc),
        averagePrecision: number(metrics.average_precision) ?? number(replicate.average_precision),
        f1: number(metrics.f1) ?? number(replicate.f1),
        threshold,
        sensitivity: number(metrics.sensitivity) ?? number(point.sensitivity),
        specificity: number(metrics.specificity) ?? number(point.specificity),
        precision: number(metrics.precision) ?? number(point.precision),
        trueNegative: number(matrix.tn) ?? number(point.true_negative),
        falsePositive: number(matrix.fp) ?? number(point.false_positive),
        falseNegative: number(matrix.fn) ?? number(point.false_negative),
        truePositive: number(matrix.tp) ?? number(point.true_positive),
        hypothesis: text(result.hypothesis),
        resultUid: text(result.result_uid), pipelineNumber: number(result.pipeline_number), replicateNumber: number(result.replicate_number),
        interpretationOutputIds: Array.isArray(result.interpretation_output_ids)?result.interpretation_output_ids.map(text).filter(Boolean):[],
        explanationOutputIds: Array.isArray(result.explanation_output_ids)?result.explanation_output_ids.map(text).filter(Boolean):[],
        interpretationStatus: text(result.interpretation_status)||'not_loaded', explanationStatus: text(result.explanation_status)||'not_loaded',
      };
    });
  });
  return rows.sort((left,right)=>left.hypothesisSkill.localeCompare(right.hypothesisSkill)
    || left.pipeline.localeCompare(right.pipeline)
    || (left.scheduledReplicate??Number.MAX_SAFE_INTEGER)-(right.scheduledReplicate??Number.MAX_SAFE_INTEGER)
    || left.evaluationReplicate-right.evaluationReplicate);
}

function quote(value: unknown): string {
  let rendered = value === null || value === undefined ? '' : String(value);
  if (/^[\t\r ]*[=+\-@]/.test(rendered)) rendered = `'${rendered}`;
  return `"${rendered.replaceAll('"', '""')}"`;
}

export function hypothesisSummaryCsv(rows: readonly HypothesisSummaryRow[]): string {
  const fields: [string, keyof HypothesisSummaryRow][] = [
    ['Hypothesis Skill','hypothesisSkill'],['Pipeline','pipeline'],['Run Tag','runTag'],['Scheduled Replicate','scheduledReplicate'],
    ['Evaluation Replicate','evaluationReplicate'],['Result ID','resultId'],['Task ID','taskId'],['Trial','trial'],
    ['Subjects','subjects'],['N Train','nTrain'],['N Test','nTest'],['Seed','seed'],['Model','model'],['AUROC','auroc'],
    ['Average Precision','averagePrecision'],['F1','f1'],['Threshold','threshold'],['Sensitivity','sensitivity'],
    ['Specificity','specificity'],['Precision','precision'],['TN','trueNegative'],['FP','falsePositive'],['FN','falseNegative'],
    ['TP','truePositive'],['Hypothesis','hypothesis'],
    ['result_uid','resultUid'],['Pipeline Number','pipelineNumber'],['Schedule Replicate','replicateNumber'],
    ['interpretation_output_ids','interpretationOutputIds'],['explanation_output_ids','explanationOutputIds'],
    ['interpretation_status','interpretationStatus'],['explanation_status','explanationStatus'],
  ];
  return '\uFEFF' + [fields.map(([label])=>quote(label)).join(','), ...rows.map(row=>fields.map(([,key])=>quote(Array.isArray(row[key])?JSON.stringify(row[key]):row[key])).join(','))].join('\r\n') + '\r\n';
}
