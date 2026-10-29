import {useId} from 'react';

export function explanationLengthError(value: number = 250): string {
  return Number.isInteger(value) && value >= 1 && value <= 10000
    ? '' : 'Enter a whole number from 1 to 10,000 words.';
}

export default function ExplanationLengthSettings({value = 250, disabled, onChange}: {
  value?: number; disabled?: boolean; onChange: (value: number) => void;
}) {
  const id = useId();
  const error = explanationLengthError(value);
  return <section className="mb-4 rounded-lg border border-paper-line bg-paper-panel p-4" aria-label="Explanation report settings">
    <label htmlFor={id} className="block text-sm font-medium">Report length (words)</label>
    <input id={id} type="number" min={1} max={10000} step={1} disabled={disabled}
      value={Number.isFinite(value) ? value : ''} aria-invalid={!!error} aria-describedby={`${id}-help`}
      onChange={event => onChange(event.target.valueAsNumber)}
      className="mt-2 block w-full max-w-48 rounded-md border border-paper-line bg-paper p-2 text-ink"/>
    <p id={`${id}-help`} className="mt-2 text-xs text-ink-muted">Default: 250 words. Approximate length of each Explanation report; sentences are not cut off.</p>
    {error && <p className="mt-2 text-sm text-red-600" role="alert">{error}</p>}
  </section>;
}
