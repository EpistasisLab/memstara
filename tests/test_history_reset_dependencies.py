"""Exercise scoped deletion predicates with FK-enforced synthetic records."""
import importlib.util
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location(
    "reset_history", Path(__file__).resolve().parents[1] / "deployment/reset-execution-history.py")
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


def edge(child, parent, child_column, parent_column="id"):
    return {"child": child, "parent": parent, "child_schema": "public",
            "child_columns": [child_column], "parent_columns": [parent_column]}


def test_memory_with_different_fk_column_and_nested_steps_preserves_unrelated_rows():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("ATTACH DATABASE ':memory:' AS public")
    db.executescript('''
      CREATE TABLE public.agents(id TEXT PRIMARY KEY, configuration TEXT);
      CREATE TABLE public.agent_runs(id TEXT PRIMARY KEY, agent_id TEXT REFERENCES agents(id));
      CREATE TABLE public.run_steps(id TEXT PRIMARY KEY, run_id TEXT REFERENCES agent_runs(id));
      CREATE TABLE public.memory_entries(id TEXT PRIMARY KEY,
          source_run_id TEXT REFERENCES agent_runs(id), step_id TEXT REFERENCES run_steps(id));
      INSERT INTO public.agents VALUES ('configured-agent', 'preserve');
      INSERT INTO public.agent_runs VALUES ('old', 'configured-agent'), ('other', 'configured-agent');
      INSERT INTO public.run_steps VALUES ('old-step', 'old'), ('other-step', 'other');
      INSERT INTO public.memory_entries VALUES ('old-memory', 'old', NULL),
          ('step-memory', NULL, 'old-step'), ('other-memory', 'other', 'other-step'),
          ('unlinked-memory', NULL, NULL);
    ''')
    columns = {"agent_runs": {"id"}, "run_steps": {"id", "run_id"},
               "memory_entries": {"id", "source_run_id", "step_id"}}
    plan = reset.runtime_cleanup_plan(set(columns), columns, [
        edge("run_steps", "agent_runs", "run_id"),
        edge("memory_entries", "agent_runs", "source_run_id"),
        edge("memory_entries", "run_steps", "step_id"),
    ])
    assert [table for table, _ in plan] == ["memory_entries", "run_steps", "agent_runs"]
    for table, predicate in plan:
        # SQLite supplies the relational/FK check; PostgreSQL binds a UUID array.
        predicate = predicate.replace("=ANY($1::uuid[])", " IN ('old')")
        db.execute(f'DELETE FROM public."{table}" WHERE {predicate}')
    assert db.execute("SELECT id FROM public.agent_runs").fetchall() == [("other",)]
    assert db.execute("SELECT id FROM public.run_steps").fetchall() == [("other-step",)]
    assert set(db.execute("SELECT id FROM public.memory_entries")) == {("other-memory",), ("unlinked-memory",)}
    assert db.execute("SELECT configuration FROM public.agents").fetchall() == [("preserve",)]
    db.close()


def test_unknown_dependent_is_rejected_before_deletion():
    with pytest.raises(RuntimeError, match="Unrecognized runtime dependency"):
        reset.runtime_cleanup_plan({"agent_runs"}, {}, [edge("settings", "agent_runs", "last_run_id")])


def test_memory_without_execution_link_is_not_blindly_deleted():
    with pytest.raises(RuntimeError, match="Cannot safely scope memory_entries"):
        reset.runtime_cleanup_plan({"agent_runs", "memory_entries"}, {"memory_entries": {"id", "content"}}, [])
