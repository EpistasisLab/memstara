"""Per-condition isolation for the HIV model-knowledge control."""

VERSION = "isolated_no_knowledge_v1"
SKILL = "hiv-no-knowledge"


def selected(plan, wave):
    if not plan:
        return False
    if plan.get("no_knowledge_condition"):
        return True
    if plan.get("combination_plan"):
        from memstara.combinations import loop_flavors

        books = [
            a["id"] for a in loop_flavors(plan["combination_plan"], wave + 1)["agents"] if a["stage"] == "hypothesis"
        ]
    else:
        books = plan.get("books", {}).get("hypothesis", [])
    if SKILL in books and books != [SKILL]:
        raise ValueError("Run no-knowledge and OKF hypotheses in separate scheduled conditions")
    return books == [SKILL]


def scope(plan, wave):
    if not selected(plan, wave):
        return plan
    if plan.get("no_knowledge_isolation") != VERSION:
        raise ValueError(
            "This historical no-knowledge execution was not isolated. Start a new execution; "
            "existing results cannot be relabeled as an OKF-free control."
        )
    profile = plan.get("research_profile") or {}
    configuration = profile.get("configuration", {})
    return {
        **plan,
        "no_knowledge_condition": True,
        "knowledge_policy": {"mode": "no_okf", "retrieval_enabled": False},
        "knowledge_mode": "llm_only",
        "knowledge_hashes": {},
        "knowledge_path": "",
        "experiment_policy": {"version": "independent_replicates_v1", "prior_outcome_feedback": False},
        "research_profile": {"configuration": {**configuration, "knowledge_mode": "llm_only", "knowledge_path": ""}}
        if profile
        else None,
    }


def tools_for_condition(tools):
    # No arbitrary reference reader, prior-question catalog, memory, documents,
    # semantic retrieval, web, or raw data access. The controller claims the exact
    # assigned question; the agent receives its verified contract inline.
    allowed = {"lookup_predictor_catalog", "propose_questions", "create_task"}
    result = []
    for tool in tools:
        name = tool.get("tool_name") or tool.get("name")
        if name not in allowed:
            continue
        item = dict(tool)
        if name == "propose_questions":
            item["description"] = (
                "Save a model-knowledge question for this run and wave. Use predictor_concepts, "
                "rationale and proposed_mapping with exact CSV columns. Set source_ids=[] and okf_tags=[], "
                'and source_id="" in every mapping. No retrieved evidence or prior-outcome lineage is permitted.'
            )
        elif name == "create_task":
            item["description"] = (
                "Save the assigned, controller-claimed question as a task. Preserve its exact "
                "question_id, trial, perspective and hypothesis. Supply validated CSV columns and feature_mapping. "
                'Use okf_concept_ids=[], path_uses=[], and source_id="". Never claim retrieved evidence.'
            )
        result.append(item)
    return result
