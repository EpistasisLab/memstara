"""Read-only experiment registry queries; no filesystem inventory is required."""
import json
from fastapi import HTTPException
from db import pools


def decode(row):
    return {k: json.loads(v) if k in ('definition','configuration','prompts','outcome','metadata','evidence','receipt','evaluation','metrics') and isinstance(v,str) else v
            for k,v in dict(row).items()}


async def query(fn):
    result = await pools.guarded('memstara',fn,None)
    if result is None:
        raise HTTPException(503,'Experiment registry is unavailable. No empty result is assumed.')
    return result


async def inventory():
    async def fetch(conn):
        rows = await conn.fetch('''SELECT e.id,e.definition,e.created_at,
            (SELECT count(*) FROM memstara_experiment_combinations c WHERE c.experiment_id=e.id) combinations,
            (SELECT count(*) FROM memstara_executions r WHERE r.experiment_id=e.id) executions
            FROM memstara_experiments e ORDER BY e.created_at DESC LIMIT 500''')
        return [decode(r) for r in rows]
    return await query(fetch)


async def experiment(experiment_id):
    async def fetch(conn):
        rows=await conn.fetch('''SELECT c.id,(c.definition - 'configuration') ||
            jsonb_build_object('skills',c.definition#>'{configuration,books}') AS definition,
            r.run_tag,r.status,r.synced_at,
            (SELECT sum(a.duration_seconds) FROM memstara_execution_agents a WHERE a.run_tag=r.run_tag) agent_seconds,
            (SELECT sum((x.receipt->>'usd')::numeric) FROM memstara_execution_costs x WHERE x.run_tag=r.run_tag) estimated_usd,
            (SELECT count(*) FROM memstara_execution_costs x WHERE x.run_tag=r.run_tag AND x.receipt->>'usd' IS NULL) unpriced_calls,
            (SELECT count(*) FROM memstara_execution_costs x WHERE x.run_tag=r.run_tag) priced_attempts
            ,(SELECT jsonb_agg(jsonb_build_object('task_id',x.task_id,'model',m.key,'auc',m.value->'auc',
                'f1',m.value#>'{evaluation,replicates,0,f1}')) FROM memstara_results x
                CROSS JOIN LATERAL jsonb_each(x.evaluation->'model_results') m WHERE x.run_tag=r.run_tag) metrics
            FROM memstara_experiment_combinations c LEFT JOIN memstara_executions r
            ON r.experiment_id=c.experiment_id AND r.combination_id=c.id
            WHERE c.experiment_id=$1 ORDER BY c.id,r.synced_at''',experiment_id)
        return [decode(r) for r in rows]
    return await query(fetch)


async def execution(tag):
    async def fetch(conn):
        row=await conn.fetchrow('SELECT * FROM memstara_executions WHERE run_tag=$1',tag)
        if not row:
            raise HTTPException(404,'Execution is not registered')
        result=decode(row)
        for key,table,order in [('agents','memstara_execution_agents','started_at'),
                               ('costs','memstara_execution_costs','id'),
                               ('artifacts','memstara_execution_artifacts','path')]:
            result[key]=[decode(r) for r in await conn.fetch(f'SELECT * FROM {table} WHERE run_tag=$1 ORDER BY {order}',tag)]
        result['results']=[decode(r) for r in await conn.fetch('SELECT * FROM memstara_results WHERE run_tag=$1 ORDER BY result_id',tag)]
        return result
    return await query(fetch)
