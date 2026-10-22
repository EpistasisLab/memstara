import { memo } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { reportLoopText } from '../lib/reportLoopText';
import { reportMarkdown } from '../lib/reportMarkdown';
import { reportTableColumns } from '../lib/reportTableColumns';
import { displayMarkdown } from '../lib/displayMarkdown';
import ReportTransparency from './ReportTransparency';
import ContentOrigin, { type ContentOriginKind } from './ContentOrigin';
import './report-transparency.css';

// Stable component types preserve the table DOM across polling and content updates.
const markdownPlugins = [remarkGfm, reportTableColumns, displayMarkdown];
const markdownComponents: Components = {
      th: ({children, node, ...props}) => {
        const kind = String(node?.properties?.['data-assessment-kind'] ?? node?.properties?.dataAssessmentKind ?? '');
        return <th {...props} data-assessment-kind={kind || undefined} scope="col">
          <span>{children}</span>
          {kind && <span className="assessment-column-context">
            <span className="assessment-badge">{kind === 'judgment' ? 'LLM assessment' : kind === 'proposal' ? 'Agent research proposal' : 'Calculated metric'}</span>
            <span className="assessment-column-note">{String(node?.properties?.['data-assessment-note'] ?? node?.properties?.dataAssessmentNote ?? (kind === 'judgment' ? 'Qualitative judgment · no fixed scoring rule' : 'Computed from predictions and outcomes'))}</span>
          </span>}
        </th>;
      },
      pre: ({children}) => <pre tabIndex={0} aria-label="Code block">{children}</pre>,
      img: ({alt}) => <span>{alt || 'Image omitted'}</span>,
      table: ({children}) => <div className="report-table-wrap"><div className="report-table-scroll" role="region" aria-label="Report table — scroll horizontally to see all columns" tabIndex={0}><table>{children}</table></div><p className="report-table-hint">If columns extend beyond the panel, scroll the table horizontally.</p></div>,
      a: ({children,href}) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
};

/** Markdown is rendered as text elements; model-provided HTML is never evaluated. */
function ReportBody({text, report = false, origin, analysesPerLoop, compactOrigin = false}:{text:string; report?: boolean; origin?: ContentOriginKind; analysesPerLoop?: number; compactOrigin?: boolean}) {
  return <div className="report-markdown">
    {(origin || report) && <ContentOrigin kind={origin ?? 'mixed'} compact={compactOrigin}/>}
    {(report || /^##\s+Ranked hypotheses\s*$/im.test(text)) && <ReportTransparency />}
    <Markdown remarkPlugins={markdownPlugins} skipHtml components={markdownComponents}>
      {report ? reportLoopText(reportMarkdown(text), analysesPerLoop) : reportMarkdown(text)}
    </Markdown>
  </div>;
}

// Unchanged report text needs no Markdown parsing when surrounding live metrics update.
export default memo(ReportBody);
