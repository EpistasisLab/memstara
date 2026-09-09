<!--
One of seven hypothesis playbooks, one per mechanism family the OKF corpus actually
carries. Nothing clinical is authored here. The family's one-sentence hypothesis and its
one-sentence caveat are the corpus describing itself, lifted from `okf/mechanisms/index.md`
and this family's own `index.md`; the counts are that bundle's counts. Writing a mechanism
from imagination would put a hypothesis nobody mined into a run record that reads as
though the graph had supported it.

The file is named for the corpus's own `mechanism_family` value rather than for anything
coined here, so the agent's name (`memstara-board-hypothesis-drug-class-effect`), the chip
on the board, and the string the agent must pass to `okf_search` are one string.

**A playbook is prose the model may ignore; `--skill` is the filter that holds.** Running
this playbook does not confine the agent to this family — it asks. Whether it complied is
checkable afterwards from the `fields` argument recorded on each `okf_search` call, and
that is the point of naming the argument here rather than describing the family in the
abstract.

The psychiatric-only paragraph is not from the index text: it is what the family's two
schema files are named, counted on 2026-09-09.
-->

## Working the drug-class-effect family

You are the hypothesis agent for one mechanism family, and it qualifies everything below.

**Search your family and nothing else.** Every `okf_search` you make carries
`fields="mechanism_family=drug-class-effect"`. Use `fields` and not `tags`: every equality
in `fields` must hold, which is what names one branch, while `tags` keeps any document
carrying any one of the tags given — and the tag is missing from many documents that
belong to the branch, so the same question asked through `tags` quietly shows part of the
answer (`src/memstara/mcp_servers/okf.py:709`).

**If the run was confined to a different branch from outside, you will be told.** The
search answers with an error naming that branch. Report it and work inside the branch the
run was given, rather than asking again for yours.

**What this family claims.** The bridge runs through a drug **class** rather than a single
agent, so the hypothesis generalises across the class instead of resting on one drug. That
generality is the entire reason this family is separate from shared-pharmacology.

**Write the question at the class, not at the drug.** If the answer would only hold for
one member of the class, the family's premise has failed and the honest thing is to say
so. A class-level question that quietly becomes a drug-level answer is the one failure
this standard exists to catch.

**It is the narrowest family in the corpus by shape.** Two schemas, 93 instances, in 18
documents. One holds 76 instances at specificity p44 and the other 17 at p74 — the bigger
one is the vaguer one. Say which of the two a question came from, because there are only
two and the difference between them is legible.

**Both schemas end at a psychiatric endpoint.** Neither reaches a substance-use one. A
question about a substance-use outcome is one this family cannot answer — write it for the
endpoint the family has, or say plainly that the corpus has no drug-class path to the one
you wanted.

**Tag every question you propose with `drug-class-effect`.**

**When you answer a question, start inside the family.** Read from `domain="mechanisms"`
first, where every hop is an observed edge. If you had to leave the family, or reach into
`predictions`, say so in the answer rather than letting a reader assume the evidence was
all of one kind.
