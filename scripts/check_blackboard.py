#!/usr/bin/env python3
"""Prove that two agents cannot take the same task.

This is the gate the design document put before everything else. If claiming is not
atomic, two data agents eventually work the same row, and every strange result after
that is ambiguous — was it the race, or the prompt? Settling it here means later
failures have one fewer explanation.

The tools are called as plain functions, not over MCP. The question is whether the
database statement is safe under concurrency; a server round trip would only add noise.

Usage::

    set -a && . ./.env && set +a          # in the core repo
    python scripts/check_blackboard.py

A check script that confirms the **board table** (blackboard) behaves. The board is a
database table where the work to be done is written down, and several agents take one
piece each from it. This file actually runs that taking and sees whether it is safe.

There are three functions.

    cleanup()               deletes rows carrying the test marker (run_tag). Called
                            twice, before and after
    ok(passed, label, ...)  prints one line for one check and returns its verdict
    main()                  the body of the check. It flows in the order below

What main() confirms, in order:

  (0) file questions into the question bank — one with no tag is refused, and the same
      one is filed only once. **A reword is blocked too** — while a neighbouring
      question on a different branch is let through
  (1) make 8 pieces of waiting work (carrying the question id filed in (0))
  (2) **THE GATE** — when 12 rush to claim at once, do any overlap
  (3) does a claimed piece carry what the previous stage left on it (outcome
      column · columns)
  (4) does claim → submit → hand on to the next stage keep flowing
  (5) is submitting without claiming blocked
  (6) does a finished piece pile up in the results table, and is what remains counted
      exactly
  (7) is the score fed back into the question bank, and does the bank survive the
      board being cleared
  (8) does a question used three times retire and drop out of the open list — while
      the record and the reword block stay
  (9) does a claimed row name its holder, and is another worker's result refused —
      including the stalled-worker overwrite, end to end
 (10) two named workers claiming **at the same time**, which is what the driver does
      now that --data-agents may be more than 1
 (11) the same one table over: two hypothesis workers claiming out of the question
      bank, and the driver handing back what the run held

Easy to miss:

  · **(2) is the reason this file exists.** If claiming is not atomic, two data agents
    eventually hold the same row, and every strange result after that has two
    explanations — was it the race, or the prompt? Settling it here means later
    failures have one fewer explanation.
  · The tools are called **as plain Python functions**, not across an MCP server. The
    question is whether the database statement is safe under concurrency, not whether
    the server round trip works, so putting a server in the way only adds noise.
  · This check **writes to the real database.** That is why cleanup() picks out only
    its own rows at the start and at the end.
  · **The question bank (memstara_questions), unlike the board, accumulates across
    runs.** So in that table too, cleanup() picks out only the rows whose origin_run —
    not run_tag — is its own. Clearing it wholesale would take with it the questions
    other runs have piled up.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter

from memstara.mcp_servers import blackboard as bb  # the board's tools — called directly, without a server

# The marker put only on rows this check made. It is what lets us pick out this
# check's rows and delete them without touching the real run records that live in
# the same table.
RUN_TAG = "test_atomicity"


async def cleanup() -> None:
    """Delete only the rows this check made. Called once at the start and once at the end.

    Why it also deletes at the start: if an earlier check died partway there is debris
    left behind, and then the item counting "8 waiting" would see a number that is not
    8. A check has to start from the same place whenever it is run.

    Only the question bank has a different condition. That table has no run_tag — it is
    a global table that accumulates across runs, and that was left out on purpose. So
    rows are picked out by "who filed it" (origin_run). Clearing it wholesale would
    take the questions other runs piled up along with it.
    """
    import asyncpg

    conn = await asyncpg.connect(bb._dsn())
    try:
        await conn.execute("DELETE FROM memstara_results WHERE run_tag = $1", RUN_TAG)
        await conn.execute("DELETE FROM memstara_blackboard WHERE run_tag = $1", RUN_TAG)
        # A claim is the one mark this check can leave on a row it does **not** own.
        # Item (11) claims a third question to show that a claimed one is not handed out
        # twice, and that third question belongs to whoever filed it. Releasing before
        # the delete repairs a run that died holding it; the delete below would not,
        # because origin_run is not this check's tag.
        await conn.execute(
            "UPDATE memstara_questions SET claimed_run = '', claimed_by = '', claimed_at = NULL "
            "WHERE claimed_run = $1", RUN_TAG)
        await conn.execute("DELETE FROM memstara_questions WHERE origin_run = $1", RUN_TAG)
    finally:
        await conn.close()


async def cleanup_tag(run_tag: str) -> None:
    """Do what `cleanup()` does, but for any tag.

    Seeing whether runs avoid claiming each other's work needs **two** tags. The second
    tag is not RUN_TAG, so the cleanup() above does not delete it.
    """
    import asyncpg

    conn = await asyncpg.connect(bb._dsn())
    try:
        await conn.execute("DELETE FROM memstara_results WHERE run_tag = $1", run_tag)
        await conn.execute("DELETE FROM memstara_blackboard WHERE run_tag = $1", run_tag)
    finally:
        await conn.close()


def ok(passed: bool, label: str, detail: str = "") -> bool:
    """Print one line for one check and return its verdict unchanged.

    main() piles the returned values into a list and produces "how many of how many
    passed" at the end. Printing and counting are bound into one function so that
    printing something and forgetting to count it cannot happen.
    """
    print(f"  {'OK  ' if passed else 'FAIL'} {label}" + (f"  — {detail}" if detail else ""))
    return passed


async def main() -> int:
    """The body of the check. Steps (0)-(11) from the header above are here, in order."""
    results: list[bool] = []   # each item's verdict, piled up
    await cleanup()            # clear an earlier check's debris first
    await cleanup_tag(f"{RUN_TAG}_other")   # and the second tag that (7) uses

    # ---- file into the question bank first ------------------------------
    #
    # This comes before the board. For a trial to exist there first has to be something
    # to ask. Until now the thing to ask was 20 items hard-coded into the source
    # (`memstara.pipeline.core.PERSPECTIVES`), so there was nowhere to go back and ask "why did
    # this trial exist".
    QTEXT = f"from a psychiatric-comorbidity perspective ({RUN_TAG})"
    QTAGS = ["psychiatric", "sud"]
    # Two are filed at once — one with a tag and one without. The one without has to be
    # refused.
    #
    # Why this is not a formality check: given a question the corpus cannot answer, the
    # hypothesis agent produces an answer anyway. That stage has no ending that means
    # "found no evidence". So it invents the evidence. Forcing a tag here is the place
    # that makes that **impossible**.
    p1 = json.loads(await bb.propose_questions(json.dumps([
        {"text": QTEXT, "okf_tags": QTAGS,
         "rationale": "the corpus's 333 documents cluster on this branch"},
        {"text": f"a question filed with no tag ({RUN_TAG})", "okf_tags": [], "rationale": ""},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=0))
    results.append(ok(len(p1.get("added", [])) == 1 and len(p1.get("rejected", [])) == 1,
                      "only a tagged question reaches the bank (an unevidenced one is refused)",
                      f"added {len(p1.get('added', []))} · refused {len(p1.get('rejected', []))}"))
    QID = p1["added"][0]["question_id"]

    # File the same question again with only its case and its surrounding whitespace
    # changed. A question that looks the same to a person has to be the same question to
    # the bank too — otherwise the next run cannot recognise what has already been asked
    # and goes on asking it. That looks like progress and is not.
    p2 = json.loads(await bb.propose_questions(json.dumps([
        {"text": "  " + QTEXT.upper() + "  ", "okf_tags": QTAGS},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=1))
    results.append(ok(not p2.get("added") and len(p2.get("duplicates", [])) == 1,
                      "a question already asked is not filed again (case and space ignored)",
                      f"added {len(p2.get('added', []))} · duplicate {len(p2.get('duplicates', []))}"))

    # ---- ⭐ THE GATE: is a reworded question recognised ------------------
    #
    # The check above catches **identical characters** only. But the way the curator
    # actually creates an overlap is not filing the same sentence twice — it is
    # **writing the same thing differently**. The trial then costs what it costs and
    # returns nothing.
    #
    # Three are thrown at once. Each has to hold a different line:
    #   (1) a reword                     → blocked. It even says which question it
    #                                      repeats (duplicate_of)
    #   (2) same tags, different content  → filed. Block the neighbour too and the bank
    #                                      stalls on one branch
    #   (3) similar sentence, different tags → filed. A different branch is a different
    #                                      question
    p3 = json.loads(await bb.propose_questions(json.dumps([
        {"text": f"from a comorbid psychiatric illness perspective ({RUN_TAG})",
         "okf_tags": QTAGS, "rationale": "a reword"},
        {"text": f"from a substance-use-disorder perspective ({RUN_TAG})",
         "okf_tags": QTAGS, "rationale": "a different question on the same branch"},
        {"text": f"from a psychiatric comorbidity perspective ({RUN_TAG})",
         "okf_tags": ["metapath"], "rationale": "similar sentence, different branch"},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=1))
    reword = (p3.get("skipped") or [{}])[0]
    results.append(ok(len(p3.get("skipped", [])) == 1
                      and reword.get("duplicate_of") == QID
                      and len(p3.get("added", [])) == 2,
                      "a reworded question is blocked, a neighbour and another branch get through",
                      f"blocked {len(p3.get('skipped', []))} (#{reword.get('duplicate_of')} "
                      f"similarity {reword.get('similarity')}) · added {len(p3.get('added', []))}"))

    # Does what was filed come back unchanged. If the tags and the rationale do not make
    # the round trip, the curator cannot see "on what evidence was this asked" in the
    # next wave, and the feedback loop breaks right there.
    bank = json.loads(await bb.read_questions(limit=200)).get("questions", [])
    mine = next((q for q in bank if q.get("question_id") == QID), None)
    results.append(ok(mine is not None
                      and mine.get("okf_tags") == QTAGS
                      and mine.get("rationale", "").startswith("the corpus")
                      and mine.get("times_used") == 0,
                      "the question bank returns the tags and the rationale unchanged",
                      f"tags {(mine or {}).get('okf_tags')} · times used {(mine or {}).get('times_used')}"))

    # ---- fill the board ----------------------------------------------
    #
    # The perspective and the hypothesis do not matter in content, so they are just
    # numbered. What is being confirmed is the board's behaviour, not the quality of a
    # hypothesis. The columns and the outcome column use real names — because further
    # down we confirm that those come back carried unchanged.
    N = 8
    # One of these two carries a comma INSIDE the name — 158 of the cohort's 1,393
    # columns do. It is here so the board's round trip is checked against the case
    # that used to break it, not only against names a split would survive.
    COLUMNS = ["CURRENT_AGE", "LAB__HDL CHOLESTEROL, DIRECT"]
    # The evidence for why these columns were chosen. Whether it survives to the end is
    # what the two items below ask.
    OKF_IDS = ["anchors/hiv", "mechanisms/comorbidity/mp010-comorbidity-psychiatric"]
    for i in range(N):
        r = json.loads(await bb.create_task(RUN_TAG, i, f"perspective {i}", f"hypothesis {i}",
                                            COLUMNS, "HIV_DETECTABLE",
                                            okf_concept_ids=OKF_IDS,
                                            question_id=QID))
        assert "task_id" in r, r
    results.append(ok(True, f"made {N} pieces of waiting work"))

    # ---- ⭐ THE GATE: claiming at once, do any overlap ------------------
    #
    # More claimers than tasks on purpose: the surplus must come back empty rather
    # than duplicate somebody else's row. 12 claimers for 8 pieces; the 4 left over have
    # to come back empty-handed rather than take one more of somebody else's row. Throw
    # exactly as many as there are and an overlap could hide in the arithmetic.
    #
    # asyncio.gather launches the 12 claims **at the same time**. Calling them one after
    # another means the race never happens and this check confirms nothing.
    #
    # Sending RUN_TAG along matters. Without it, the claim takes the oldest waiting row
    # on the **whole board**, and if another run was interrupted and left a task behind,
    # that one gets caught first. That really happened: while this line had no tag, the
    # ml-stage check below claimed a task left by a `dry-stop` run and wrote the check's
    # fake numbers into that run's results table.
    claims = await asyncio.gather(
        *[bb.claim_task("data", RUN_TAG) for _ in range(N + 4)])
    got = [json.loads(c) for c in claims]
    ids = [g["task_id"] for g in got if g.get("task_id") is not None]   # claimed
    empty = [g for g in got if g.get("task_id") is None]                # empty-handed
    dupes = [i for i, n in Counter(ids).items() if n > 1]               # claimed by two

    results.append(ok(not dupes, "no two claimed the same piece in a concurrent claim",
                      f"{len(ids)} claimed, {len(dupes)} duplicated"))
    results.append(ok(len(ids) == N, f"all {N} waiting were claimed exactly once each", f"{len(ids)}/{N}"))
    results.append(ok(len(empty) == 4, "the 4 thrown beyond the waiting count came back empty",
                      f"{len(empty)} with task_id=null"))

    # ---- does a claimed piece carry what the previous stage left --------
    first = next(g for g in got if g.get("task_id") is not None)   # any one of the claimed
    # The outcome column has to come back with the task, or a stage would have to be
    # told it separately and the board would not be the source of truth it claims to be.
    # The moment there are two sources of truth, one day the two disagree.
    results.append(ok(first.get("y_column") == "HIV_DETECTABLE",
                      "a claimed piece carries the outcome column", str(first.get("y_column"))))
    results.append(ok(first.get("columns") == COLUMNS,
                      "a claimed piece carries the columns the hypothesis chose (comma inside a name included)",
                      str(first.get("columns"))))

    # ---- does reading the board show the evidence ----------------------
    #
    # `read_board`'s SELECT once left out `okf_concept_ids`. It was being written
    # correctly, so it was there in the table and invisible only through the window —
    # which meant that however hard you stared at the board you could not tell "why
    # these columns". What is confirmed here is **that what went in comes back out**.
    board_now = json.loads(await bb.read_board(RUN_TAG))["tasks"][0]
    results.append(ok(board_now.get("okf_concept_ids") == OKF_IDS,
                      "reading the board shows the evidence documents", str(board_now.get("okf_concept_ids"))))

    # ---- the flow: claim → submit → on to the next type -----------------
    #
    # When the data stage submits its result, that row has to turn into "the ml stage's
    # turn" by itself and go back to waiting. There is nobody to tell the next stage
    # separately — the board has to hand it on itself for the flow to continue.
    tid = first["task_id"]

    # What the matcher looked at and what it chose. This is the slot the driver fills
    # from the trace, so here it is imitated by hand. It has to be attached **before the
    # task completes** — the moment it completes it is copied into the results table.
    TRACE = [{"tool": "match_concepts",
              "arguments": {"concepts": ["age"]},
              "result": {"results": [{"concept": "age", "candidates": [
                  {"feature_name": "CURRENT_AGE", "similarity_score": 0.93},
                  {"feature_name": "LAB__AGE_ADJ", "similarity_score": 0.91}]}]}}]
    at = json.loads(await bb.attach_match_trace(tid, json.dumps(TRACE)))
    results.append(ok(at.get("calls") == 1, "the matcher record is attached to the board", str(at.get("calls"))))

    r = json.loads(await bb.submit_result(tid, subset_path="outputs/sub_x.csv",
                                          columns_used=COLUMNS))
    results.append(ok(r.get("task_type") == "ml" and r.get("status") == "ready",
                      "the data stage submitted and the next turn moved to ml", f"{r.get('status')} · {r.get('task_type')}"))

    # is submitting without claiming blocked
    #
    # tid has just finished submitting, so it is not in progress. Trying to submit to it
    # again has to raise an error. If this is not blocked, one late-arriving response can
    # overwrite an already-finished row and the result changes silently.
    r2 = json.loads(await bb.submit_result(tid))
    results.append(ok("error" in r2, "a piece that was not claimed cannot be submitted to", r2.get("error", "")[:48]))

    # ml → interpret → done
    #
    # Walk the remaining two stages as they are. The values (auc 0.71 and so on) can be
    # any numbers. What is confirmed is whether the status becomes "done" when the last
    # stage finishes.
    c = json.loads(await bb.claim_task("ml", RUN_TAG))
    await bb.submit_result(c["task_id"], auc=0.71, feature_importance='{"CURRENT_AGE": 0.4}')
    c = json.loads(await bb.claim_task("interpret", RUN_TAG))
    r3 = json.loads(await bb.submit_result(c["task_id"], interpretation="supported"))
    results.append(ok(r3.get("status") == "done", "once interpretation finishes it becomes done", str(r3.get("status"))))

    # ---- did it pile up in the results table ---------------------------
    #
    # The board (memstara_blackboard) holds the progress, and what has finished has to
    # move to the results table (memstara_results). Here the database is asked directly —
    # confirming it through the tool could pass while the tool and the table are wrong
    # together.
    board = json.loads(await bb.read_board(RUN_TAG))
    import asyncpg

    conn = await asyncpg.connect(bb._dsn())
    try:
        n_res = await conn.fetchval("SELECT count(*) FROM memstara_results WHERE run_tag=$1", RUN_TAG)
    finally:
        await conn.close()
    results.append(ok(n_res == 1, "what finished piled up in the results table", f"{n_res} rows"))

    # ---- did the evidence make it across to the results table ----------
    #
    # The table that lasts is the results table. It used to receive nine fields, and all
    # nine were **conclusions** — hypothesis · columns used · AUC · interpretation. Why
    # those columns (okf_concept_ids · match_trace) and whether they were worth anything
    # (feature_importance) stayed on the table you are allowed to clear. So the record
    # that lasted was precisely **the part you could not check**.
    res = json.loads(await bb.read_results(RUN_TAG, include_match_trace=True))["results"][0]
    carried = (res.get("okf_concept_ids") == OKF_IDS
               and len(res.get("match_trace") or []) == 1
               and (res.get("feature_importance") or {}).get("CURRENT_AGE") == 0.4
               and res.get("columns") == COLUMNS)
    results.append(ok(carried, "the results table holds the evidence along with the conclusion",
                      f"evidence {len(res.get('okf_concept_ids') or [])} · "
                      f"candidate records {len(res.get('match_trace') or [])} · "
                      f"importances {len(res.get('feature_importance') or {})}"))

    # ---- did the result carry "what was asked" too ---------------------
    #
    # The results table used to hold **the answer only**. Which question it answered was
    # in the board's perspective field alone, and the board disappears when cleared. So
    # when a run ended the answer stayed and the question was gone — and the way to feed
    # the score back to the question disappears at that moment.
    results.append(ok(res.get("question_id") == QID,
                      "the results table keeps which question the answer came from",
                      f"question_id={res.get('question_id')} (expected {QID})"))

    # ---- feed the score back into the question bank --------------------
    #
    # What calls this is not an agent but the driving program. Only that side knows the
    # fact that a wave has ended. Without it the bank is only a list of "what was asked",
    # never a record of "what came of asking".
    fed = json.loads(await bb.record_question_outcomes(RUN_TAG))
    scored = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                   if q.get("question_id") == QID), {})
    # Calling it once more has to leave it in the same place. times_used is not
    # incremented but recounted from the results table — a retry or a duplicate call must
    # not inflate the count.
    await bb.record_question_outcomes(RUN_TAG)
    again = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                  if q.get("question_id") == QID), {})
    results.append(ok(fed.get("ok") is True
                      and scored.get("times_used") == 1
                      and scored.get("best_auc") == 0.71
                      and again.get("times_used") == 1,
                      "the score is fed back into the question bank (same when called twice)",
                      f"times used {scored.get('times_used')} · best AUC {scored.get('best_auc')}"))

    # ---- counting ------------------------------------------------------
    #
    # Only 1 of the 8 went all the way, and the other 7 are still sitting claimed. So
    # waiting 0 · in progress 7 (= N-1) is the right answer. If these numbers are off it
    # means a status changed twice somewhere.
    #
    # Counted narrowed to RUN_TAG. Given nothing, count_waiting counts the **whole
    # board**, and then tasks other runs left get mixed into this number — one ml task
    # left by `dry-stop` really did make in-progress read 8 and this item fail. What is
    # being counted is "what this check made", so narrowing is the right call.
    cnt = json.loads(await bb.count_waiting(run_tag=RUN_TAG))
    results.append(ok(cnt["ready"] == 0 and cnt["in_progress"] == N - 1,
                      "what is left is counted exactly", f"waiting {cnt['ready']} · in progress {cnt['in_progress']}"))
    results.append(ok(board["count"] == N, "the whole board is read", f"{board['count']}"))

    # ---- ⭐ THE GATE: does the evidence survive clearing the board ------
    #
    # This is the reason the tables were split in two, so this item is among the most
    # important in this file. The board is a workbench and can be cleared at any time
    # (`blackboard.py --drop`), and once cleared the only thing left is the results
    # table. Had the evidence been on the board alone, it would vanish at this point.
    #
    # Why it comes last — the board's rows are deleted here, so the counting items above
    # have to have finished first.
    conn = await asyncpg.connect(bb._dsn())
    try:
        await conn.execute("DELETE FROM memstara_blackboard WHERE run_tag=$1", RUN_TAG)
    finally:
        await conn.close()
    # Read with the defaults and the candidate record comes back as a count only — so the
    # reporting prompt does not swell.
    brief = json.loads(await bb.read_results(RUN_TAG))["results"][0]
    # Ask for it and the content comes too. What the gate has to prove is the content.
    after = json.loads(await bb.read_results(RUN_TAG, include_match_trace=True))["results"][0]
    survived = (after.get("task_id") is None            # the link is broken
                and after.get("okf_concept_ids") == OKF_IDS   # the content stays
                and "match_trace" not in brief and brief.get("match_trace_calls") == 1
                and len(after.get("match_trace") or []) == 1
                and (after.get("feature_importance") or {}).get("CURRENT_AGE") == 0.4)
    results.append(ok(survived, "the results table's evidence survives clearing the board",
                      f"task_id={after.get('task_id')} · "
                      f"evidence {len(after.get('okf_concept_ids') or [])} · "
                      f"candidate records {len(after.get('match_trace') or [])}"))

    # ---- ⭐ THE GATE: does the question bank survive clearing the board -
    #
    # This is the reason the question was pulled out into its own table instead of being
    # left in the board's perspective field. The board's rows were just deleted wholesale,
    # and even so the bank's question and the results table's question_id have to be alive
    # together. Lose either one and the next run has no way of knowing "this was already
    # asked and it gave AUC 0.71", so it asks the same question as if for the first time.
    #
    # That the bank holds no foreign key pointing at the board is also what this item
    # protects. Had there been one, the table meant to last would point at the table meant
    # to disappear first.
    bank_after = next((q for q in json.loads(await bb.read_questions(limit=200))["questions"]
                       if q.get("question_id") == QID), None)
    results.append(ok(bank_after is not None
                      and bank_after.get("times_used") == 1
                      and after.get("question_id") == QID,
                      "the question bank and its link survive clearing the board",
                      f"bank {'present' if bank_after else 'absent'} · "
                      f"results question_id={after.get('question_id')}"))

    # ---- ⭐ THE GATE: does a used-up question retire --------------------
    #
    # The `status` field and its two values ('open' | 'exhausted') were in the schema from
    # the day the bank was built, and until 2026-08-30 **not one line of code ever wrote
    # 'exhausted'.** So the open list only grew, and a question tried three times kept
    # coming back in front of the curator wearing the same face as one nobody had asked
    # yet.
    #
    # The board was deleted wholesale above, so two new ones are made here and walked to
    # the end. QID already has one result, so this makes three, and at that moment it has
    # to retire.
    for i in range(N, N + 2):
        await bb.create_task(RUN_TAG, i, f"perspective {i}", f"hypothesis {i}",
                             COLUMNS, "HIV_DETECTABLE",
                             okf_concept_ids=OKF_IDS, question_id=QID)
        c = json.loads(await bb.claim_task("data", RUN_TAG))
        await bb.submit_result(c["task_id"], subset_path="outputs/sub_x.csv",
                               columns_used=COLUMNS)
        c = json.loads(await bb.claim_task("ml", RUN_TAG))
        await bb.submit_result(c["task_id"], auc=0.5)
        c = json.loads(await bb.claim_task("interpret", RUN_TAG))
        await bb.submit_result(c["task_id"], interpretation="not supported")

    fed2 = json.loads(await bb.record_question_outcomes(RUN_TAG))
    open_now = json.loads(await bb.read_questions(status="open", limit=500))["questions"]
    retired_now = json.loads(await bb.read_questions(status="exhausted", limit=500))["questions"]
    gone = next((q for q in retired_now if q.get("question_id") == QID), None)
    results.append(ok(fed2.get("questions_retired", 0) >= 1
                      and not any(q.get("question_id") == QID for q in open_now)
                      and gone is not None
                      and gone.get("times_used") == 3
                      # Retiring is not deleting. The best score has to stay as it was.
                      and gone.get("best_auc") == 0.71,
                      "a question used three times retires out of the next wave's list (the record stays)",
                      f"retired {fed2.get('questions_retired')} · "
                      f"times used {(gone or {}).get('times_used')} · "
                      f"best AUC {(gone or {}).get('best_auc')}"))

    # Having retired it must not let a reword of it through either. Asking a used-up,
    # shelved question again in different words is exactly as wasteful as rewording an
    # open one.
    p4 = json.loads(await bb.propose_questions(json.dumps([
        {"text": f"from a comorbid psychiatric illness perspective ({RUN_TAG})",
         "okf_tags": QTAGS, "rationale": "a reword of a retired question"},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=2))
    results.append(ok(not p4.get("added") and len(p4.get("skipped", [])) == 1,
                      "a retired question blocks rewords too",
                      f"added {len(p4.get('added', []))} · blocked {len(p4.get('skipped', []))}"))

    # ---- (7) do runs avoid claiming each other's work --------------------
    #
    # `claim_task` did not look at run_tag for a long time. It took the oldest waiting row
    # on the whole board with `ORDER BY task_id`, so **a task left by a dead run was the
    # first thing the next run claimed**. That run's money does somebody else's work, and
    # the result is filed under the dead run's tag. run_lock() cannot stop this — it only
    # looks at the same tag.
    #
    # This is not imagined. On 2026-08-31, while the ml-stage check above had no tag, this
    # check claimed a task left by a `dry-stop` run and wrote the check's fake numbers
    # (auc 0.71, "supported") into that run's results table.
    #
    # Two tags are made and **the later one** is named when claiming. Without the
    # narrowing the older A would come out, so this check fails the moment the condition
    # goes missing.
    other_tag = f"{RUN_TAG}_other"
    await bb.create_task(other_tag, 90, "perspective A", "hypothesis A", COLUMNS, "HIV_DETECTABLE")
    await bb.create_task(RUN_TAG, 91, "perspective B", "hypothesis B", COLUMNS, "HIV_DETECTABLE")
    picked = json.loads(await bb.claim_task("data", RUN_TAG))
    results.append(ok(picked.get("run_tag") == RUN_TAG,
                      "given a run_tag it claims only its own run's work (even if another's is older)",
                      f"claimed row's tag {picked.get('run_tag')}"))

    # An empty string looks at the whole board as before. Existing callers must not break,
    # and the check has to hold on to that fact so it cannot change quietly later.
    #
    # This one line does touch the **whole board**, though, so if another run left a
    # waiting row it would claim it and turn it in_progress. That is the very accident
    # this check exists to fix. So look first, and if somebody else's is there, skip the
    # claim.
    board_all = json.loads(await bb.read_board())["tasks"]
    strays = [t for t in board_all
              if t["task_type"] == "data" and t["status"] == "ready"
              and t["run_tag"] not in (RUN_TAG, other_tag)]
    if strays:
        results.append(ok(True, "skipping the untagged-claim check — another run's waiting rows are on the board",
                          f"{len(strays)} ({strays[0]['run_tag']} and so on)"))
    else:
        picked2 = json.loads(await bb.claim_task("data"))
        results.append(ok(picked2.get("run_tag") == other_tag,
                          "given no tag it claims the oldest on the whole board, as before",
                          f"claimed row's tag {picked2.get('run_tag')}"))

    # ---- (8) can leftover tasks be reclaimed and closed -------------------
    #
    # The two rows above are in_progress right now. If the run dies here nobody clears
    # them — the driver's reclaim_stalled looks at its own tag only, and then only inside
    # the work loop. blackboard.py's three commands fill that gap.
    from memstara import blackboard as bbm

    # Note down first what state the other tag is in. That it is **unchanged** after
    # --reclaim is half of what this item checks.
    other_before = [t["status"] for t in json.loads(await bb.read_board(other_tag))["tasks"]]
    back = await bbm.reclaim(RUN_TAG)
    after = json.loads(await bb.read_board(RUN_TAG))["tasks"]
    mine_ready = [t for t in after if t["status"] == "ready" and t["trial"] == 91]
    other_after = [t["status"] for t in json.loads(await bb.read_board(other_tag))["tasks"]]
    results.append(ok(back == 1 and len(mine_ready) == 1 and other_after == other_before,
                      "--reclaim requeues that run only and does not touch another's tag",
                      f"reclaimed {back} · other tag {other_before} → {other_after}"))

    closed = await bbm.close_run(RUN_TAG)
    left = json.loads(await bb.read_board(RUN_TAG))["tasks"]
    failed = [t for t in left if t["status"] == "failed"]
    results.append(ok(closed >= 1 and len(failed) == closed,
                      "--close only closes as failed, it does not delete rows (why there is no result stays)",
                      f"closed {closed} · failed rows left {len(failed)}"))

    # ---- (9) ⭐ THE GATE: is the holder recorded, and does the record hold -
    #
    # The gate at the top proves two workers cannot **take** the same task. This one is
    # about what happens after: a worker that has already taken one and is slow.
    #
    # `submit_result` used to check the status and nothing else, and a status cannot tell
    # these two apart — "the task I am holding" and "the task that was taken away from me
    # and given to somebody else" are both `in_progress` when you look at them. So a
    # worker that overran `--stale-after`, had its row requeued and handed on, and then
    # finished, wrote its result straight over the top of whoever now held it. Nothing
    # errored and nothing looked wrong; the results table simply held the wrong run of
    # the wrong worker's work.
    #
    # This never happened, because there has only ever been one worker per stage. It is
    # the ordinary case with two, which is the whole point of adding a second.
    #
    # RUN_TAG's rows are all `failed` by now (--close, just above), so the task made here
    # is the only one this claims, and no earlier item is disturbed.
    await bb.create_task(RUN_TAG, 92, "perspective C", "hypothesis C", COLUMNS, "HIV_DETECTABLE")
    held = json.loads(await bb.claim_task("data", RUN_TAG, worker="data-1"))
    owned = held["task_id"]
    shown = next(t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]
                 if t["task_id"] == owned)
    results.append(ok(held.get("claimed_by") == "data-1" and shown.get("claimed_by") == "data-1",
                      "a claimed task records who is holding it, and the board shows it",
                      f"claim returned {held.get('claimed_by')!r} · board shows {shown.get('claimed_by')!r}"))

    # Somebody else's result, on a task that is legitimately in_progress. The status check
    # passes here — it has to, the task really is in progress — so if this goes through,
    # the only guard that could have stopped it is the one being checked.
    wrong = json.loads(await bb.submit_result(owned, subset_path="outputs/sub_wrong.csv",
                                              columns_used=COLUMNS, worker="data-2"))
    intact = next(t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]
                  if t["task_id"] == owned)
    results.append(ok("error" in wrong and "data-1" in wrong.get("error", "")
                      and intact.get("status") == "in_progress"
                      and intact.get("task_type") == "data"
                      # Refused means nothing was written, not written and rolled back
                      # later. columns_used is what that submit would have filled.
                      and intact.get("columns_used") == [],
                      "another worker's result is refused by name and nothing is written",
                      wrong.get("error", "ALLOWED")[:56]))

    # And the holder's own result still goes through — a guard that refuses everybody is
    # not a guard, it is an outage.
    rightful = json.loads(await bb.submit_result(owned, subset_path="outputs/sub_x.csv",
                                                 columns_used=COLUMNS, worker="data-1"))
    freed = next(t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]
                 if t["task_id"] == owned)
    results.append(ok(rightful.get("task_type") == "ml" and freed.get("claimed_by") == "",
                      "the holder's own result goes through, and submitting releases the task",
                      f"{rightful.get('status')} · {rightful.get('task_type')} · "
                      f"holder now {freed.get('claimed_by')!r}"))

    # ---- the whole thing, end to end -----------------------------------
    #
    # The three items above check the pieces. This one walks the accident itself: claim,
    # stall, requeue, somebody else takes it, the slow one finishes and submits. `reclaim`
    # stands in for `reclaim_stalled` — same UPDATE without the time condition, so the
    # stall does not have to be waited out.
    slow = json.loads(await bb.claim_task("ml", RUN_TAG, worker="ml-1"))["task_id"]
    await bbm.reclaim(RUN_TAG)
    requeued = next(t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]
                    if t["task_id"] == slow)
    retaken = json.loads(await bb.claim_task("ml", RUN_TAG, worker="ml-2"))
    late = json.loads(await bb.submit_result(slow, auc=0.99, worker="ml-1"))
    results.append(ok(requeued.get("claimed_by") == ""
                      and retaken.get("task_id") == slow
                      and retaken.get("claimed_by") == "ml-2"
                      and "error" in late and "ml-2" in late.get("error", ""),
                      "the stalled-worker overwrite: requeued names nobody, the second worker "
                      "takes it, the first one's late result is refused",
                      f"requeued holder {requeued.get('claimed_by')!r} → retaken by "
                      f"{retaken.get('claimed_by')!r} · late submit "
                      f"{late.get('error', 'ALLOWED — the overwrite happened')[:40]}"))

    # ---- (10) two named workers on one run, at the same time -------------
    #
    # (9) proves the contract one call at a time. This is the shape the driver actually
    # produces now that --data-agents may be more than 1: the work loop collects a lap's
    # calls and starts them with asyncio.gather, so two `data` workers reach claim_task
    # together rather than in turn.
    #
    # The gate at the top of this file already fires 12 claimers at 8 tasks and proves no
    # row is taken twice. What that one cannot show is the **name**: it claims without a
    # worker, so every row it takes is held by "". Here each claimer carries the identity
    # the driver mints (`data#1`, `data#2`), and the thing being checked is that the name
    # on the row is the name of the worker that was handed the row — not merely that some
    # name is there. Mix those up and the guard in (9) starts refusing the right worker.
    #
    # Two rounds of two rather than one round of four, because that is the driver's own
    # rhythm: the lap launches min(waiting, N) workers, they finish, the next lap looks at
    # the board again. A worker name is reused across laps and must not be a problem.
    made = []
    for trial in range(93, 97):
        r = json.loads(await bb.create_task(RUN_TAG, trial, f"perspective {trial}",
                                            f"hypothesis {trial}", COLUMNS, "HIV_DETECTABLE"))
        made.append(r["task_id"])

    taken: list[tuple[str, int]] = []          # (worker, task_id), in claim order
    for _lap in range(2):
        names = ["data#1", "data#2"]
        got = await asyncio.gather(*(bb.claim_task("data", RUN_TAG, worker=w) for w in names))
        # strict=True on purpose: gather returns one result per coroutine, so a length
        # mismatch here would mean a claim silently vanished, and zip's default would
        # hide exactly the worker whose disappearance this item exists to catch.
        taken += [(w, json.loads(g).get("task_id")) for w, g in zip(names, got, strict=True)]

    rows = {t["task_id"]: t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]}
    ids = [tid for _w, tid in taken]
    results.append(ok(sorted(i for i in ids if i is not None) == sorted(made)
                      and len(set(ids)) == len(ids)
                      # The row names the worker that was handed it — not just somebody.
                      and all(rows[tid]["claimed_by"] == w for w, tid in taken),
                      "two workers claiming together take four different tasks, each under its own name",
                      " · ".join(f"{w}→#{tid}" for w, tid in taken)))

    # Both submit, together, each naming itself. Every one has to go through: (9) showed
    # the guard refusing a stranger, and a guard that also refuses the holder under load
    # would look identical from the outside until a real run stalled on it.
    sent = await asyncio.gather(*(bb.submit_result(tid, subset_path="outputs/sub_x.csv",
                                                   columns_used=COLUMNS, worker=w)
                                  for w, tid in taken))
    moved = {t["task_id"]: t for t in json.loads(await bb.read_board(RUN_TAG))["tasks"]}
    results.append(ok(all("error" not in json.loads(s) for s in sent)
                      and all(moved[tid]["task_type"] == "ml" for _w, tid in taken)
                      # Handing the task on releases it, or the ml worker that picks it up
                      # next is refused by a data worker's name left behind on the row.
                      and all(moved[tid]["claimed_by"] == "" for _w, tid in taken),
                      "each worker's own result goes through and hands the task on, naming nobody",
                      f"{sum('error' not in json.loads(s) for s in sent)}/{len(sent)} accepted · "
                      f"holders after {[moved[tid]['claimed_by'] for _w, tid in taken]}"))

    # ---- (11) two hypothesis workers, one question bank -------------------
    #
    # (10) is the board. This is the same shape one table over, and it is the half the
    # board's claim could never cover: the bank has **no run_tag**, on purpose, because it
    # accumulates across runs. So two hypothesis agents seeding one wave both read it top
    # down and both set out from the newest question unless something marks it taken.
    # A wave of two then spends two agents to ask one thing.
    #
    # ORDER BY question_id DESC is also what makes this checkable against a bank this
    # check does not own: the two filed here are the newest rows in it, so they are
    # exactly the two the next two claims have to take. Any other pair and the ordering
    # is not what the tool says it is.
    #
    # Neither text uses the "from a ... perspective" frame the items above file under this
    # same tag. Written that way one of the two is blocked as a reword of them — measured,
    # not guessed — and then only one question reaches the bank and there is nothing for
    # the second worker to take. The dedup gate working is what item (2) checks; here it
    # is only in the way, so the two are written far from it and far from each other.
    p5 = json.loads(await bb.propose_questions(json.dumps([
        {"text": f"which laboratory chemistry values move together before a rebound ({RUN_TAG} claim)",
         "okf_tags": ["metapath"], "rationale": "one to be claimed"},
        {"text": f"whether distance to the nearest clinic changes appointment adherence ({RUN_TAG} claim)",
         "okf_tags": ["metapath"], "rationale": "a second, far enough from the first not to read as a reword"},
    ], ensure_ascii=False), origin_run=RUN_TAG, origin_wave=2))
    banked = sorted(q["question_id"] for q in p5.get("added", []))
    results.append(ok(len(banked) == 2, "two questions are banked for the workers to claim", str(banked)))

    workers = ["hypothesis#1", "hypothesis#2"]
    got = [json.loads(g) for g in
           await asyncio.gather(*(bb.claim_question(RUN_TAG, worker=w) for w in workers))]
    # strict=True for the reason given in (10): a length mismatch would mean a claim
    # vanished, and that is the worker this item exists to notice.
    claimed = [(w, g.get("question_id")) for w, g in zip(workers, got, strict=True)]
    held = {q["question_id"]: q for q in json.loads(await bb.read_questions(limit=500))["questions"]}
    results.append(ok(sorted(qid for _w, qid in claimed) == banked
                      and len({qid for _w, qid in claimed}) == 2
                      # The row names the worker that was handed it, and the run that
                      # worker belongs to — the run is what release_questions works from.
                      and all(held[qid]["claimed_by"] == w for w, qid in claimed)
                      and all(held[qid]["claimed_run"] == RUN_TAG for _w, qid in claimed)
                      # The question itself comes back with the claim. Without the text
                      # the worker holds an id and has nothing to set out from.
                      and all(g.get("text") for g in got),
                      "two hypothesis workers claiming together get the two newest questions, "
                      "each under its own name",
                      " · ".join(f"{w}→#{qid}" for w, qid in claimed)))

    # A question already claimed is not handed out again. The bank is shared, so a third
    # worker does not come back empty here — it comes back holding somebody else's
    # question, and what is being checked is that it is **not** one of these two.
    # The empty-bank branch (question_id null) is deliberately not exercised: reaching it
    # would mean claiming every open row in a bank this check did not fill.
    third = json.loads(await bb.claim_question(RUN_TAG, worker="hypothesis#3"))
    results.append(ok(third.get("question_id") not in {qid for _w, qid in claimed},
                      "a question one worker holds is not handed to the next",
                      f"the third worker got #{third.get('question_id')}, not "
                      f"{sorted(qid for _w, qid in claimed)}"))

    # Releasing is the driver's, not an agent's — the same split reclaim() above keeps.
    # It matters more here than on the board: a board row is scoped to a run and dies with
    # it, but a claim left on a bank row is permanent, so this check alone would take
    # three questions away from every run that came after it.
    freed = await bbm.release_questions(RUN_TAG)
    now_open = {q["question_id"]: (q["claimed_run"], q["claimed_by"])
                for q in json.loads(await bb.read_questions(limit=500))["questions"]}
    touched = [qid for _w, qid in claimed] + ([third["question_id"]] if third.get("question_id") else [])
    results.append(ok(freed == len(touched)
                      and all(now_open[qid] == ("", "") for qid in touched),
                      "the driver hands back every question the run was holding",
                      f"freed {freed} of {len(touched)} · holders after {[now_open[qid] for qid in touched]}"))

    # What the check made is not left behind. The second tag made above goes too.
    await cleanup()
    await cleanup_tag(other_tag)
    # sum(results) — True is 1 and False is 0, so adding them gives the number passed.
    print(f"\n  {sum(results)}/{len(results)} passed")
    # If even one failed, exit with a non-zero value. So CI or a shell notices the failure.
    return 0 if all(results) else 1


if __name__ == "__main__":
    # There used to be a `sys.path.insert` of this file's own folder here, so it could
    # find the `src/memstara/mcp_servers/blackboard.py` that sat beside it at the repository root. The board
    # server is now `memstara.mcp_servers.blackboard` in an installed package, so this
    # runs the same from any directory without help.
    raise SystemExit(asyncio.run(main()))
