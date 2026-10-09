"""Server-owned target binding for new primary questions; no model-based validation."""
import re
from typing import NotRequired
from typing_extensions import TypedDict


class QuestionProposal(TypedDict):
    predictor_concepts: list[str]
    okf_tags: list[str]
    rationale: str
    source_ids: NotRequired[list[str]]
    target: NotRequired[str]
    text: NotRequired[str]
    parent_task_ids: NotRequired[list[int]]
    learning_goal: NotRequired[str]


class FeatureMapping(TypedDict):
    concept: str
    column: str
    source_id: str
    rationale: str

VERSION = "fixed_target_v1"

# These are graph edge types, not measurable clinical phenomena. Do not reject
# arbitrary uppercase acronyms: CD4 and MCV are legitimate clinical concepts.
RELATION_TYPES = {"ISA", "SYMPTOMMANIFESTATIONOFDISEASE", "TREATS", "CAUSES",
                  "ASSOCIATEDWITH", "INTERACTSWITH", "CONTRAINDICATEDWITH"}


def enabled(plan):
    return (plan or {}).get("hypothesis_policy", {}).get("question_contract") == VERSION


def knowledge_text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be non-empty text of at most {limit} characters")
    value = " ".join(value.split())
    # Metric names alone are not experimental evidence: a prospective falsification
    # criterion may legitimately mention AUC or SHAP. Match explicit feedback cues
    # instead. This remains a lexical guard, not a proof of scientific provenance;
    # source IDs and run-local parent-task lineage are validated separately.
    metric = r"(?:AUC|AUROC|SHAP|feature importances?|permutation importance)"
    signal = re.search(
        r"\b(?:previous trials?|prior trials?|previous experiments?|prior experiments?|"
        r"successful features?|negative.importance|positive.importance)\b"
        rf"|\b(?:observed|measured|achieved|obtained)\s+(?:an?\s+)?{metric}\b"
        rf"|\b{metric}\s+(?:was|were|showed|confirmed|demonstrated)\b",
        value, re.I,
    )
    if signal:
        raise ValueError(
            f"{label} contains experimental feedback ({signal.group(0)!r}); "
            "primary questions require knowledge-only evidence. Describe the knowledge-based "
            "mechanism and prospective evaluation; do not use observed run results without lineage."
        )
    return value


def make_contract(item, plan):
    from memstara.pipeline.feature_selection import context, scoped
    selection = context(plan, item.get("origin_wave"))
    random_selection = selection is not None and selection["mode"] == "random"
    if selection:
        plan = scoped(plan, item["origin_wave"])
    target = plan.get("y_column")
    if not isinstance(target, str) or not target or item.get("target", target) != target:
        raise ValueError("Question target must exactly match the fixed run target")
    concepts = item.get("predictor_concepts")
    if not isinstance(concepts, list) or not 1 <= len(concepts) <= 40:
        raise ValueError("Supply 1–40 predictor_concepts grounded in the knowledge source")
    if random_selection:
        if concepts != selection["required_features"]:
            raise ValueError("Random question must use the exact server-sampled predictors")
    else:
        concepts = [knowledge_text(c, "predictor concept", 160) for c in concepts]
    if len(set(c.casefold() for c in concepts)) != len(concepts):
        raise ValueError("Predictor concepts must be distinct")
    for concept in ([] if random_selection else concepts):
        if re.sub(r"[^A-Z0-9]", "", concept.upper().split("(")[0]) in RELATION_TYPES:
            raise ValueError("A graph relation is not a predictor concept. Read the document's "
                             "Instances section and use concrete clinical entities or measurements.")
        if target.casefold() in concept.casefold() or re.search(
            r"[?\n]|\b(predict\w*|target|outcome)\b", concept, re.I
        ):
            raise ValueError("Predictor concepts must name phenomena, not prediction targets or instructions")
    from memstara.pipeline.iteration_learning import enabled as learning_enabled, read_feedback
    lineage = {}
    if learning_enabled(plan):
        wave = item.get("origin_wave")
        if type(wave) is not int or wave < 0:
            raise ValueError("A nonnegative origin_wave is required")
        context = read_feedback(plan, wave)
        allowed = {entry['task_id'] for entry in context['evidence']}
        parents = item.get('parent_task_ids', [])
        if not isinstance(parents, list) or any(type(p) is not int for p in parents):
            raise ValueError('parent_task_ids must be integer task identifiers')
        if len(set(parents)) != len(parents) or set(parents) - allowed:
            raise ValueError('Parents must reference distinct prior tasks from this run feedback. ' +
                             f'Allowed parent_task_ids: {sorted(allowed)}. Use task_id, not question_id; '
                             'cite only tasks whose observations support the learning_goal.')
        if allowed and not parents:
            raise ValueError('Follow-up questions must cite at least one prior task. ' +
                             f'Allowed parent_task_ids: {sorted(allowed)}. Do not omit lineage or use question_id.')
        goal = item.get('learning_goal', '')
        if parents and (not isinstance(goal, str) or not goal.strip() or len(goal) > 2000):
            raise ValueError('Explain the follow-up experiment in learning_goal (1–2000 characters)')
        lineage = {'origin_wave': wave, 'parent_task_ids': parents,
                   'kind': 'evidence_informed_refinement' if parents else 'primary_knowledge_driven',
                   'learning_goal': goal if parents else ''}
    if lineage.get('parent_task_ids'):
        rationale = item.get('rationale')
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
            raise ValueError('rationale must contain 1–4000 characters')
        rationale = ' '.join(rationale.split())
    else:
        rationale = knowledge_text(item.get("rationale"), "rationale")
    from memstara.pipeline.ablation import enabled as ablation_enabled
    ablated = ablation_enabled(plan)
    sources = item.get("source_ids")
    if ablated:
        if sources not in (None, []) or item.get('okf_tags') not in (None, []):
            raise ValueError('OKF ablation must not claim source documents or corpus tags')
        sources = []
    elif plan.get("recovery_policy") or sources is not None:
        if (not isinstance(sources, list) or not sources
                or any(not isinstance(s, str) or not s.strip() for s in sources)):
            raise ValueError("source_ids must list the exact document IDs returned by okf_read")
        if len(sources) > 40 or len(set(sources)) != len(sources):
            raise ValueError("Supply at most 40 distinct source document IDs")
        inventory = plan.get("knowledge_hashes", {})
        if inventory and any(s.removesuffix(".md") + ".md" not in inventory for s in sources):
            raise ValueError("Source document is not in the frozen knowledge bundle")
    if selection:
        lineage["origin_wave"] = item["origin_wave"]
        if random_selection:
            lineage["kind"] = "random_feature_control"
    contract = {"version": VERSION, "target": target, "predictor_concepts": concepts,
                "rationale": rationale, **lineage,
                **({"evidence_mode": "no_okf"} if ablated else {}),
                **({"source_ids": sources} if sources is not None else {})}
    if item.get("text") not in (None, "", question_text(contract)):
        raise ValueError("Omit free-text questions; the server binds the predictor concepts to the fixed target")
    return contract


def question_text(contract):
    text = f"Do {'; '.join(contract['predictor_concepts'])} predict {contract['target']}?"
    if contract.get("kind") == "random_feature_control":
        text += f" (Random control, Loop {contract['origin_wave'] + 1})"
    return text


def hypothesis_text(contract):
    return f"{' ; '.join(contract['predictor_concepts'])} jointly predict {contract['target']}."


def validate_saved(contract, text, plan):
    if not isinstance(contract, dict) or contract.get("version") != VERSION:
        raise ValueError("Question has no verified fixed-target contract; generate a new question")
    rebuilt = make_contract({**contract, "text": text}, plan)
    if rebuilt != contract:
        raise ValueError("Question contract is inconsistent")
    return contract


def generation_instructions(plan):
    if not enabled(plan):
        return ""
    from memstara.pipeline.iteration_learning import enabled as learning_enabled
    rationale = ('a rationale citing knowledge and supplied prior evidence' if learning_enabled(plan)
                 else 'a knowledge-only rationale')
    return (f" The ONLY prediction target is {plan['y_column']!r}; this is an outcome, never an input feature. "
            "Knowledge graph endpoints are candidate predictor concepts, not alternative outcomes. "
            "For propose_questions supply predictor_concepts "
            "(a list of phenotype/measurement names), source_ids (exact document IDs read with okf_read), "
            f"okf_tags, and {rationale}. "
            "Omit target and text: the server binds them to the fixed run target. "
            "Read the source's actual section headings and concrete Instances; relation names such as "
            "SYMPTOMMANIFESTATIONOFDISEASE or ISA are not clinical predictors. Do not put prediction "
            "instructions in predictor_concepts. If the knowledge cannot support this target, propose no questions.")


def validate_mapping(mapping, contract, columns, source_ids):
    """Check coverage and lineage, not the biomedical truth of an agent's judgment."""
    if not isinstance(mapping, list) or not mapping:
        raise ValueError("feature_mapping is required: concept, column, source_id, rationale for every predictor")
    concepts = set(contract["predictor_concepts"])
    seen_concepts, seen_columns = set(), set()
    for row in mapping:
        if not isinstance(row, dict):
            raise ValueError("Each feature_mapping entry must be an object")
        if row.get("concept") not in concepts or row.get("column") not in columns:
            raise ValueError("Feature mapping must reference the assigned concepts and selected columns exactly")
        if (row.get("source_id") != "" if contract.get("evidence_mode") == "no_okf"
                else row.get("source_id") not in source_ids):
            raise ValueError("Feature mapping must cite a selected knowledge source ID")
        rationale = row.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 2000:
            raise ValueError("Each mapping needs a clinical rationale of 1–2000 characters")
        seen_concepts.add(row["concept"])
        seen_columns.add(row["column"])
    if seen_concepts != concepts or seen_columns != set(columns):
        raise ValueError("Map every assigned concept and selected column; "
                         "do not silently substitute an unrelated model")
    return mapping


def predictor_column_error(columns, plan):
    """Reject invented labels before creating downstream work; never auto-substitute."""
    context = (plan or {}).get("feature_context")
    if not context:
        return None
    allowed = {entry["column"] for entry in context["features"]
               if entry["column"] != plan.get("y_column")}
    unknown = sorted(set(columns) - allowed)
    if not unknown:
        return None
    suggestions = {}
    for column in unknown:
        parts = column.split("__")
        if len(parts) >= 3 and parts[0] == "DX":
            prefix = "__".join(parts[:2]) + "__"
            suggestions[column] = sorted(c for c in allowed if c.startswith(prefix))
    return {"error": "Unknown predictor column names. Copy exact names from match_concepts or "
                     "describe_dataset; do not rewrite their labels. Correct columns AND feature_mapping "
                     "and resubmit create_task. No task was created.",
            "code": "unknown_predictor_columns", "unknown_columns": unknown,
            "same_code_columns": suggestions}
