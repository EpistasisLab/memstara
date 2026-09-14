"""Persist up to three independently configured pipeline definitions."""

import copy
import json
import threading
import uuid
from pathlib import Path

from memstara.control.request import DEFAULTS


class PipelineWorkspace:
    def __init__(self, path: Path, manager_factory):
        self.path = path
        self.lock = threading.RLock()
        self.factory = manager_factory
        self.managers = {}
        if path.exists():
            data = json.loads(path.read_text())
            if not isinstance(data, list) or len(data) > 3:
                raise ValueError("Invalid pipeline workspace; preserve the file and repair it")
            self.items = data
        else:
            self.items = []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.items, indent=2))
        temporary.replace(self.path)

    def manager(self, key):
        if not any(p["id"] == key for p in self.items):
            raise ValueError("Pipeline does not exist")
        if key not in self.managers:
            self.managers[key] = self.factory(key)
        return self.managers[key]

    def list(self):
        with self.lock:
            out = []
            for item in self.items:
                manager = self.manager(item["id"])
                current = manager.running()
                history = manager.finished()
                latest = current or (history[0] if history else None)
                progress = {}
                if latest:
                    try:
                        progress = json.loads((Path(latest["run_dir"]) / "progress.json").read_text())
                    except (OSError, ValueError):
                        pass
                out.append({**copy.deepcopy(item), "running": current, "latest": latest, "progress": progress})
            return out

    def mutate(self, body):
        with self.lock:
            action = body.get("action")
            if action == "add":
                if len(self.items) >= 3:
                    raise ValueError("At most three pipelines are supported")
                number = next(n for n in range(1, 4) if all(p["number"] != n for p in self.items))
                name = body.get("name", f"Pipeline {number}")
                if not isinstance(name, str) or not name.strip() or len(name) > 80:
                    raise ValueError("Pipeline name must contain 1–80 characters")
                item = {
                    "id": uuid.uuid4().hex,
                    "number": number,
                    "name": name.strip(),
                    "configuration": self.configuration(body.get("configuration", {})),
                }
                self.items.append(item)
            else:
                item = next((p for p in self.items if p["id"] == body.get("id")), None)
                if item is None:
                    raise ValueError("Pipeline does not exist")
                name_only = action == "update" and "name" in body and set(body) <= {"action", "id", "name"}
                if self.manager(item["id"]).running() and not name_only:
                    raise ValueError("Stop this pipeline before changing its configuration or removing it")
                if action == "remove":
                    self.items.remove(item)
                elif action == "update":
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

    @staticmethod
    def configuration(value):
        if not isinstance(value, dict) or set(value) - set(DEFAULTS):
            raise ValueError("Invalid pipeline configuration fields")
        config = {
            **copy.deepcopy(DEFAULTS),
            **value,
            "hypothesis_agents": 1,
            "interpret_agents": 1,
            "trials": 1,
            "waves": 1,
            "continuous": True,
            "question": "",
        }
        for key in ("playbook_hypothesis", "playbook_interpreter"):
            if not isinstance(config[key], str) or "," in config[key]:
                raise ValueError("Each pipeline has one hypothesis and one interpreter skill")
        return config

    def start(self, key, launch):
        with self.lock:
            item = next((p for p in self.items if p["id"] == key), None)
            if item is None:
                raise ValueError("Pipeline does not exist")
            return launch(self.manager(key), copy.deepcopy(item))

    def locate_manager(self, tag):
        with self.lock:
            for item in self.items:
                manager = self.manager(item["id"])
                current = manager.running()
                if current and current["run_tag"] == tag:
                    return manager
        return None
