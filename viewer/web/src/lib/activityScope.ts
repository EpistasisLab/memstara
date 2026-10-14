/** Match runtime stage aliases without mixing unrelated stages. */
export function normalizeActivityStage(value?: string | null): string {
  const name=(value??'').toLowerCase().trim().split('#')[0];
  return ({interpretation:'interpreter',explanation:'report',result:'ml',question:'curator'} as Record<string,string>)[name]??name;
}
export function matchesActivityStage(value: string | null | undefined, scope: string | undefined, kind: 'text' | 'tool'): boolean {
  if (!scope) return true;
  const actual=normalizeActivityStage(value);
  const selected=normalizeActivityStage(scope);
  // The floor plan groups question generation with hypothesis generation.
  if (selected==='hypothesis') return actual==='hypothesis'||actual==='curator';
  // Question tool calls use the shared hypothesis identity; text has a precise stage.
  if (selected==='curator'&&kind==='tool') return actual==='hypothesis'||actual==='curator';
  return actual===selected;
}
