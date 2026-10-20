"""Source provenance and query isolation, including missing historical metadata."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer' / 'api'))
import discovery_sources as sources
import discovery
from fastapi import HTTPException


def test_identity_uses_documents_not_paths_or_question_topics():
    base = {'knowledge_hashes': {'a.md': 'a', 'b.md': 'b'}}
    identity = sources.source_identity(base)[0]
    assert identity.startswith('okf_')
    assert sources.source_identity({**base, 'okf_path': '/private/other', 'dataset': 'other'})[0] == identity
    assert sources.source_identity({'research_profile': {'artifact_hashes': {'okf/b.md':'b','okf/a.md':'a','dataset.csv':'x'}}})[0] == identity
    assert sources.source_identity({'knowledge_hashes': {'a.md': 'changed', 'b.md': 'b'}})[0] != identity


@pytest.mark.parametrize('config', [None, {}, {'knowledge_hashes':[]}, {'research_profile':{'configuration':[], 'artifact_hashes':[]}}, {'knowledge_policy':[]}, {'knowledge_hashes':{1:'x'}}])
def test_missing_or_malformed_provenance_is_unknown(config):
    assert sources.source_identity(config)[0] == 'unknown'


def test_explicit_no_knowledge_is_not_unknown():
    assert sources.source_identity({'knowledge_mode':'llm_only'})[0] == 'none'
    assert sources.source_identity({'knowledge_policy':{'mode':'no_okf'}})[0] == 'none'


def test_catalog_counts_and_unknown_history_do_not_expose_paths():
    config = {'knowledge_hashes':{'a.md':'x'}, 'okf_path':'/private/path'}
    key = sources.source_identity(config)[0]
    rows = [{'run_tag':'a','count':2},{'run_tag':'b','count':3},{'run_tag':'missing','count':4},{'run_tag':'none','count':1}]
    with patch.object(sources.run_artifacts,'configs',return_value={'a':config,'b':config,'none':{'knowledge_mode':'llm_only'}}), patch.object(sources.pools,'guarded',AsyncMock(return_value=rows)):
        result = asyncio.run(sources.sources())
        assert {v['id']:v['count'] for v in result['sources']} == {'all':10,key:5,'unknown':4,'none':1}
        assert '/private/path' not in str(result)
        assert asyncio.run(sources.scope(key)) == ['a','b']
        assert asyncio.run(sources.scope('okf_'+'0'*64)) == []


def test_invalid_scope_and_catalog_outage_fail_explicitly():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(sources.scope('../all'))
    assert exc.value.status_code == 422
    with patch.object(sources.run_artifacts,'configs',return_value={}), patch.object(sources.pools,'guarded',AsyncMock(return_value=None)), pytest.raises(HTTPException) as exc:
        asyncio.run(sources.scope('unknown'))
    assert exc.value.status_code == 503


def test_source_and_search_are_applied_before_pagination_and_to_count():
    conn = AsyncMock();conn.fetch.return_value=[];conn.fetchval.return_value=0
    async def guarded(store, read, fallback): return await read(conn)
    with patch.object(sources,'scope',AsyncMock(return_value=['run-a'])), patch.object(discovery.pools,'guarded',guarded):
        result = asyncio.run(discovery.question_list(42,'unknown','clinical'))
    sql,before,tags,query = conn.fetch.call_args.args
    assert (before,tags,query) == (42,['run-a'],'clinical')
    assert sql.index('ANY($2)') < sql.index('LIMIT 121')
    assert sql.index('strpos') < sql.index('LIMIT 121')
    assert conn.fetchval.call_args.args[1:] == (['run-a'],'clinical')
    assert result['total']==0


def test_evidence_rejects_question_from_other_source():
    conn=AsyncMock();conn.fetchrow.return_value={'origin_run':'other'}
    async def guarded(store, read, fallback): return await read(conn)
    with patch.object(sources,'scope',AsyncMock(return_value=['run-a'])), patch.object(discovery.pools,'guarded',guarded), pytest.raises(HTTPException) as exc:
        asyncio.run(discovery.question_detail(1,'unknown'))
    assert exc.value.status_code==404
    conn.fetch.assert_not_awaited()


def test_semantic_and_novelty_receive_the_same_source_scope():
    conn=AsyncMock();conn.fetch.return_value=[]
    async def guarded(store, read, fallback): return await read(conn)
    with patch.object(sources,'scope',AsyncMock(return_value=['run-a'])), patch.object(discovery.pools,'guarded',guarded), patch('universe_semantics.index',return_value={'indexed_count':0}) as index:
        asyncio.run(discovery.semantic_questions(source='unknown'))
        index.assert_called_once_with([], '', None, scope='unknown')
        assert conn.fetch.call_args.args[1] == ['run-a']
        asyncio.run(discovery.novelty_ranking(source='unknown'))
        assert conn.fetch.call_args.args[3] == ['run-a']
        assert 'q.origin_run' in conn.fetch.call_args.args[0]
        assert 'r.run_tag = ANY($3)' in conn.fetch.call_args.args[0]
