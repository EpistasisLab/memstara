"""Raw feedback tools remain unavailable; iterative evidence is frozen and supplied by the driver."""

PRIMARY_QUESTION_TOOLS = frozenset({
    "okf_list_domains", "okf_search", "okf_read", "read_question_catalog", "propose_questions",
})
PRIMARY_MAPPING_TOOLS = frozenset({
    "okf_list_domains", "okf_search", "okf_read", "describe_dataset",
    "match_concepts", "match_concept", "claim_question", "create_task",
})


def check_primary_tools(stage, tools):
    """Fail before a model call if feedback-capable tools enter a primary turn."""
    allowed = (PRIMARY_QUESTION_TOOLS if stage.startswith("question") else
               PRIMARY_MAPPING_TOOLS if stage.startswith("hypothesis") else None)
    if allowed is None:
        return
    names = {tool.get("tool_name") or tool.get("name") for tool in tools}
    if names - allowed:
        raise ValueError(f"Primary hypothesis tool boundary violated: {sorted(str(n) for n in names - allowed)}")
