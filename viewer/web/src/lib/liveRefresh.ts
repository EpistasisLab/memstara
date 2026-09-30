export const LIVE_REFRESH_MS = 500;
export const IDLE_REFRESH_MS = 3000;

/** Schedule from request start, while allowing only one request at a time. */
export function pollContinuously(poll: () => Promise<void>, interval: () => number) {
  let stopped = false;
  let running = false;
  let timer: ReturnType<typeof setTimeout>;
  async function tick() {
    if (stopped || running) return;
    clearTimeout(timer);
    const started = performance.now();
    running = true;
    try { if (!document.hidden) await poll(); }
    finally {
      running = false;
      if (!stopped) timer = setTimeout(() => { void tick(); }, document.hidden ? IDLE_REFRESH_MS : Math.max(50, interval() - (performance.now() - started)));
    }
  }
  const visible = () => { if (!document.hidden) void tick(); };
  document.addEventListener('visibilitychange', visible);
  void tick();
  return () => { stopped = true; clearTimeout(timer); document.removeEventListener('visibilitychange', visible); };
}
