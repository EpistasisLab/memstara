type PredictorType = 'continuous' | 'categorical';
type ColumnInspection = {
  column_kinds?: Record<string, string>;
  suggested_predictor_types?: Record<string, PredictorType>;
};

/** Use inspected CSV types; semantic suggestions (e.g. stages/counts) take priority.
 * Unclassified numeric columns use mean imputation. No statistics are fitted here.
 */
export function automaticPredictorTypes(inspection: ColumnInspection): Record<string, PredictorType> {
  const types: Record<string, PredictorType> = {};
  for (const [column, kind] of Object.entries(inspection.column_kinds ?? {})) {
    if (kind === 'numeric') types[column] = 'continuous';
    else if (kind === 'categorical') types[column] = 'categorical';
  }
  return {...types, ...inspection.suggested_predictor_types};
}
