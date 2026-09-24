# SOURCE: SANDBOX-ORIGINAL — exact study-policy enforcement and cache identity.
import json
import numpy as np
import pytest
from memstara.matcher.rules import RuleSet, load_rules
from memstara.matcher.catalog import build_catalog, catalog_fingerprint, save_catalog_meta, verify_catalog
from memstara.matcher.service import VerifiedMatcher

COLS = ['Y', 'LAB__CD4', 'MED__BIKTARVY', 'LAB__ALT']


def policy(feature='LAB__CD4'):
    return RuleSet(target='Y', approved_by='test reviewer',
                   exclusions=[{'feature': feature, 'reason': 'test-only exclusion'}])


def fingerprint(rules):
    return catalog_fingerprint(cohort_file='fixture.csv', columns=COLS, outcome_col='Y',
        schema_version=1, builder_version=1, embedding_model='stub', embedding_revision=None, rules=rules)


def test_blocked_exact_feature_cannot_return_through_matching():
    entries = build_catalog(COLS, 'Y', rules=policy('MED__BIKTARVY'))
    matcher = VerifiedMatcher.build(entries, encoder=lambda texts: np.ones((len(texts), 2)))
    assert matcher.match('BIKTARVY', feature_type='medication').matches == ()
    assert all(e.feature_name not in ('Y','MED__BIKTARVY') for e in entries)
    assert 'LAB__CD4' in [e.feature_name for e in entries]


def test_cd4_exclusion_and_unchanged_no_policy():
    assert [e.feature_name for e in build_catalog(COLS,'Y')] == COLS[1:]
    assert [e.feature_name for e in build_catalog(COLS,'Y',rules=policy())] == COLS[2:]


@pytest.mark.parametrize('change', [dict(target='different'),dict(approved_by=''),
    dict(exclusions=[{'feature':'MISSING','reason':'test'}]),
    dict(exclusions=[{'feature':'LAB__CD4','reason':''}]),
    dict(exclusions=[{'feature':'LAB__CD4','reason':'x'}]*2), dict(semantic='CD4')])
def test_invalid_policy_fails_closed(change):
    data=policy().model_dump();data.update(change)
    with pytest.raises(ValueError):
        build_catalog(COLS,'Y',rules=RuleSet.model_validate(data))


def test_policy_changes_invalidate_catalog(tmp_path):
    path=tmp_path/'catalog.json';path.write_text('[]')
    save_catalog_meta([],path,fingerprint(policy()))
    assert verify_catalog(path,fingerprint(policy())) is None
    assert 'leakage_rules_sha1' in verify_catalog(path,fingerprint(policy('MED__BIKTARVY')))
    assert 'leakage_rules_sha1' in verify_catalog(path,fingerprint(None))


def test_missing_configured_file_never_falls_back(monkeypatch,tmp_path):
    monkeypatch.setenv('MEMSTARA_LEAKAGE_RULES_PATH',str(tmp_path/'absent.json'))
    with pytest.raises(FileNotFoundError): load_rules()


def test_policy_change_does_not_reuse_singleton(monkeypatch,tmp_path):
    from memstara.matcher import service
    path=tmp_path/'policy.json';path.write_text(policy().model_dump_json())
    monkeypatch.setenv('MEMSTARA_LEAKAGE_RULES_PATH',str(path))
    monkeypatch.setattr(service,'current_fingerprint',lambda **kw: fingerprint(kw['rules']))
    calls=[]
    monkeypatch.setattr(service,'_get_matcher_cached',lambda *args: calls.append(args))
    service.get_matcher()
    path.write_text(policy('MED__BIKTARVY').model_dump_json())
    service.get_matcher()
    assert calls[0] != calls[1]


def test_runtime_rejects_excluded_entry_even_if_metadata_matches(monkeypatch,tmp_path):
    from memstara.matcher import service
    from types import SimpleNamespace
    rule=policy()
    monkeypatch.setattr(service.cfg_mod,'CATALOG_JSON',tmp_path/'catalog.json')
    monkeypatch.setattr(service,'sentence_transformer_encoder',lambda _: None)
    monkeypatch.setattr(service.VerifiedMatcher,'from_catalog',lambda *args,**kwargs:
        SimpleNamespace(entries=build_catalog(COLS,'Y')))
    service._get_matcher_cached.cache_clear()
    with pytest.raises(RuntimeError,match='study-excluded'):
        service._get_matcher_cached(json.dumps(fingerprint(rule)),rule.model_dump_json())
    service._get_matcher_cached.cache_clear()


def test_local_retention_policy_is_loaded_without_env_override(monkeypatch,tmp_path):
    monkeypatch.delenv('MEMSTARA_LEAKAGE_RULES_PATH',raising=False)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR',str(tmp_path))
    assert load_rules() is None
    retained=RuleSet(target='Y',approved_by='test owner',exclusions=[])
    (tmp_path/'matcher_rules.json').write_text(retained.model_dump_json())
    assert load_rules()==retained
    assert load_rules().sha1 != fingerprint(None)['leakage_rules_sha1']
