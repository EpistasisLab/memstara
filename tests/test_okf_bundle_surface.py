"""Exercise the real OKF reader with a synthetic nested bundle, no cohort data."""
import json

import pytest

pytest.importorskip("motoro.mcp_servers.okf")
from memstara.mcp_servers import okf


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    for relative, branch in [("alpha/deep/one.md", "a"), ("beta/two.md", "b")]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\ntitle: Synthetic finding\nbranch: {branch}\n---\n## Evidence\nSynthetic only.\n")
    monkeypatch.setattr(okf, "_bundle_root", lambda: tmp_path)
    monkeypatch.delenv("MEMSTARA_OKF_FIELDS", raising=False)
    return tmp_path


def test_nested_bundle_loads_and_is_addressable(bundle):
    result = json.loads(okf.okf_list_domains())
    assert result["total"] == 2
    assert {d["slug"]: d["documents"] for d in result["domains"]} == {"alpha": 1, "beta": 1}
    result = json.loads(okf.okf_read("alpha/deep/one"))
    assert "Synthetic only." in json.dumps(result)
    assert '"error"' not in json.dumps(result)


def test_domains_respect_same_lock_as_reader(bundle, monkeypatch):
    monkeypatch.setenv("MEMSTARA_OKF_FIELDS", "branch=a")
    result = json.loads(okf.okf_list_domains())
    assert result["total"] == 1
    assert [d["slug"] for d in result["domains"]] == ["alpha"]
    assert "outside" in okf.okf_read("beta/two")


def test_invalid_lock_is_an_error_not_an_unconfined_count(bundle, monkeypatch):
    monkeypatch.setenv("MEMSTARA_OKF_FIELDS", "invalid")
    assert "error" in json.loads(okf.okf_list_domains())


def test_search_domain_suggestions_remain_inside_locked_branch(bundle, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OKF_FIELDS', 'branch=a')
    result = json.loads(okf.okf_search('synthetic', domain='missing-domain'))
    assert result['domains'] == ['alpha']


def test_invalid_lock_is_checked_before_domain_suggestions(bundle, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OKF_FIELDS', 'invalid')
    result = json.loads(okf.okf_search('synthetic', domain='missing-domain'))
    assert 'not a filter' in result['error']
    assert 'domains' not in result


def test_empty_search_filter_suggestions_remain_inside_locked_branch(bundle, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OKF_FIELDS', 'branch=a')
    result = json.loads(okf.okf_search('synthetic', tags='absent-tag'))
    assert result['values']['branch'] == ['a']


def test_failed_read_is_saved_outside_trace_files(bundle, monkeypatch):
    config = bundle / "run-config.json"
    config.write_text("{}")
    monkeypatch.setenv("MEMSTARA_RUN_CONFIG", str(config))
    response = okf.okf_read("alpha/deep/one,absent-document")
    assert "no document answers" in response
    event = json.loads((bundle / "knowledge_reads.jsonl").read_text())
    assert [row["status"] for row in event["results"]] == ["read", "failed"]
    assert event["results"][1]["ref"] == "absent-document"
    assert "Synthetic only." not in json.dumps(event)


def test_audit_failure_is_not_silently_hidden(bundle, monkeypatch):
    monkeypatch.setenv("MEMSTARA_RUN_CONFIG", str(bundle / "missing-directory" / "config.json"))
    assert "audit_error" in json.loads(okf.okf_read("alpha/deep/one"))


def test_auto_section_reads_kg_instances_instead_of_nonexistent_bottom_line(bundle):
    path = bundle / 'alpha' / 'kg.md'
    path.write_text('---\ntitle: KG example\n---\n# Metapath\nSYMPTOMMANIFESTATIONOFDISEASE\n'
                    '# Evidence — OBSERVED\nObserved support.\n# Instances\nDelirium → clinical entity\n')
    result = json.loads(okf._read_documents('kg', section='auto'))
    row = result['documents'][0] if 'documents' in result else result['results'][0]
    assert row['section'] == 'Instances'
    assert 'Delirium' in row['text']
    assert 'SYMPTOMMANIFESTATIONOFDISEASE' not in row['text']
    assert 'Evidence — OBSERVED' in row['sections']


def test_auto_section_preserves_literature_and_whole_body_fallback(bundle):
    (bundle / 'alpha' / 'paper.md').write_text('---\ntitle: Paper\n---\n# Bottom line\nConclusion.\n')
    assert 'Conclusion.' in okf._read_documents('paper', section='auto')
    assert 'Synthetic only.' in okf._read_documents('alpha/deep/one', section='auto')


@pytest.fixture
def classified_bundle(bundle):
    (bundle / 'alpha/deep/one.md').write_text(
        '---\ntitle: HIV synthetic finding\nterminus_kind: psychiatric\n'
        'mechanism_family: comorbidity\n---\nSynthetic.\n')
    (bundle / 'beta/two.md').write_text(
        '---\ntitle: HIV synthetic finding\nterminus_kind: sud\nmechanism_family: toxicity\n---\nSynthetic.\n')
    return bundle


def test_invalid_filter_never_reaches_scoring(classified_bundle, monkeypatch):
    def forbidden(_):
        pytest.fail('Invalid filters must be rejected before search scoring')
    monkeypatch.setattr(okf, '_idf', forbidden)
    for kwargs in ({'fields': 'terminus_kind=hiv'}, {'filters': {'terminus_kind': 'hiv'}}):
        result = json.loads(okf.okf_search('HIV', **kwargs))
        assert result['code'] == 'invalid_filter'
        assert result['searched'] == 0
        assert result['values']['terminus_kind'] == ['psychiatric', 'sud']
        assert result['requested_filters'] == {'terminus_kind': 'hiv'}


def test_topic_search_correction_and_legacy_equivalence(classified_bundle):
    assert json.loads(okf.okf_search('HIV'))['searched'] == 2
    selected = json.loads(okf.okf_search('HIV', filters={'terminus_kind': 'sud'}))
    assert selected == json.loads(okf.okf_search('HIV', fields='terminus_kind=sud'))
    assert selected['searched'] == 1
    assert selected['applied_filters'] == {'terminus_kind': 'sud'}
    assert 'error' in json.loads(okf.okf_search('HIV', fields='terminus_kind=sud',
                                              filters={'terminus_kind': 'psychiatric'}))


def test_choices_and_search_respect_lock(classified_bundle, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OKF_FIELDS', 'terminus_kind=sud')
    choices = json.loads(okf.okf_list_domains())['filter_options']
    assert choices == {'terminus_kind': ['sud'], 'mechanism_family': ['toxicity']}
    assert 'error' in json.loads(okf.okf_search('HIV', filters={'terminus_kind': 'psychiatric'}))
    assert json.loads(okf.okf_search('HIV'))['searched'] == 1
    result = json.loads(okf.okf_search('HIV', filters={'mechanism_family': 'comorbidity'}))
    assert result['code'] == 'invalid_filter'
    assert result['values'] == {'mechanism_family': ['toxicity']}


def test_valid_values_with_empty_intersection_do_not_broaden(classified_bundle):
    result = json.loads(okf.okf_search('HIV', filters={
        'terminus_kind': 'sud', 'mechanism_family': 'comorbidity'}))
    assert 'error' in result
    assert 'results' not in result


def test_model_schema_uses_bundle_choices_and_rejects_invention(classified_bundle):
    import asyncio
    from mcp.server.fastmcp.exceptions import ToolError

    okf.register_search_schema()

    async def check():
        tool = next(t for t in await okf.mcp.list_tools() if t.name == 'okf_search')
        schema = tool.inputSchema
        assert schema['properties']['fields']['const'] == ''
        assert 'filters' in schema['properties']
        encoded = json.dumps(schema)
        assert 'psychiatric' in encoded and 'sud' in encoded
        assert '"hiv"' not in encoded
        with pytest.raises(ToolError):
            await okf.mcp.call_tool('okf_search', {'queries': 'HIV', 'filters': {'terminus_kind': 'hiv'}})
        with pytest.raises(ToolError):
            await okf.mcp.call_tool('okf_search', {'queries': 'HIV', 'filters': {'unknown': 'sud'}})
        with pytest.raises(ToolError):
            await okf.mcp.call_tool('okf_search', {'queries': 'HIV', 'fields': 'terminus_kind=hiv'})
        response = await okf.mcp.call_tool('okf_search', {'queries': 'HIV', 'filters': {'terminus_kind': 'sud'}})
        assert 'applied_filters' in str(response)
    asyncio.run(check())


def test_schema_without_classifications_allows_unfiltered_search(bundle):
    import asyncio
    okf.register_search_schema()
    async def check():
        result = await okf.mcp.call_tool('okf_search', {'queries': 'Synthetic'})
        assert 'searched' in str(result)
    asyncio.run(check())
