"""Check portable release resources; publication remains an explicit evidence gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'specialists/SHAP-Interpretation.md', 'specialists/LIME-Interpretation.md',
    'specialists/Addiction-Expert-Explanation.md', 'specialists/HIV-Expert-Explanation.md',
    'machine-learning/ML Knowledge (1).md', 'machine-learning/ML Skill (1).md',
}
DECISIONS = {
    'toy_dataset_and_knowledge_source', 'project_license',
    'contributed_document_rights', 'human_review',
    'final_candidate_live_acceptance', 'publication_owner_approval',
}


def check(root: Path, *, publication: bool = False) -> list[str]:
    errors = []
    bundle = root / 'src/memstara/resources/contributed'
    try:
        manifest = json.loads((bundle / 'manifest.json').read_text())
        rows = manifest['files']
        names = [row['path'] for row in rows]
        if manifest['schema_version'] != 1 or set(names) != EXPECTED or len(names) != len(EXPECTED):
            errors.append('Contributed inventory must contain exactly the six current documents')
        for row in rows:
            name = row['path']
            if name not in EXPECTED:
                errors.append('Unexpected contributed path')
                continue
            path = bundle / name
            if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
                errors.append(f'{name}: unsafe bundled path')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                errors.append(f'{name}: preservation hash mismatch')
            if publication and (row.get('redistribution_approval') != 'approved'
                                or not row.get('approval_evidence')):
                errors.append(f'{name}: redistribution approval is pending')
        if publication and manifest.get('publication_status') != 'approved':
            errors.append('Contributed publication status is not approved')
        decisions = json.loads((root / 'deployment/release-readiness.json').read_text())
        if decisions.get('schema_version') != 1 or decisions.get('public_and_research_same_source') is not True:
            errors.append('Invalid release configuration or divergent source policy')
        if set(decisions.get('decisions', {})) != DECISIONS:
            errors.append('Missing or unexpected release decision gates')
        if publication:
            for name in sorted(DECISIONS):
                value = decisions.get('decisions', {}).get(name, {})
                if value.get('status') != 'approved' or not str(value.get('evidence', '')).strip():
                    errors.append(f'{name}: decision/evidence pending')
        for name in ('dataset.csv', 'research.json', 'okf/index.md', 'okf/observations/simulated-risk.md'):
            if not (root / 'examples/research-inputs' / name).is_file():
                errors.append(f'Toy example missing: {name}')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f'Release content cannot be verified: {type(exc).__name__}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publication', action='store_true')
    args = parser.parse_args()
    errors = check(ROOT, publication=args.publication)
    for error in errors:
        print(error)
    print(f'{len(errors)} errors; mode={"publication" if args.publication else "content-only"}. '
          'This does not attest human review or live pipeline success.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
