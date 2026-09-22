import { useEffect, useRef } from 'react';
import { Layers3 } from 'lucide-react';
import MasterStop from './MasterStop';

/** Workspace-wide controls, independent of the selected pipeline or current view. */
export default function PipelineExecutionDock() {
  const dock = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = dock.current;
    if (!node) return;
    const measure = () => {
      document.documentElement.style.setProperty('--execution-dock-bottom', `${Math.max(0,node.getBoundingClientRect().bottom)}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    for (const sibling of node.parentElement?.children ?? []) {
      if (sibling === node) break;
      observer.observe(sibling);
    }
    window.addEventListener('scroll',measure,true);
    window.addEventListener('resize',measure);
    measure();
    return () => { observer.disconnect(); window.removeEventListener('scroll',measure,true); window.removeEventListener('resize',measure); document.documentElement.style.removeProperty('--execution-dock-bottom'); };
  }, []);
  return <section ref={dock} className="pipeline-execution-dock" aria-label="All pipeline execution controls">
    <div className="execution-dock-scope"><Layers3 size={18} aria-hidden="true"/><div><strong>All pipelines</strong><span>Applies to every pipeline, including those hidden by filters.</span></div></div>
    <div className="execution-dock-actions" role="group" aria-label="Workspace-wide execution"><MasterStop/></div>
  </section>;
}
