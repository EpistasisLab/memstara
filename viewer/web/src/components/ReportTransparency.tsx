import { assessmentNotes } from '../lib/reportTransparency';
import { Calculator, Sparkles } from 'lucide-react';
import './report-transparency.css';

export default function ReportTransparency() {
  return <aside aria-label="Report assessment transparency" className="assessment-guide">
    <h3>How to read this report</h3>
    <p className="assessment-intro">Two different kinds of evidence — clearly labeled in the table.</p>
    <div className="assessment-research-purpose" role="note">
      <strong>Research priority ≠ clinical readiness</strong>
      <p>A hypothesis can be worth investigating even when it is not ready for clinical use. Look for a grounded question, a meaningful uncertainty and a feasible next experiment.</p>
      <small>Low clinical actionability alone should not lower research priority. Historical rankings have not been automatically reassessed.</small>
    </div>
    <div className="assessment-guide-grid">
      <section className="assessment-guide-card" data-assessment-kind="measured">
        <div className="assessment-card-label"><Calculator size={18} aria-hidden="true"/><span className="assessment-badge">Calculated metric</span></div>
        <h4>AUC & recorded ML metrics</h4>
        <p>Computed from model predictions and observed outcomes.</p>
        <p className="assessment-card-footnote">A measured score alone does not establish clinical usefulness.</p>
      </section>
      <section className="assessment-guide-card" data-assessment-kind="judgment">
        <div className="assessment-card-label"><Sparkles size={18} aria-hidden="true"/><span className="assessment-badge">LLM assessment</span></div>
        <h4>Rank · Evidence strength · Clinical actionability · Novelty · Decision</h4>
        <p><strong>LLM interpretations, not calculated scores.</strong> No fixed formula or standardized grading rubric.</p>
        <p className="assessment-card-footnote">Different models or prompts may judge the same evidence differently. Not clinically validated ratings.</p>
        <p className="assessment-card-footnote">Novelty is judged within consulted sources; it is not a systematic literature search or proof of a first discovery.</p>
      </section>
    </div>
    <details className="assessment-method-details"><summary>What each assessment means and its limitations</summary>
      <dl>{assessmentNotes.map(([title, body]) => <div key={title}><dt>{title}</dt><dd>{body}</dd></div>)}</dl>
    </details>
    <p className="assessment-source-note">Memstara explanatory note · applies to new and historical reports</p>
  </aside>;
}
