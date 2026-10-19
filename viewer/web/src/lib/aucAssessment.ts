export function aucAssessment(auc: unknown) {
  if (typeof auc !== 'number' || !Number.isFinite(auc) || auc < 0 || auc > 1)
    return {kind:'unavailable', label:'AUC unavailable'};
  if (auc < .5) return {kind:'below', label:'Below-chance discrimination'};
  if (auc === .5) return {kind:'chance', label:'Chance-level discrimination'};
  return {kind:'above', label:'Above-chance measured AUC · validation required'};
}
