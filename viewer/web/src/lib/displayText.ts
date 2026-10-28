import legacyRules from './legacyDisplayRules.json' with {type: 'json'};

/** Display aliases never change saved evidence or API identifiers. */
const specialistLabels: Record<string, string> = {
  'shared-shap': 'SHAP Interpretation',
  'shared-lime': 'LIME Interpretation',
  'shared-addiction': 'Addiction Expert Explanation',
  'shared-hiv': 'HIV Expert Explanation',
  'shared-heart-failure-cardiovascular': 'Heart Failure — Cardiovascular Explanation',
  'shared-heart-failure-comorbidity': 'Heart Failure — Comorbidities and Social Context Explanation',
};
const legacyPatterns = legacyRules.map(rule => ({...rule, regex: new RegExp(rule.pattern, rule.flags)}));

/** Read legacy contributor-prefixed IDs without using names as code identifiers. */
function canonicalSkillId(id: string): string {
  return id.replace(/^shared-[^-]+-(shap|lime|addiction|hiv)$/i, 'shared-$1').toLowerCase();
}

export function displayText(text: string | null | undefined): string {
  let visible = (text ?? '').replace(/(?<![\p{L}\p{N}])shared[-_ ](?:[\p{L}]+[-_ ])?(shap|lime|addiction|hiv)(?![\p{L}\p{N}])/giu,
    (_, role: string) => specialistLabels[`shared-${role.toLowerCase()}`]);
  for (const rule of legacyPatterns) visible = visible.replace(rule.regex, rule.replacement);
  return visible;
}

export function skillLabel(id?: string | null, title?: string | null, fallback = 'Skill not recorded'): string {
  const key = canonicalSkillId(id ?? '');
  if (key.startsWith('user-') && title?.trim()) return title.trim();
  return Object.hasOwn(specialistLabels, key) ? specialistLabels[key] : displayText(title?.trim() || id?.trim() || fallback);
}

/** Read-only formatted preview. The underlying object remains unchanged. */
export function displayJson(value: unknown): string {
  return displayText(JSON.stringify(value, null, 2));
}
