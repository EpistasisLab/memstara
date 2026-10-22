import { useEffect, useRef, useState } from 'react';
import type { Result } from '../types';
import { measuredResults, useResultNotices } from '../store/resultNotices';

/** Acknowledge loaded results once per visible scope, never a hidden/loading panel. */
export function useResultsReadReceipt(results: Result[] | null | undefined, scope: string, enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const viewedScope = useRef<string | null>(null);
  const [visible, setVisible] = useState(false);
  const hasResults = !!results?.length;
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let intersecting = false;
    const update = () => setVisible(intersecting && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => { intersecting = entry.isIntersecting; update(); });
    observer.observe(element);
    document.addEventListener('visibilitychange', update);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', update); };
  }, [hasResults]);
  useEffect(() => {
    if (!enabled || !visible) { viewedScope.current = null; return; }
    if (viewedScope.current === scope || !measuredResults(results ?? []).length) return;
    viewedScope.current = scope;
    useResultNotices.getState().acknowledge(results ?? []);
  }, [enabled, visible, scope, results]);
  return ref;
}
