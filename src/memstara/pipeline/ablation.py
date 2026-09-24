"""Explicit no-OKF experimental condition; does not erase pretrained model knowledge."""
INSTRUCTIONS = (
    'EXPERIMENT CONDITION: OKF retrieval is disabled for this execution. Do not call OKF tools, '
    'claim to have read a knowledge document, or invent citations. Use the available predictor '
    'schema and explicitly label hypotheses as no-OKF ablation proposals. Supply source_ids=[] '
    'and okf_tags=[] for questions; okf_concept_ids=[] for tasks; use source_id="" in each '
    'feature_mapping. Keep target binding, mapping coverage and prior-result lineage intact. '
    'This overrides instructions to retrieve KG/OKF sources in the regular workflow.'
)


def enabled(plan):
    return (plan or {}).get('knowledge_policy', {}).get('mode') == 'no_okf'


def filter_tools(tools, plan):
    if not enabled(plan):
        return tools
    return [t for t in tools if t.get('server') != 'okf' and not str(t.get('tool_name','')).startswith('okf_')]
