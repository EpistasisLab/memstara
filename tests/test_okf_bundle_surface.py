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
