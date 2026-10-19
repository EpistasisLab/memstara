/** Reject invalid responses at the read boundary, before rendering scientific evidence. */
export async function readDiscoveryResponse(response: Response, url: string): Promise<unknown> {
  if (!response.ok) throw Error(response.status === 503 ? 'The records are temporarily unavailable.' : `Could not read records (${response.status}).`);
  let data: unknown;
  try { data = await response.json(); }
  catch { throw Error('The server returned an unreadable response. Retrying automatically; saved results are unchanged.'); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw Error('The server returned invalid records.');
  const record = data as Record<string, unknown>;
  const detail = /\/questions\/(\d+)(?:\?|$)/.exec(url);
  const question = (raw: unknown) => {
    if (!raw || typeof raw !== 'object') throw Error('Invalid question record.');
    const q = raw as Record<string, unknown>;
    if (!Number.isSafeInteger(q.question_id) || typeof q.text !== 'string') throw Error('Invalid question identity.');
    return {...q, question_id: q.question_id as number, text: q.text, okf_tags: Array.isArray(q.okf_tags) ? q.okf_tags.filter(t => typeof t === 'string') : [],
      rationale: typeof q.rationale === 'string' ? q.rationale : ''};
  };
  if (detail) {
    const q = question(record.question);
    if (q.question_id !== Number(detail[1])) throw Error('The returned evidence does not match the selected question.');
    if (!Array.isArray(record.tasks) || !Array.isArray(record.results)) throw Error('Question evidence is incomplete.');
    const normalize = (raw: unknown, id: string) => {
      if (!raw || typeof raw !== 'object' || !Number.isSafeInteger((raw as Record<string, unknown>)[id]))
        throw Error('Invalid linked result identity.');
      const item = raw as Record<string, unknown>;
      if (item.question_id != null && item.question_id !== q.question_id)
        throw Error('A result belongs to another question.');
      const arrays = Object.fromEntries(['columns','columns_used','columns_missing'].map(key=>[
        key, Array.isArray(item[key]) ? item[key].filter(v=>typeof v==='string') : []]));
      return {...item, ...arrays};
    };
    return {...record, question: q, tasks: record.tasks.map(r=>normalize(r,'task_id')),
      results: record.results.map(r=>normalize(r,'result_id'))};
  }
  if (url.includes('/discovery/questions?')) {
    if (!Array.isArray(record.questions)) throw Error('The question list is unavailable.');
    return {...record, questions: record.questions.map(question)};
  }
  return data;
}
