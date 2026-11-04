"""Visibility settings preserve saved studies and skip optional demo startup."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memstara.research_visibility import selection_policy, visible_records
from memstara import startup_research


class ResearchVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hidden = "a" * 32
        self.hiv = "b" * 32

    def configure(self):
        (self.root / "app-selection.json").write_text(json.dumps({
            "register_bundled_demo": False, "hidden_research_ids": [self.hidden]
        }))

    def test_default_keeps_existing_behavior(self):
        self.assertTrue(selection_policy(self.root)["register_bundled_demo"])
        records = [{"id": self.hidden}, {"id": self.hiv}]
        self.assertEqual(visible_records(records, self.root), records)

    def test_hidden_study_preserved(self):
        self.configure()
        records = [{"id": self.hidden}, {"id": self.hiv}]
        self.assertEqual(visible_records(records, self.root), [{"id": self.hiv}])
        self.assertEqual(len(records), 2)

    def test_disabling_demo_still_registers_user_study_repeatably(self):
        self.configure()
        folder = self.root / "hiv"
        folder.mkdir()
        (folder / "research.json").write_text("{}")
        with patch.object(startup_research, "prepare") as prepare:
            with patch.object(startup_research, "register_file", return_value=self.hiv) as register:
                kwargs = dict(root=self.root / "no-examples", inputs=self.root,
                              destination=self.root / "output")
                first = startup_research.bootstrap(**kwargs)
                second = startup_research.bootstrap(**kwargs)
                self.assertEqual(first, second)
                self.assertIsNone(first["bundled"])
                self.assertEqual(first["user_inputs"][0]["id"], self.hiv)
                self.assertFalse(first["execution_started"])
                self.assertEqual(register.call_count, 2)
                prepare.assert_not_called()

    def restrict(self):
        self.configure()
        policy = json.loads((self.root / "app-selection.json").read_text())
        policy["allowed_sources"] = {
            "dataset_path": str(self.root / "hiv.csv"),
            "knowledge_path": str(self.root / "hiv-okf"),
        }
        (self.root / "app-selection.json").write_text(json.dumps(policy))
        return policy

    def test_sources_and_symlinks(self):
        from memstara.research_visibility import require_source_access
        policy = self.restrict()
        require_source_access(policy["allowed_sources"], self.root)
        with self.assertRaisesRegex(ValueError, "not permitted"):
            require_source_access({**policy["allowed_sources"],
                                   "dataset_path": str(self.root / "heart-failure.csv")}, self.root)
        link = self.root / "alias.csv"
        link.symlink_to(self.root / "heart-failure.csv")
        with self.assertRaisesRegex(ValueError, "not permitted"):
            require_source_access({**policy["allowed_sources"], "dataset_path": str(link)}, self.root)

    def test_new_hiv_ids_allowed_but_heart_failure_load_and_resume_blocked(self):
        from memstara import research_inputs
        policy = self.restrict()
        registry = self.root / "registry"
        registry.mkdir()
        configuration = {"name": "HIV", **policy["allowed_sources"],
                         "target": {"column": "outcome", "positive_label": "1", "negative_label": "0"}}
        for identifier in (self.hiv, "c" * 32):
            (registry / (identifier + ".json")).write_text(json.dumps({
                "id": identifier, "fingerprint": "d" * 64, "configuration": configuration
            }))
        blocked = {**configuration, "dataset_path": str(self.root / "heart-failure.csv")}
        (registry / (self.hidden + ".json")).write_text(json.dumps({
            "id": self.hidden, "fingerprint": "e" * 64, "configuration": blocked
        }))
        with patch.dict("os.environ", {"MEMSTARA_INPUTS_DIR": str(self.root),
                                      "MEMSTARA_RESEARCH_INPUTS_DIR": str(registry)}):
            for identifier in (self.hiv, "c" * 32):
                self.assertEqual(research_inputs.load(identifier)["id"], identifier)
            with self.assertRaisesRegex(ValueError, "not permitted"):
                research_inputs.load(self.hidden)
            with self.assertRaisesRegex(ValueError, "not permitted"):
                research_inputs.verify_materialized({"id": self.hidden, "configuration": blocked})
            with self.assertRaisesRegex(ValueError, "not permitted"):
                research_inputs.inspect(blocked)

    def test_no_knowledge_mode_keeps_hiv_dataset_restriction(self):
        from memstara import research_inputs
        from memstara.research_visibility import require_source_access
        policy = self.restrict()
        config = research_inputs.config({
            "name": "HIV no knowledge", **policy["allowed_sources"],
            "knowledge_mode": "llm_only",
        })
        require_source_access(config, self.root)
        with self.assertRaisesRegex(ValueError, "not permitted"):
            require_source_access({**config, "dataset_path": str(self.root / "heart-failure.csv")}, self.root)

    def test_invalid_policy_is_rejected(self):
        (self.root / "app-selection.json").write_text('{"register_bundled_demo":"false"}')
        with self.assertRaises(ValueError):
            selection_policy(self.root)


if __name__ == "__main__":
    unittest.main()
