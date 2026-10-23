"""Persist independently configured pipeline definitions without a fixed count cap."""

import copy
import json
import threading
import uuid
from pathlib import Path
from typing import Any

from memstara.control.request import DEFAULTS, normalize_agent_configuration, playbook_field
from memstara.agent_labels import AGENT_LABELS
from memstara.pipeline.checkpoint import atomic_json


def loop_totals(records):
    """Count recorded Loop attempts across executions, never configured budgets."""
    totals = dict(attempted=0, completed=0, blocked=0, unknown_executions=0)
    seen = set()
    for record in records:
        tag = record.get("run_tag")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        try:
            progress = json.loads((Path(record["run_dir"]) / "progress.json").read_text())
            outcome = progress.get("exploration") or {}
            attempted = outcome.get("attempted", progress.get("iteration"))
            if type(attempted) is not int or attempted < 0:
                raise ValueError("No recorded Loop count")
            totals["attempted"] += attempted
            for field in ("completed", "blocked"):
                value = outcome.get(field, 0)
                if type(value) is int and value >= 0:
                    totals[field] += value
        except (OSError, ValueError, KeyError, TypeError):
            totals["unknown_executions"] += 1
    return totals


class PipelineWorkspace:
    def __init__(self, path: Path, manager_factory):
        self.path = path
        self.lock = threading.RLock()
        self.factory = manager_factory
        self.managers: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text())
            if not isinstance(data, list):
                raise ValueError("Invalid pipeline workspace; preserve the file and repair it")
            self.items = [{**item, "agent_labels": dict(AGENT_LABELS),
                           "configuration": self.read_configuration(item.get("configuration", {}))[0]}
                          for item in data]
            if self.items != data:
                self._save()
        else:
            self.items = []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.path, self.items)

    def manager(self, key):
        if not any(p["id"] == key for p in self.items):
            raise ValueError("Pipeline does not exist")
        if key not in self.managers:
            self.managers[key] = self.factory(key)
        return self.managers[key]

    def list(self):
        with self.lock:
            out = []
            removed = []
            for item in list(self.items):
                manager = self.manager(item["id"])
                current = manager.running()
                # A deletion request for a live execution is finalized only after
                # its controller reaps the child. This prevents removing ownership
                # while the child is still writing its run artifacts.
                if item.get("deleting") and current is None:
                    removed.append(item)
                    continue
                history = manager.finished()
                latest = current or (history[0] if history else None)
                progress = {}
                if latest:
                    try:
                        progress = json.loads((Path(latest["run_dir"]) / "progress.json").read_text())
                    except (OSError, ValueError):
                        pass
                if latest:
                    # Historical progress must use that execution's frozen limit,
                    # even after the user changes the next execution's settings.
                    try:
                        frozen = json.loads((Path(latest["run_dir"]) / "config.json").read_text())
                        latest = {**latest, "configuration": {
                            "waves": frozen.get("waves"), "continuous": frozen.get("continuous", False),
                            "combination_plan": frozen.get("combination_plan")}}
                        if current:
                            current = {**current, "configuration": {**current.get("configuration", {}),
                                       **latest["configuration"]}}
                    except (OSError, ValueError):
                        pass
                configuration, configuration_error = self.read_configuration(item["configuration"])
                from memstara.pipeline.failures import visible_failure
                failure = visible_failure(latest["run_dir"], include_legacy=(
                    not current and latest.get("exit_code") not in (None, 0))) if latest else None
                out.append({**copy.deepcopy(item), "configuration": configuration,
                            "failure": failure,
                            "configuration_error": configuration_error,
                            "running": current, "latest": latest, "progress": progress,
                            "deleting": bool(item.get("deleting")),
                            "loop_totals": loop_totals(manager.history_records() if hasattr(manager, "history_records")
                                                       else [*history, *([current] if current else [])])})
            if removed:
                for item in removed:
                    self.items.remove(item)
                    self.managers.pop(item["id"], None)
                self._save()
            return out

    def mutate(self, body):
        with self.lock:
            action = body.get("action")
            item: dict[str, Any] | None
            if action == "add":
                used = {p["number"] for p in self.items}
                number = next(n for n in range(1, len(used) + 2) if n not in used)
                name = body.get("name", f"Pipeline {number}")
                if not isinstance(name, str) or not name.strip() or len(name) > 80:
                    raise ValueError("Pipeline name must contain 1–80 characters")
                # Creating a pipeline is not cloning the selected pipeline's model
                # assignment. Resolve current server defaults even for older clients
                # that submit a previously selected run's frozen profiles.
                configuration = copy.deepcopy(body.get("configuration", {}))
                if not isinstance(configuration, dict):
                    raise ValueError("Invalid pipeline configuration fields")
                from memstara.control.catalog import validate_new_design
                validate_new_design(configuration)
                configuration.update(provider="", model="", stage_models={})
                item = {
                    "id": uuid.uuid4().hex,
                    "agent_labels": dict(AGENT_LABELS),
                    "number": number,
                    "name": name.strip(),
                    "configuration": self.configuration(configuration),
                }
                self.items.append(item)
            else:
                item = next((p for p in self.items if p["id"] == body.get("id")), None)
                if item is None:
                    raise ValueError("Pipeline does not exist")
                if action == "remove":
                    if item.get("deleting"):
                        return {**copy.deepcopy(item), "deleting": True}
                    manager = self.manager(item["id"])
                    current = manager.running()
                    if current:
                        # A delete click is an explicit request to discard this
                        # execution's ability to resume. Signal termination and
                        # keep its owner record until the child has actually exited.
                        if hasattr(manager, "terminate"):
                            manager.terminate(current["run_tag"])
                        else:  # Small test doubles and legacy controllers.
                            manager.stop(current["run_tag"])
                        item["deleting"] = True
                        self._save()
                        return {**copy.deepcopy(item), "deleting": True,
                                "run_tag": current.get("run_tag")}
                    self.items.remove(item)
                    self.managers.pop(item["id"], None)
                    self._save()
                    return copy.deepcopy(item)
                name_only = action == "update" and "name" in body and set(body) <= {"action", "id", "name"}
                if item.get("deleting"):
                    raise ValueError("This pipeline is being deleted")
                if self.manager(item["id"]).running() and not name_only:
                    raise ValueError("Stop this pipeline before changing its configuration or removing it")
                if action == "update":
                    if isinstance(body.get('configuration'), dict):
                        from memstara.control.catalog import validate_new_design
                        validate_new_design(body['configuration'])
                    if "name" in body:
                        name = body["name"]
                        if not isinstance(name, str) or not name.strip() or len(name) > 80:
                            raise ValueError("Pipeline name must contain 1–80 characters")
                        item["name"] = name.strip()
                    if "configuration" in body:
                        item["configuration"] = self.configuration(body["configuration"])
                else:
                    raise ValueError("Unknown pipeline action")
            self._save()
            return copy.deepcopy(item)

    @classmethod
    def read_configuration(cls, value):
        """Keep unavailable saved skills editable; validate strictly when starting."""
        try:
            return cls.configuration(value), None
        except (ValueError, TypeError, KeyError) as error:
            return copy.deepcopy(value), str(error)

    @staticmethod
    def configuration(value):
        value = normalize_agent_configuration(value)
        from memstara.corpus_skills import with_default_hypothesis
        value = with_default_hypothesis(value)
        if not isinstance(value, dict) or set(value) - set(DEFAULTS):
            raise ValueError("Invalid pipeline configuration fields")
        config = {
            **copy.deepcopy(DEFAULTS),
            "playbook_interpreter": "interpreter_factual_observations",
            "playbook_explanation": "report_clinical_explanations",
            **value,
            "hypothesis_agents": 1,
            "interpret_agents": 1,
            "trials": 1,
            "waves": value.get("waves", 10),
            "continuous": value.get("continuous", False),
            "question": "",
        }
        if config.get('research_input_id'):
            from memstara.research_inputs import load
            research = load(config['research_input_id'])['configuration']
            config.update(knowledge_mode=research['knowledge_mode'], data_mode=research['data_mode'],
                          research_objective=research['target']['description'],
                          y_column=research['target']['column'] or 'outcome')
        if (config.get('knowledge_mode') not in ('okf', 'llm_only')
                or config.get('data_mode') not in ('dataset', 'proposal')):
            raise ValueError('Select supported knowledge and data modes')
        if config.get('data_mode') == 'proposal' and not str(config.get('research_objective', '')).strip():
            raise ValueError('Proposal mode requires a research objective')
        from memstara.stage_models import validate_profiles
        # Design persistence validates supplied identities but does not require a live deployment.
        if config.get('stage_models') != {}:
            config['stage_models'] = validate_profiles(config['stage_models'])
        from memstara.control.request import _MAX_WAVES
        if config.get('combination_skills'):
            from memstara.combinations import build_plan
            plan = build_plan(config['combination_skills'], config['combination_repetitions'],
                              random_start=config['combination_random_start'],
                              max_loops=config['combination_max_loops'], start_index=0)
            if plan['total_loops'] > 10000:
                raise ValueError('At most 10000 total replicates are supported')
            config['waves'] = plan['total_loops']
            config['continuous'] = False
            for stage, entries in plan['skills'].items():
                config[playbook_field(stage)] = entries[0]['id']
        maximum = 10000 if config.get('combination_skills') else _MAX_WAVES
        if type(config['waves']) is not int or not 1 <= config['waves'] <= maximum:
            raise ValueError(f'Total replicates must be between 1 and {maximum}')
        if type(config['continuous']) is not bool:
            raise ValueError('Continuous must be a boolean')
        # Older workspace definitions used continuous=True with a dummy waves=1.
        # Migrate these to the explicit MVP ceiling before display or launch.
        if config['continuous']:
            config['waves'] = 10
        config['continuous'] = False
        for key in ("playbook_hypothesis", "playbook_interpreter"):
            if not isinstance(config[key], str) or "," in config[key]:
                raise ValueError("Each pipeline has one hypothesis and one interpreter skill")
        from memstara.ml_configuration import validate_overrides
        ml_skills = (config.get('combination_skills', {}).get('ml', []) if config.get('combination_skills')
                     else str(config.get('playbook_ml', '')).split(','))
        if not isinstance(config.get('evaluation'), dict):
            raise ValueError('ML evaluation settings must be an object')
        config['ml_overrides'] = validate_overrides(
            config.get('ml_overrides', {}), ml_skills, replicates=config.get('evaluation', {}).get('replicates', 1))
        if config['ml_overrides'] and config.get('controlled_comparison'):
            raise ValueError('Controlled comparisons cannot also use advanced ML overrides')
        return config

    def start(self, key, launch, *, mode="initial", additional_loops=None, expected_run_tag=None):
        with self.lock:
            item = next((p for p in self.items if p["id"] == key), None)
            if item is None:
                raise ValueError("Pipeline does not exist")
            if item.get("deleting"):
                raise ValueError("This pipeline is being deleted and cannot start another execution")
            manager = self.manager(key)
            if manager.running():
                raise ValueError("This pipeline is already running; pause or resume its current execution")
            history = manager.finished()
            latest = history[0] if history else None
            if mode not in ("initial", "additional", "fresh", "retry"):
                raise ValueError("Invalid execution mode")
            if latest and mode == "initial":
                raise ValueError("Choose additional analysis and a total replicate count, "
                                 "or explicitly start a new execution")
            if mode in ("additional", "fresh", "retry"):
                if not latest or expected_run_tag != latest.get("run_tag"):
                    raise ValueError("Execution history changed. Refresh and review before starting")
            configuration = self.configuration(item["configuration"])
            if mode == "additional" and configuration.get("combination_skills"):
                raise ValueError("All Combinations restarts the full reviewed schedule; use a new execution")
            if mode == "additional":
                from memstara.control.request import _MAX_WAVES
                if type(additional_loops) is not int or not 1 <= additional_loops <= _MAX_WAVES:
                    raise ValueError(f"Additional total replicates must be between 1 and {_MAX_WAVES}")
                configuration.update(waves=additional_loops, continuous=False)
            elif additional_loops is not None:
                raise ValueError("Additional replicates require additional analysis mode")
            if mode == "retry":
                from memstara.control.retry import configuration_for_retry
                configuration = configuration_for_retry(latest, configuration, key)
            return launch(manager, {**copy.deepcopy(item), "configuration": configuration})

    def stop_all(self):
        """Freeze workspace membership and signal each live pipeline independently."""
        with self.lock:
            stopped, errors = [], []
            for item in self.items:
                manager = self.manager(item['id'])
                run = manager.running()
                if not run:
                    continue
                try:
                    manager.stop(run['run_tag'])
                    stopped.append(run['run_tag'])
                except (RuntimeError, OSError) as exc:
                    errors.append({'pipeline': item['name'], 'error': str(exc)})
            return {'stopping': stopped, 'errors': errors}

    def locate_manager(self, tag):
        with self.lock:
            for item in self.items:
                manager = self.manager(item["id"])
                current = manager.running()
                if (current and current["run_tag"] == tag) or any(r["run_tag"] == tag for r in manager.finished()):
                    return manager
        return None
