"""Append a Motoro cost snapshot after completed loops; never control experiments.

This one-shot observer reads local completion records and HTTP GET endpoints only.
It writes the requested report and a matching evidence JSON, then exits. Run it
separately from start.sh so monitoring cannot delay or restart application services.
"""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen


def get(base, tag, loop):
    query = urlencode({"run_tag": tag, "loop": loop})
    with urlopen(base.rstrip('/') + '/api/cost-details?' + query, timeout=45) as response:
        result = json.load(response)
    if result.get('run_tag') != tag or result.get('source') != 'motoro':
        raise ValueError('Unexpected cost evidence source or execution')
    return result


def totals(rows):
    return (len(rows), sum(r.get('prompt_tokens') or 0 for r in rows),
            sum(r.get('completion_tokens') or 0 for r in rows),
            sum((Decimal(str(r['usd'])) for r in rows if r.get('usd') is not None), Decimal(0)))


def role(stage):
    for prefix, label in [('question', 'Question generation'), ('hypothesis', 'Hypothesis'),
                          ('data', 'Data'), ('ml', 'ML'), ('interpret', 'Interpretation'),
                          ('report', 'Explanation'), ('explanation', 'Explanation')]:
        if (stage or '').startswith(prefix):
            return label
    return 'Other / ' + str(stage)


def render(tag, loops, rows, captured, evidence_name):
    count, inp, out, usd = totals(rows)
    long_rows = [r for r in rows if (r.get('prompt_tokens') or 0) > 100000]
    long_count, _, _, long_usd = totals(long_rows)
    all_tokens = inp + out
    lines = [f'## New execution: first {len(loops)} completed combinations', '',
             f'Execution: `{tag}`. Captured at **{captured}**. Completed Loop IDs: '
             + ', '.join(map(str, loops)) + '.', '',
             'Scope: persisted Motoro requests for these completed loops only, including their retries. '
             'Later or unfinished loops are excluded. Each selected loop was checked for inactive agent runs, '
             'missing records, and unknown prices. This is recorded estimated cost, not an Azure invoice.', '',
             f'Evidence: [{evidence_name}]({evidence_name}).', '',
             '| Metric | Earlier 8070 snapshot | New completed-loop snapshot |',
             '|---|---:|---:|',
             f'| LLM requests | 258 | {count:,} |',
             f'| Input tokens | 18,378,435 | {inp:,} |',
             f'| Output tokens | 382,602 | {out:,} |',
             f'| Total tokens | 18,761,037 | {all_tokens:,} |',
             f'| Input share | 97.96% | {inp / all_tokens * 100:.2f}% |',
             f'| Recorded estimated cost | $7.20704521 | ${usd:.8f} |',
             f'| Blended cost per million total tokens | $0.38415 | ${usd * 1000000 / all_tokens:.5f} |',
             f'| Requests above 100,000 input tokens | 83 | {long_count} |',
             f'| Cost of those long requests | $6.54902895 | ${long_usd:.8f} |',
             f'| Long-request share of recorded cost | 90.87% | {long_usd / usd * 100:.2f}% |', '',
             'The totals cover different execution scopes and are not a paired experimental comparison. '
             'Per-request figures below help separate request volume from average context size; '
             'question selection, tools, skills, and retries can also differ.', '',
             '| Per-request metric | Earlier snapshot | New snapshot |', '|---|---:|---:|',
             f'| Mean input tokens | {18378435 / 258:,.1f} | {inp / count:,.1f} |',
             f'| Mean output tokens | {382602 / 258:,.1f} | {out / count:,.1f} |',
             f'| Mean recorded cost | ${7.20704521 / 258:.8f} | ${usd / count:.8f} |', '',
             '### Agent-level usage', '',
             '| Agent | Requests | Input tokens | Output tokens | Recorded cost | Long requests |',
             '|---|---:|---:|---:|---:|---:|']
    for label in dict.fromkeys(role(r.get('stage')) for r in rows):
        group = [r for r in rows if role(r.get('stage')) == label]
        n, i, o, cost = totals(group)
        long_n = sum((r.get('prompt_tokens') or 0) > 100000 for r in group)
        lines.append(f'| {label} | {n} | {i:,} | {o:,} | ${cost:.8f} | {long_n} |')
    lines += ['', '### Completed-loop usage', '',
              '| Loop | Requests | Input tokens | Output tokens | Recorded cost |',
              '|---|---:|---:|---:|---:|']
    for loop in loops:
        n, i, o, cost = totals([r for r in rows if r['loop'] == loop])
        lines.append(f'| {loop} | {n} | {i:,} | {o:,} | ${cost:.8f} |')
    lines += ['', 'Models recorded: ' + ', '.join(sorted({str(r.get('model')) for r in rows})) + '.',
              'Pricing sources recorded: ' + ', '.join(sorted({str(r.get('source')) for r in rows})) + '.',
              'Recorded cache-read tokens: ' + str(sum(r.get('cache_read_input_tokens') or 0 for r in rows))
              + '; cache-write tokens: ' + str(sum(r.get('cache_creation_input_tokens') or 0 for r in rows)) + '.',
              'Null cache counters, if present, are not evidence of zero provider caching. '
              'No official-rate recalculation or invoice reconciliation is implied. '
              'The observer did not stop, restart, reconfigure, or invoke any experiment.', '']
    return '\n'.join(lines)


def main(args):
    run = Path(args.run_dir)
    report = Path(args.report)
    tag = args.run_tag
    marker = f'<!-- cost-observation:{tag} -->'
    if marker in report.read_text():
        print('Report already contains this observation.', flush=True)
        return
    deadline = time.monotonic() + 86400
    while time.monotonic() < deadline:
        try:
            outcomes = json.loads((run / 'iteration_outcomes.json').read_text())
            loops = sorted(int(k) for k, v in outcomes.items() if v.get('outcome') == 'completed')[:args.count]
            print(f'{datetime.now(timezone.utc).isoformat()} completed={len(loops)}/{args.count}', flush=True)
            if len(loops) == args.count:
                snapshots = [get(args.base_url, tag, loop) for loop in loops]
                if any(s.get('active') or s.get('missing_runs') or s.get('unpriced_calls')
                       or s.get('status') != 'complete' for s in snapshots):
                    raise ValueError('Waiting for complete persisted Motoro records')
                records = list({r['id']: r for s in snapshots for r in s['records']}.values())
                if not records or any(r.get('loop') not in loops for r in records):
                    raise ValueError('Unexpected request loop attribution')
                captured = datetime.now(timezone.utc).isoformat()
                evidence = report.with_name(f'llm_cost_snapshot_{tag}_first{args.count}.json')
                evidence.write_text(json.dumps({'run_tag': tag, 'captured_at': captured,
                    'completed_loops': loops, 'snapshots': snapshots}, indent=2) + '\n')
                section = render(tag, loops, records, captured, evidence.name)
                # Append only; preserve all existing report sections and concurrent edits.
                if marker not in report.read_text():
                    with report.open('a') as handle:
                        handle.write('\n' + marker + '\n\n' + section)
                print(f'COMPLETE: appended report {report}', flush=True)
                return
            if (run / 'pipeline_failure.json').exists():
                print('Execution failed before the threshold; no completed-eight snapshot written.', flush=True)
                return
        except (OSError, ValueError, KeyError) as exc:
            print(f'Retry: {type(exc).__name__}: {exc}', flush=True)
        time.sleep(60)
    print('Observation expired after 24 hours; no threshold snapshot written.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--run-tag', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8070')
    parser.add_argument('--count', type=int, default=8)
    main(parser.parse_args())
