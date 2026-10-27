/** Prefer original per-call narratives over historical generated report wrappers. */
export function savedReportText(report?: {text?: string; explanation_outputs?: {text: string}[]} | null): string {
  return report?.explanation_outputs?.length
    ? report.explanation_outputs.map(output=>output.text).join('\n\n')
    : report?.text ?? '';
}
