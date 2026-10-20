export default function ManualPricingSettings(){
  return <section aria-label="Cost estimation" className="space-y-3 text-sm">
    <p>Motoro calculates model cost estimates. Memstara records and displays the returned amounts without recalculating them.</p>
    <p>If Motoro cannot provide a price, the cost remains unavailable. Local manual rates and pricing JSON do not override execution costs.</p>
    <p>Estimates are separate from actual Azure billing.</p>
  </section>;
}
