/** One in-flight request and one timer for all consumers of a read-only resource. */
export function sharedPoller<T>(load: (signal: AbortSignal) => Promise<T>, interval = 6000) {
  let state: {data: T | null; error: string; refreshing: boolean} = {data: null, error: '', refreshing: false};
  const listeners = new Set<() => void>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | null = null;
  const emit = (patch: Partial<typeof state>) => {state = {...state, ...patch}; listeners.forEach(listener => listener());};
  const refresh = async () => {
    if (controller || !listeners.size) return;
    clearTimeout(timer);
    const current = new AbortController(); controller = current;
    emit({refreshing: true});
    const deadline = setTimeout(() => current.abort(), 6500);
    try {
      const data = await load(current.signal);
      if (!current.signal.aborted) emit({data, error: ''});
    } catch (error) {
      if (listeners.size) emit({error: error instanceof Error ? error.message : 'Measurements unavailable'});
    } finally {
      clearTimeout(deadline); controller = null; emit({refreshing: false});
      if (listeners.size) timer = setTimeout(() => void refresh(), interval);
    }
  };
  return {
    getSnapshot: () => state,
    refresh: () => {void refresh();},
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      if (listeners.size === 1) void refresh();
      return () => {
        listeners.delete(listener);
        if (!listeners.size) {clearTimeout(timer); controller?.abort();}
      };
    },
  };
}
