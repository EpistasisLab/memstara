"""Provisional expert scopes over the existing corpus; no invented taxonomy filters."""

import hashlib
import json
from pathlib import Path

from memstara.expert_knowledge import KnowledgeError

TERMS = {
    "addiction": [
        "addiction",
        "substance",
        "sud",
        "alcohol",
        "opioid",
        "cocaine",
        "cannabis",
        "dependence",
        "withdrawal",
    ],
    "hiv": ["hiv", "aids", "antiretroviral", "viral", "cd4", "sexual"],
}


def freeze(expert):
    from memstara.mcp_servers.okf import _load, _bundle_root

    root = _bundle_root().resolve()
    docs, _ = _load(root)
    selected = []
    for doc in docs:
        if not doc.path.resolve().is_relative_to(root):
            raise KnowledgeError("Knowledge source escapes corpus root")
        tokens = set().union(*(doc.field_tokens.get(k, frozenset()) for k in ("title", "tags", "description")))
        matched = sorted(tokens & set(TERMS[expert]))
        if matched:
            selected.append(
                {
                    "id": doc.address,
                    "relative_path": doc.path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(doc.path.read_bytes()).hexdigest(),
                    "matched_terms": matched,
                }
            )
    if not selected:
        raise KnowledgeError(f"{expert}: no documents match the provisional OKF scope")
    corpus = hashlib.sha256(
        json.dumps(
            [(d.address, hashlib.sha256(d.path.read_bytes()).hexdigest()) for d in docs], sort_keys=True
        ).encode()
    ).hexdigest()
    return {
        "expert": expert,
        "database_id": "okf-" + expert,
        "kind": "okf",
        "path": str(root),
        "scope_policy": "metadata_keywords_v1_provisional",
        "terms": TERMS[expert],
        "overlap_policy": "documents may belong to both scopes",
        "documents": selected,
        "corpus_sha256": corpus,
        "confirmation_required": True,
    }


def validate(binding, expert):
    if (
        binding.get("expert") != expert
        or binding.get("scope_policy") != "metadata_keywords_v1_provisional"
        or not binding.get("documents")
        or not Path(binding.get("path", "")).is_dir()
    ):
        raise KnowledgeError("Invalid frozen OKF expert scope")
    root = Path(binding["path"]).resolve()
    for row in binding["documents"]:
        path = (root / row["relative_path"]).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise KnowledgeError("Frozen OKF scope changed or became unavailable")


async def probe(binding):
    validate(binding, binding["expert"])
    return {
        "status": "readable",
        "expert": binding["expert"],
        "database_id": binding["database_id"],
        "documents": len(binding["documents"]),
        "corpus_sha256": binding["corpus_sha256"],
        "scope_policy": binding["scope_policy"],
        "confirmation_required": True,
    }


async def retrieve(binding, text):
    from memstara.mcp_servers.okf import _parse_concept_file, _tokens

    validate(binding, binding["expert"])
    terms = _tokens(text)
    root = Path(binding["path"])
    ranked = []
    for row in binding["documents"]:
        fields, body = _parse_concept_file(root / row["relative_path"])
        searchable = " ".join(str(fields.get(k, "")) for k in ("title", "tags", "description"))
        score = len(terms & _tokens(searchable))
        if score:
            ranked.append((score, row, fields, body))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    if not ranked:
        raise KnowledgeError(f"{binding['expert']}: no query evidence in the frozen OKF scope")
    documents = []
    for score, row, fields, body in ranked[:10]:
        excerpt = (str(fields.get("title", "")) + "\n" + body)[:6000]
        documents.append(
            {
                "id": row["id"],
                "text": excerpt,
                "source_sha256": row["sha256"],
                "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "truncated": len(str(fields.get("title", "")) + "\n" + body) > 6000,
                "score": score,
            }
        )
    return {
        "database_id": binding["database_id"],
        "expert": binding["expert"],
        "query": {"text": text},
        "documents": documents,
        "version": {"corpus_sha256": binding["corpus_sha256"]},
        "scope_policy": binding["scope_policy"],
        "confirmation_required": True,
        "retrieval_policy": "Provisional metadata keyword scope; lexical query ranking; overlapping scopes allowed.",
    }
