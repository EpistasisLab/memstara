/** UI labels only. Never use these values for API requests, hashes or saved evidence. */
const specialistLabels: Record<string, string> = {
  'shared-anil-shap': 'SHAP Interpretation',
  'shared-anil-lime': 'LIME Interpretation',
  'shared-anil-addiction': 'Addiction Expert Explanation',
  'shared-anil-hiv': 'HIV Expert Explanation',
};

/** Remove legacy project contributor attribution from visible text, including old records.
 * This is a presentation rule for known project names, not a general PII detector.
 * Letter/number boundaries preserve clinical terms such as neutrophil and aniline.
 */
export function displayText(text: string | null | undefined): string {
  return (text ?? '')
    .replace(/(?<![\p{L}\p{N}])shared[-_ ]anil[-_ ](shap|lime|addiction|hiv)(?![\p{L}\p{N}])/giu,
      (_, role: string) => specialistLabels[`shared-anil-${role.toLowerCase()}`])
    .replace(/\ban Anil-authored\b/gi, 'a contributor-authored')
    .replace(/(?<![\p{L}\p{N}])(?:anil|phil)[-_]shared(?![\p{L}\p{N}])/giu, 'contributed-resources')
    .replace(/(?<![\p{L}\p{N}])(?:anil(?:\s+saini)?|phil(?:\s+freda)?|jason(?:\s+moore)?|hyunjun(?:\s+choi|a)?|choih2|junchoi)(?![\p{L}\p{N}])/giu, 'contributor');
}

export function skillLabel(id?: string | null, title?: string | null, fallback = 'Skill not recorded'): string {
  const key = id?.toLowerCase() ?? '';
  return Object.hasOwn(specialistLabels, key) ? specialistLabels[key] : displayText(title?.trim() || id?.trim() || fallback);
}

/** Read-only formatted preview. The underlying object remains unchanged. */
export function displayJson(value: unknown): string {
  return displayText(JSON.stringify(value, null, 2));
}
