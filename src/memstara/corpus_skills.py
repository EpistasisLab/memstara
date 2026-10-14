"""Explicit source-to-skill bindings, independent of disease or folder names.

The index digests identify the supplied corpora, not clinical validation. Registered
research inputs separately freeze and verify every knowledge file before execution.
Unknown corpora use the general profile; copying a disease name cannot enable one.
"""
import hashlib
import os
from pathlib import Path

PROFILES = {
    'hiv': {
        'label': 'HIV / Addiction knowledge corpus',
        'hypothesis': ['addiction-substance-use', 'addiction-sdoh', 'addiction-psychiatric', 'random_features'],
        'report': ['shared-anil-addiction', 'shared-anil-hiv'],
    },
    'heart_failure': {
        'label': 'HeartFailure knowledge corpus',
        'hypothesis': ['heart-failure-cardiovascular', 'heart-failure-metabolic-renal',
                       'heart-failure-lifestyle-social', 'random_features'],
        'report': ['report_general'],
    },
    'general': {
        'label': 'General research corpus / model knowledge',
        'hypothesis': ['hypothesis_general', 'random_features'],
        'report': ['report_general'],
    },
}
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

    return {'profiles': PROFILES, 'default': corpus_profile(),
            'research': {record['id']: corpus_profile(record) for record in list_inputs()}}


def validate_hypotheses(books, profile=None, *, knowledge_mode='okf'):
    scope = corpus_profile(profile, knowledge_mode=knowledge_mode)
    # General/custom choices remain executable for existing saved runs. The UI
    # offers the four corpus-specific choices for new known-corpus selections.
    permitted = set(PROFILES[scope]['hypothesis']) | {'hypothesis_general'}
    for name in books.get('hypothesis', []):
        if name not in permitted and not name.startswith('user-hypothesis-'):
            raise ValueError(f'{name}: Hypothesis skill does not match the selected corpus ({scope}). '
                             'Review Knowledge sources and select a matching skill.')
    reports = set(PROFILES[scope]['report']) | {'report_general'}
    for name in books.get('report', []):
        if name not in reports and not name.startswith('user-report-'):
            raise ValueError(f'{name}: Explanation skill does not match the selected corpus ({scope}). '
                             'Select a matching or general Explanation skill.')
