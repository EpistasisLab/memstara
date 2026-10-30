# SOURCE: SANDBOX-ORIGINAL — explicit resolved-column exclusion policy for issue #5.
"""Study-approved exact-column rules; no inferred clinical exclusions.

This is the wide-table RuleSet adapter, not a copy of afc-forge's semantic or
ontology rule engine. Unsupported selectors fail validation instead of being ignored.
"""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExclusionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature: str
    reason: str

    @field_validator("feature", "reason")
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Values must be nonempty and have no surrounding whitespace")
        return value


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    target: str
    approved_by: str
    exclusions: tuple[ExclusionRule, ...] = Field(default_factory=tuple)

    @field_validator("target", "approved_by")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Target and approval attribution are required")
        return value

    def validate_columns(self, columns, target):
        if self.target != target:
            raise ValueError("Leakage policy target does not match configured target")
        names = [r.feature for r in self.exclusions]
        if len(names) != len(set(names)) or any(c not in columns for c in names):
            raise ValueError("Leakage policy has duplicate or unavailable exact columns")

    @property
    def excluded(self):
        return frozenset(r.feature for r in self.exclusions)

    @property
    def sha1(self):
        import json

        payload = self.model_dump()
        payload["exclusions"] = sorted(payload["exclusions"], key=lambda r: r["feature"])
        return hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_rules() -> RuleSet | None:
    value = os.environ.get("MEMSTARA_LEAKAGE_RULES_PATH", "").strip()
    from memstara.paths import output_dir

    path = Path(value).expanduser() if value else output_dir() / "matcher_rules.json"
    if not value and not path.exists():
        return None
    return RuleSet.model_validate_json(path.read_text(encoding="utf-8"))


EMPTY_RULES_SHA1 = hashlib.sha1(b"no-study-exclusions-v1").hexdigest()
