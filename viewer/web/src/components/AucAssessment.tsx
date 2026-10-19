import {aucAssessment} from '../lib/aucAssessment';
export default function AucAssessment({auc}:{auc:unknown}) {
 const assessment=aucAssessment(auc);
 return <div className="universe-note" data-auc-assessment={assessment.kind}>
  <strong>{assessment.label}</strong>
  <p>This describes the recorded score, not statistical significance, clinical utility or proof for or against the hypothesis. Check the evaluation partition and uncertainty before comparing results.</p>
 </div>;
}
