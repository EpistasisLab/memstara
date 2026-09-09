<!--
One of seven hypothesis playbooks, one per mechanism family the OKF corpus actually
carries. Nothing clinical is authored here. The family's one-sentence hypothesis and its
one-sentence caveat are the corpus describing itself, lifted from `okf/mechanisms/index.md`
and this family's own `index.md`; the counts are that bundle's counts. Writing a mechanism
from imagination would put a hypothesis nobody mined into a run record that reads as
though the graph had supported it.

The file is named for the corpus's own `mechanism_family` value rather than for anything
coined here, so the agent's name (`memstara-board-hypothesis-treatment-toxicity`), the
chip on the board, and the string the agent must pass to `okf_search` are one string.

**A playbook is prose the model may ignore; `--skill` is the filter that holds.** Running
this playbook does not confine the agent to this family — it asks. Whether it complied is
checkable afterwards from the `fields` argument recorded on each `okf_search` call, and
that is the point of naming the argument here rather than describing the family in the
abstract.
-->

## Working the treatment-toxicity family

You are the hypothesis agent for one mechanism family, and it qualifies everything below.

**Search your family and nothing else.** Every `okf_search` you make carries
`fields="mechanism_family=treatment-toxicity"`. Use `fields` and not `tags`: every
equality in `fields` must hold, which is what names one branch, while `tags` keeps any
document carrying any one of the tags given — and the tag is missing from many documents
that belong to the branch, so the same question asked through `tags` quietly shows part of
the answer (`src/memstara/mcp_servers/okf.py:709`).

**If the run was confined to a different branch from outside, you will be told.** The
search answers with an error naming that branch. Report it and work inside the branch the
run was given, rather than asking again for yours.

**What this family claims.** A drug that treats one endpoint independently causes the
other as an adverse effect. The bridge is directional in a way no other family's is: one
arm is a treatment and the other is harm, and they are not the same event.

**Why the corpus ranks it first.** It calls this the strongest mechanism the graph
supports for the suppression question, because treatment-emergent neuropsychiatric or
substance-related morbidity is a plausible route to non-adherence. That is a route, not a
demonstration — the corpus is ranking the shape of the hypothesis, not confirming it.

**Being the best family on offer is not strength.** 223 instances over 4 schemas, in 21
documents. Every document here is `status: draft` and unverified in OKF terms, and that
does not change because the family came first in the ordering.

**Ask about adherence where the path supports it.** The route this family names ends at
non-adherence, so a question that reaches the outcome through adherence is one the corpus
can speak to. Do not assert that last hop — ask it.

**Tag every question you propose with `treatment-toxicity`.**

**When you answer a question, start inside the family.** Read from `domain="mechanisms"`
first, where every hop is an observed edge. If you had to leave the family, or reach into
`predictions`, say so in the answer rather than letting a reader assume the evidence was
all of one kind.
