import { useEffect, useState, type RefObject } from 'react';
import { useOutputNotices } from '../store/outputNotices';

/** Reading one visible replicate never consumes another view's unread output. */
export function useOutputReadReceipt(root: RefObject<HTMLDivElement | null>, keys: string[], enabled: boolean) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!root.current) return;
    let intersecting = false;
    const update = () => setVisible(intersecting && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => { intersecting = entry.isIntersecting; update(); });
    observer.observe(root.current);
    document.addEventListener('visibilitychange', update);
    return () => {observer.disconnect(); document.removeEventListener('visibilitychange', update);};
  }, [root]);
  useEffect(() => {
    if (enabled && visible) useOutputNotices.getState().acknowledge(keys);
  }, [enabled, visible, keys]);
}
