"""Delete execution records only; retain study, agent and workspace definitions.

Run with control/API/web stopped. Default is a read-only plan; --apply deletes.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil

BOARD_TABLES = (
    "memstara_execution_artifacts", "memstara_execution_costs", "memstara_execution_agents",
    "memstara_executions", "memstara_results", "memstara_blackboard", "memstara_questions",
    "memstara_experiment_combinations", "memstara_experiments",
)
RUNTIME_CHILDREN = ("messages", "run_steps", "flat", "memory_entries")


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def preserved(root):
    candidates = [root / "runs/pipeline_workspace.json", root / "skills",
                  root / "private-model-connections", root / "skill_aliases.json",
                  Path(os.environ.get("MEMSTARA_INPUTS_DIR", "/app/user-inputs"))]
    files = [p for item in candidates for p in (item.rglob("*") if item.is_dir() else [item]) if p.is_file()]
    files.extend((root / "research_inputs").glob("*.json"))
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def targets(root):
    result = []
    for p in (root / "runs").iterdir() if (root / "runs").exists() else ():
        if p.name in {"pipeline_workspace.json", "history_epoch.json"}:
            continue
        if not p.is_dir() or not (p / "control_record.json").is_file():
            raise RuntimeError(f"Unrecognized runs entry; not deleting: {p.name}")
        result.append(p)
    logs = root / "logs"
    if logs.exists():
        result.extend(logs.iterdir())
    result.extend((root / "research_inputs/prepared").glob("*/derived"))
    for p in result:
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("Cleanup target escapes output root")
    return result


async def tables(conn):
    return {r["tablename"] for r in await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'")}


def validate_board_dependencies(edges):
    for edge in edges:
        if edge['parent'] in BOARD_TABLES and (edge['child_schema'] != 'public' or edge['child'] not in BOARD_TABLES):
            raise RuntimeError('Unknown dependency on execution history; nothing deleted')


def runtime_cleanup_plan(existing, columns, edges, *, include_agent_memories=True):
    """Follow actual FK columns; never assume memory uses a column named run_id."""
    allowed = {"agent_runs", *RUNTIME_CHILDREN}
    incoming = {name: [] for name in allowed}
    for edge in edges:
        child, parent = edge["child"], edge["parent"]
        if parent not in allowed:
            continue
        if edge["child_schema"] != "public" or child not in allowed:
            raise RuntimeError(f"Unrecognized runtime dependency: {child} -> {parent}; nothing deleted")
        if not edge["child_columns"] or len(edge["child_columns"]) != len(edge["parent_columns"]):
            raise RuntimeError("Invalid runtime foreign key metadata; nothing deleted")
        incoming[child].append(edge)
    predicates, order = {}, []

    def visit(table, visiting):
        if table in predicates:
            return predicates[table]
        if table in visiting:
            raise RuntimeError("Cyclic runtime dependencies require review; nothing deleted")
        if table == "agent_runs":
            if incoming[table]:
                raise RuntimeError("Unexpected run-to-child dependency; nothing deleted")
            predicate = '"id"=ANY($1::uuid[])'
        else:
            terms = []
            for edge in incoming[table]:
                parent = edge["parent"]
                parent_predicate = visit(parent, visiting | {table})
                child_cols = ", ".join(quote(c) for c in edge["child_columns"])
                if len(edge["child_columns"]) > 1:
                    child_cols = f"({child_cols})"
                parent_cols = ", ".join(quote(c) for c in edge["parent_columns"])
                terms.append(f"{child_cols} IN (SELECT {parent_cols} FROM public.{quote(parent)} "
                             f"WHERE {parent_predicate})")
            # Older runtime versions contain run-linked rows without an FK.
            if "run_id" in columns.get(table, set()):
                terms.append('"run_id"=ANY($1::uuid[])')
            if include_agent_memories and table == 'memory_entries' and 'agent_id' in columns.get(table, set()):
                # Semantic/episodic memories can outlive their run FK. Reset the
                # installation's agent memories too, without removing the agents.
                terms.append('"agent_id" IN (SELECT id FROM public.agents WHERE name LIKE \'memstara%\' '
                             'OR id IN (SELECT agent_id FROM public.agent_runs WHERE id=ANY($1::uuid[])))')
            if not terms and table == 'memory_entries' and not include_agent_memories:
                # Unattributed agent memory may be shared by other experiments.
                terms.append('FALSE AND $1::uuid[] IS NOT NULL')
            if not terms:
                raise RuntimeError(f"Cannot safely scope {table} to executions; nothing deleted")
            predicate = "(" + " OR ".join(terms) + ")"
        predicates[table] = predicate
        order.append(table)
        return predicate

    for table in sorted(allowed & existing):
        visit(table, set())
    return [(table, predicates[table]) for table in reversed(order)]


async def main(apply, *, root=None, on_phase=None, scope=None):
    import asyncpg

    supplied_root = root
    root = Path(root or os.environ.get("MEMSTARA_OUTPUT_DIR", "/app/outputs")).resolve()
    if supplied_root is None and root != Path("/app/outputs"):
        raise RuntimeError("Expected this deployment's /app/outputs mount")
    keep = preserved(root)
    paths = targets(root) if scope is None else [Path(p) for p in scope['paths'] if Path(p).exists()]
    if scope is not None:
        from memstara.control.history_scope import validate_paths
        validate_paths(root, paths)
    connections = []
    transactions = []
    try:
        for key in ("MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL"):
            url = os.environ[key].replace("postgresql+asyncpg://", "postgresql://", 1)
            conn = await asyncpg.connect(url, timeout=15)
            connections.append(conn)
            tx = conn.transaction()
            await tx.start()
            transactions.append(tx)
            await conn.execute("SET LOCAL lock_timeout = '10s'")
        board, runtime = connections
        if scope is not None:
            import zlib
            for tag in scope['run_tags']:
                if not await board.fetchval('SELECT pg_try_advisory_xact_lock($1::bigint)', zlib.crc32(tag.encode('utf-8'))):
                    raise RuntimeError('A selected execution still owns its database lease; nothing deleted')
        bt, rt = await tables(board), await tables(runtime)
        if not {"memstara_blackboard", "memstara_results", "memstara_questions"} <= bt:
            raise RuntimeError("Unexpected research DB schema; nothing deleted")
        if not {"agents", "agent_runs"} <= rt:
            raise RuntimeError("Unexpected runtime DB schema; nothing deleted")
        if scope is not None:
            if await board.fetchval('''SELECT count(*) FROM memstara_executions
                    WHERE run_tag=ANY($1::text[]) AND pipeline_id IS DISTINCT FROM $2''',
                    scope['run_tags'], scope.get('pipeline_id')):
                raise RuntimeError('Execution ownership changed; nothing deleted')
            # Recheck sharing after backup: another live experiment may have
            # indexed a generated artifact since the deletion plan was recorded.
            for row in await board.fetch('''SELECT path FROM memstara_execution_artifacts
                    WHERE NOT (run_tag=ANY($1::text[]))''', scope['run_tags']):
                shared_path = Path(row['path'])
                if any(shared_path == path or (path.is_dir() and shared_path.is_relative_to(path)) for path in paths):
                    raise RuntimeError('An execution file is now shared by another experiment; nothing deleted')
        validate_board_dependencies(await board.fetch("""SELECT child.relname AS child, parent.relname AS parent,
            ns.nspname AS child_schema FROM pg_constraint c
            JOIN pg_class child ON child.oid=c.conrelid JOIN pg_namespace ns ON ns.oid=child.relnamespace
            JOIN pg_class parent ON parent.oid=c.confrelid
            WHERE c.contype='f' AND parent.relnamespace='public'::regnamespace
            AND parent.relname=ANY($1::text[])""", list(BOARD_TABLES)))
        run_ids = [r["id"] for r in await runtime.fetch(
            "SELECT r.id FROM agent_runs r JOIN agents a ON a.id=r.agent_id WHERE a.name LIKE 'memstara%'")] if scope is None else scope['runtime_run_ids']
        # The registry also owns calls made through uploaded/custom agents.
        if "memstara_execution_agents" in bt:
            run_ids = list(set(run_ids) | {r["agent_run_id"] for r in await board.fetch(
                "SELECT DISTINCT agent_run_id FROM memstara_execution_agents WHERE agent_run_id IS NOT NULL" +
                (" AND run_tag=ANY($1::text[])" if scope is not None else ''),
                *([scope['run_tags']] if scope is not None else []))})
        if scope is not None:
            # Shared calls are retained even if the selected experiment references them.
            shared = {r['agent_run_id'] for r in await board.fetch(
                'SELECT DISTINCT agent_run_id FROM memstara_execution_agents WHERE NOT (run_tag=ANY($1::text[]))',
                scope['run_tags'])}
            from uuid import UUID
            shared.update(UUID(str(value)) for value in scope.get('shared_runtime_run_ids', []))
            run_ids = list({UUID(str(value)) for value in run_ids} - shared)
        # Reject unfamiliar FK dependents rather than cascading into unknown data.
        edges = await runtime.fetch("""SELECT child.relname AS child, parent.relname AS parent,
            ns.nspname AS child_schema,
            ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(num, pos)
                  JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num ORDER BY k.pos) AS child_columns,
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(num, pos)
                  JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num ORDER BY k.pos) AS parent_columns
            FROM pg_constraint c JOIN pg_class child ON child.oid=c.conrelid
            JOIN pg_namespace ns ON ns.oid=child.relnamespace
            JOIN pg_class parent ON parent.oid=c.confrelid
            WHERE c.contype='f' AND parent.relnamespace='public'::regnamespace
            AND parent.relname=ANY($1::text[])""", ["agent_runs", *RUNTIME_CHILDREN])
        columns = {}
        for row in await runtime.fetch("""SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name=ANY($1::text[])""", ["agent_runs", *RUNTIME_CHILDREN]):
            columns.setdefault(row["table_name"], set()).add(row["column_name"])
        runtime_plan = runtime_cleanup_plan(rt, columns, edges, include_agent_memories=scope is None)
        if scope is not None:
            from memstara.control.history_scope import board_predicates
            predicates = board_predicates(scope)
        else:
            predicates = {t: ('TRUE', []) for t in BOARD_TABLES}
        counts = {t: await board.fetchval(f"SELECT count(*) FROM public.{quote(t)} WHERE {predicates[t][0]}", *predicates[t][1])
                  for t in BOARD_TABLES if t in bt}
        print(json.dumps({"apply": apply, "research_rows": counts, "runtime_runs": len(run_ids),
                          "remove_paths": [str(p) for p in paths],
                          "preserved_settings_files": len(keep),
                          "runtime_cleanup_order": [table for table, _ in runtime_plan]}, indent=2), flush=True)
        if not apply:
            return
        if on_phase:
            on_phase("clearing_databases")
        # Delete children explicitly. Unexpected RESTRICT constraints abort both transactions.
        for table, predicate in runtime_plan:
            await runtime.execute(f"DELETE FROM public.{quote(table)} WHERE {predicate}", run_ids)
        for table in BOARD_TABLES:
            if table in bt:
                predicate, args = predicates[table]
                await board.execute(f"DELETE FROM public.{quote(table)} WHERE {predicate}", *args)
        if preserved(root) != keep:
            raise RuntimeError("Settings changed during cleanup")
        for tx in transactions:
            await tx.commit()
        transactions.clear()
        if on_phase:
            on_phase("clearing_files")
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        if preserved(root) != keep:
            raise RuntimeError("Settings preservation check failed")
        for table in BOARD_TABLES:
            if table in bt and await board.fetchval(f"SELECT count(*) FROM public.{quote(table)} WHERE {predicates[table][0]}", *predicates[table][1]):
                raise RuntimeError("Execution database verification failed")
        if await runtime.fetchval("SELECT count(*) FROM agent_runs WHERE id=ANY($1::uuid[])", run_ids):
            raise RuntimeError("Runtime execution verification failed")
        print("Execution history removed. Workspace, research, model and agent settings preserved.")
        print("No experiment started. Database schemas and sequence values retained.")
    finally:
        for tx in transactions:
            try:
                await tx.rollback()
            except Exception:
                pass
        for conn in connections:
            await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    from memstara.control.history_gate import maintenance_guard, quiescent_ml

    cleanup_root = Path(os.environ.get("MEMSTARA_OUTPUT_DIR", "/app/outputs"))
    with maintenance_guard(cleanup_root), quiescent_ml(cleanup_root):
        apply = parser.parse_args().apply
        asyncio.run(main(apply))
        if apply:
            from uuid import uuid4
            from memstara.control.history import HistoryReset

            identifier = str(uuid4())
            HistoryReset(None, None)._save({'id': identifier, 'state': 'completed',
                'revision': identifier, 'blocked': False,
                'message': 'Execution history cleared by the startup maintenance command.'})
