"""Keep educational source links and agent tool permissions aligned with this checkout."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES = (ROOT / 'viewer/web/src/developer/agentStories.ts').read_text()
ACTORS = json.loads(STORIES.split('export const actors:Actor[] = ', 1)[1].split(';\nexport const scenarios:', 1)[0])
SCENARIOS = json.loads(STORIES.split('export const scenarios:Scenario[] = ', 1)[1].strip().removesuffix(';'))


def test_every_transfer_has_known_endpoints_and_existing_source():
    identifiers = {a['id'] for a in ACTORS}
    assert len(identifiers) == len(ACTORS)
    for scenario in SCENARIOS:
        assert len({s['id'] for s in scenario['steps']}) == len(scenario['steps'])
        for step in scenario['steps']:
            assert {step['fromId'], step['toId'], step['owner']} <= identifiers
            assert step['fromId'] != step['toId']
            assert (ROOT / step['source']).is_file()
    for actor in ACTORS:
        assert (ROOT / actor['source']).is_file()
        for source in (actor.get('profile') or {}).get('sources', []):
            assert (ROOT / source).is_file()


def test_agent_tool_descriptions_match_actual_permissions():
    tree = ast.parse((ROOT / 'src/memstara/pipeline/core.py').read_text())
    permissions = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'BOARD_TOOLS' for t in node.targets))
    for actor in ACTORS:
        if actor['kind'] != 'agent':
            continue
        shown = actor['profile']['tools']
        if actor['id'] == 'hypothesis':
            shown = shown[1].split(': ', 1)[1].split(', ')
        assert set(shown) == permissions[actor['id']]
    policy = ast.parse((ROOT / 'src/memstara/pipeline/scientific_policy.py').read_text())
    question_tools = next(ast.literal_eval(n.value.args[0]) for n in policy.body
                          if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'PRIMARY_QUESTION_TOOLS' for t in n.targets))
    displayed = next(a for a in ACTORS if a['id'] == 'hypothesis')['profile']['tools'][0]
    assert set(displayed.split(': ', 1)[1].split(', ')) == question_tools


def test_narrative_examples_use_the_real_fixed_target_templates():
    source = ast.parse((ROOT / 'src/memstara/pipeline/question_contract.py').read_text())
    templates = ast.Module(body=[n for n in source.body
                                if isinstance(n, ast.FunctionDef)
                                and n.name in {'question_text', 'hypothesis_text'}], type_ignores=[])
    namespace = {}
    exec(compile(templates, '<question templates>', 'exec'), namespace)
    contract = {'predictor_concepts': ['Marker A', 'Marker B'], 'target': 'Y'}
    narrative = (ROOT / 'viewer/web/src/developer/PipelineNarrative.tsx').read_text()
    assert namespace['question_text'](contract) in narrative
    assert namespace['hypothesis_text'](contract) in narrative
    focused = (ROOT / 'viewer/web/src/developer/HypothesisLesson.tsx').read_text()
    assert namespace['question_text'](contract) in focused
    assert namespace['hypothesis_text'](contract) in focused
