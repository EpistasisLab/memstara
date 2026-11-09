import {lazy, StrictMode, Suspense} from 'react';
import {createRoot} from 'react-dom/client';
import Atlas from './Atlas';

const PerformanceTrends = lazy(() => import('./PerformanceTrends'));
const performance = new URLSearchParams(location.search).get('view') === 'performance';
createRoot(document.getElementById('root')!).render(<StrictMode>
  {performance ? <Suspense fallback={<p>Loading developer diagnostics…</p>}><PerformanceTrends/></Suspense> : <Atlas/>}
</StrictMode>);
