"""Broad-category defaults, empty-selection persistence and historical isolation."""
import copy
import json
import pytest
from memstara import corpus_skills
from memstara.control import catalog
from memstara.control.workspace import PipelineWorkspace
from memstara.control.request import build_argv
from memstara.combinations import build_plan, validate_plan
from memstara.pipeline import feature_selection as fs
from memstara.pipeline.prompts import load_prompt

NEW = 'heart-failure-all-categories'
OLD = 'heart-failure-all'


def choices(hypothesis):
    return {'hypothesis': hypothesis, 'data': ['data_training_heavy'],
            'ml': [], 'interpreter': ['shared-shap'], 'report': ['shared-addiction']}


@pytest.mark.parametrize('scope,expected', [('heart_failure',NEW),('hiv','addiction-substance-use'),('general','hypothesis_general')])
def test_empty_selection_is_saved_and_launched_with_matching_default(monkeypatch, scope, expected):
    from memstara import research_inputs
    index = next((h for h,p in corpus_skills.INDEX_PROFILES.items() if p==scope), 'unknown')
    profile = {'configuration': {'name':'fixture','knowledge_mode':'okf','data_mode':'dataset',
               'target':{'column':'outcome','description':'synthetic outcome'}},
               'knowledge':{'hashes':{'index.md':index}}}
    monkeypatch.setattr(research_inputs,'load',lambda _:profile)
    for role in ('QUESTION','HYPOTHESIS','DATA','ML','INTERPRETATION','EXPLANATION'):
        monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER','openai')
        monkeypatch.setenv(f'MEMSTARA_{role}_MODEL','fixture')
    original = {'research_input_id':'fixture','knowledge_mode':'llm_only','combination_skills':choices([])}
    saved = PipelineWorkspace.configuration(original)
    assert original['combination_skills']['hypothesis']==[]
    assert saved['combination_skills']['hypothesis']==[expected]
    for body in (saved, {**saved, 'combination_skills': choices([])}):
        argv=build_argv(body,[],[s['id'] for s in catalog.catalog()],list(choices([])))
        plan=json.loads(argv[argv.index('--combination-plan')+1])
        assert plan['skills']['hypothesis'][0]['id']==expected
        assert plan['combinations']==1


def test_explicit_selection_is_not_replaced():
    value={'combination_skills':choices(['heart-failure-cardiovascular'])}
    assert corpus_skills.with_default_hypothesis(value)==value


def test_new_all_categories_allows_justified_subset_and_preserves_legacy_all():
    pool=[f'x{i}' for i in range(30)]
    base={'run_tag':'fixture','y_column':'outcome','dataset_sha256':'fixture',
          'evaluation':{'seed':42},'feature_context':{'features':[{'column':c} for c in pool]}}
    for skill in (OLD,NEW):
        plan={**copy.deepcopy(base),'combination_plan':build_plan(choices([skill]))}
        plan['feature_selection_policy']=fs.freeze(plan)
        contract=fs.context(plan,0)
        assert validate_plan(plan['combination_plan'])==plan['combination_plan']
        if skill==NEW:
            assert contract['mode']=='guided' and contract['required_features'] is None
            assert fs.validate(pool[:6],plan,0)['actual_count']==6
            assert fs.scoped(plan,0)==plan
            with pytest.raises(ValueError):fs.validate(pool[:5]+['outcome'],plan,0)
        else:
            assert contract['mode']=='all' and contract['required_features']==pool
            with pytest.raises(ValueError):fs.validate(pool[:6],plan,0)
            assert fs.validate(pool,plan,0)['actual_count']==30
    prompt=load_prompt('board/hypothesis',NEW)['system_prompt']
    assert 'does not require using every eligible predictor' in prompt
    assert catalog.resolve(OLD)['content'] in load_prompt('board/hypothesis',OLD)['system_prompt']
    assert OLD not in {s['id'] for s in catalog.catalog()}
    assert NEW in {s['id'] for s in catalog.catalog()}
    with pytest.raises(ValueError,match='historical all-predictor'):
        catalog.validate_new_design({'combination_skills':choices([OLD])})
