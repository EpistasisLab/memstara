"""Explicit question policy for independent combination evaluations.

Only newly frozen runs opt in. Historical iterative runs keep their contract.
Repeating a question in another Loop is permitted, not forced or evidence that
independently generated questions constitute a controlled comparison.
"""

VERSION = 'independent_combination_questions_v1'


def enabled(plan):
    return (plan or {}).get(
        'hypothesis_policy', {}).get('combination_questions') == VERSION


def instructions():
    return (
        '\nINDEPENDENT COMBINATION EVALUATION: Earlier Loops test other scheduled configurations. '
        'A supported question may be evaluated again in this Loop; a matching question in an '
        'earlier Loop is NOT a reason to declare the corpus exhausted. Duplicate exclusion '
        'applies within this Loop only. Do not select predictors from earlier ML performance. '
        'Read source documents and submit a supported question with propose_questions even '
        'when its predictors match a previous Loop. Do not claim every possible question has '
        'been exhausted based on a few search results. Never invent missing measurements or '
        'citations. If no supported question can be established, explain the specific limitation. '
        'Independent generations need not be identical; do not attribute their differences '
        'solely to downstream skill choices.\n'
    )


def skip_unavailable(plan, run_dir, wave, checkpoint, *, dry_streak, waves_run,
                     seeded_total, missing_trials):
    """Advance only a verified empty bank, never a provider/DB exception."""
    if not enabled(plan):
        return False
    import json
    for path in run_dir.glob(f"question_repair_{wave}_*.json"):
        feedback = json.loads(path.read_text())
        if feedback.get("run_tag") != plan.get("run_tag") or feedback.get("config_hash") != plan.get("config_hash"):
            raise ValueError("Question feedback belongs to another execution")
        response = feedback.get("response", {})
        if response.get("error") or any(r.get("code") == "mapping_preflight_unavailable"
                                        for r in response.get("rejected", [])):
            raise RuntimeError(
                "Question feasibility could not be verified; infrastructure failure is not a skipped question")
    from memstara.pipeline.exploration import record_round, write_progress
    record_round(run_dir, wave + 1, 'skipped',
                 'No supported executable question was saved after bounded recovery. '
                 'No analysis was performed; corpus exhaustion is not established.')
    write_progress(run_dir, wave + 1, 'hypothesis')
    checkpoint.advance(wave, dry_streak=dry_streak + 1, waves_run=waves_run,
                       seeded_total=seeded_total, missing_trials=missing_trials)
    return True
