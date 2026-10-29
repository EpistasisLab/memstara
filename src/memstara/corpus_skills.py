"""Explicit source-to-skill bindings, independent of disease or folder names.

The index digests identify the supplied corpora, not clinical validation. Registered
research inputs separately freeze and verify every knowledge file before execution.
Unknown corpora use the general profile; copying a disease name cannot enable one.
"""
import hashlib
import os
from pathlib import Path

PROFILES = {
    "hiv": {
        "label": "HIV / Addiction knowledge corpus",
        "hypothesis": ["addiction-substance-use", "addiction-sdoh", "addiction-psychiatric", "random_features"],
        "report": ["shared-heart-failure-cardiovascular", "shared-heart-failure-comorbidity"],
    },
    "heart_failure": {
        "label": "HeartFailure knowledge corpus",
        "hypothesis": [
            "heart-failure-all-categories",
            "heart-failure-all",
            "heart-failure-cardiovascular",
            "heart-failure-metabolic-renal",
            "heart-failure-lifestyle-social",
            "random_features",
        ],
        "report": ["shared-heart-failure-cardiovascular", "shared-heart-failure-comorbidity"],
    },
    "general": {
        "label": "General research corpus / model knowledge",
        "hypothesis": ["hypothesis_general", "random_features"],
        "report": ["shared-heart-failure-cardiovascular", "shared-heart-failure-comorbidity"],
    },
}
# Active Explanation perspectives are selectable independently of the corpus.
# Historical identifiers are retained only for saved-record resolution.
EXPLANATION_SKILLS = (
    'shared-heart-failure-cardiovascular', 'shared-heart-failure-comorbidity',
)
for _profile in PROFILES.values():
    _profile['report'] = list(dict.fromkeys([*_profile['report'], *EXPLANATION_SKILLS]))

INDEX_PROFILES = {
    'aec7452874f70ec9b427f55187aad44a8115d0720e585294fc70e6ad11b12527': 'hiv',
    'e90b6191d13c1c1bc626713bf4c12787f445b72e24aac523598ac483156c7a06': 'heart_failure',
}


def corpus_profile(profile=None, *, knowledge_mode='okf'):
    if knowledge_mode == 'llm_only':
        return 'general'
    if profile is not None:
        if profile['configuration'].get('knowledge_mode', 'okf') == 'llm_only':
            return 'general'
        # Inspection/registration and materialized execution manifests use
        # different inventories. Resume must identify the frozen artifact,
        # not fall back to the deployment's current corpus.
        if 'artifact_hashes' in profile:
            index = profile['artifact_hashes'].get('okf/index.md')
        else:
            index = profile.get('knowledge', {}).get('hashes', {}).get('index.md')
    else:
        if knowledge_mode == 'llm_only':
            return 'general'
        root = os.environ.get('AGENTIC_OKF_BUNDLE_DIR', '')
        try:
            index = hashlib.sha256((Path(root) / 'index.md').read_bytes()).hexdigest() if root else None
        except OSError:
            index = None
    return INDEX_PROFILES.get(index, 'general')


def menu_bindings():
    from memstara.research_inputs import list_inputs

    return {
        "profiles": {
            key: {
                **profile,
                "hypothesis": [
                    skill for skill in profile["hypothesis"] if skill not in ("random_features", "heart-failure-all")
                ],
            }
            for key, profile in PROFILES.items()
        },
        "default": corpus_profile(),
        "research": {record["id"]: corpus_profile(record) for record in list_inputs()},
    }


def validate_hypotheses(books, profile=None, *, knowledge_mode='okf'):
    scope = corpus_profile(profile, knowledge_mode=knowledge_mode)
    # General/custom choices remain executable for existing saved runs. The UI
    # offers the four corpus-specific choices for new known-corpus selections.
    permitted = set(PROFILES[scope]['hypothesis']) | {'hypothesis_general'}
    for name in books.get('hypothesis', []):
        if name not in permitted and not name.startswith('user-hypothesis-'):
            raise ValueError(f'{name}: Hypothesis skill does not match the selected corpus ({scope}). '
                             'Review Knowledge sources and select a matching skill.')
    # Retain historical input validation; the new-execution catalog gate rejects retired choices.
    reports = set(EXPLANATION_SKILLS) | {'shared-addiction', 'shared-hiv'}
    from memstara.control.catalog import canonical_name
    for name in books.get('report', []):
        if canonical_name(name) not in reports:
            raise ValueError(f'{name}: select a supplied Explanation skill from the library.')


def with_default_hypothesis(body):
    """Resolve an empty new-design selection to an explicit corpus-compatible skill."""
    choices = body.get('combination_skills')
    if not isinstance(choices, dict) or not choices:
        return body
    profile = None
    if body.get('research_input_id'):
        from memstara.research_inputs import load
        profile = load(body['research_input_id'])
    mode = profile['configuration']['knowledge_mode'] if profile else body.get('knowledge_mode', 'okf')
    scope = corpus_profile(profile, knowledge_mode=mode)
    updated = dict(choices)
    for stage in ('hypothesis', 'report'):
        if updated.get(stage, []) == []:
            updated[stage] = [PROFILES[scope][stage][0]]
    return {**body, 'combination_skills': updated}
