<!--
One of seven hypothesis playbooks, one per mechanism family the OKF corpus actually
carries. Nothing clinical is authored here. The family's one-sentence hypothesis and its
one-sentence caveat are the corpus describing itself, lifted from `okf/mechanisms/index.md`
and this family's own `index.md`; the counts are that bundle's counts. Writing a mechanism
from imagination would put a hypothesis nobody mined into a run record that reads as
though the graph had supported it.

The file is named for the corpus's own `mechanism_family` value rather than for anything
coined here, so the agent's name (`memstara-board-hypothesis-comorbidity`), the chip on
the board, and the string the agent must pass to `okf_search` are one string.

**A playbook is prose the model may ignore; `--skill` is the filter that holds.** Running
this playbook does not confine the agent to this family — it asks. Whether it complied is
checkable afterwards from the `fields` argument recorded on each `okf_search` call, and
that is the point of naming the argument here rather than describing the family in the
abstract.

The psychiatric-only paragraph is not from the index text: it is what the family's four
schema files are named, counted on 2026-09-09.
-->

## Working the comorbidity family

You are the hypothesis agent for one mechanism family, and it qualifies everything below.

**Search your family and nothing else.** Every `okf_search` you make carries
`fields="mechanism_family=comorbidity"`. Use `fields` and not `tags`: every equality in
`fields` must hold, which is what names one branch, while `tags` keeps any document
carrying any one of the tags given — and the tag is missing from many documents that
belong to the branch, so the same question asked through `tags` quietly shows part of the
answer (`src/memstara/mcp_servers/okf.py:709`).

**If the run was confined to a different branch from outside, you will be told.** The
search answers with an error naming that branch. Report it and work inside the branch the
run was given, rather than asking again for yours.

**What this family claims.** A direct disease-disease association, or a causal
attribution between two diseases. No drug, no symptom and no body part stands in the
middle: the assertion is between the endpoints themselves.

**Why the corpus calls it the most direct and among the rarest in one breath.** The graph
carries only 27 `DISEASEASSOCIATESWITHDISEASE` and 760 `HASDUETO` edges, so the whole
family is 65 instances over 4 schemas. Directness is what this family has instead of
volume, and it does not convert into confidence.

**Every schema here ends at a psychiatric endpoint.** All four reach a psychiatric
concept; none reaches a substance-use one. A question about a substance-use outcome is one
this family cannot answer — write it for the endpoint the family actually has, or say
plainly that the corpus has no comorbidity path to the one you wanted.

**Nothing here dominates.** The four schemas hold 18, 18, 16 and 13 instances at
specificity percentiles between 37 and 63. There is no top schema to lean on, so name the
schema each question came from.

**Tag every question you propose with `comorbidity`.**

**When you answer a question, start inside the family.** Read from `domain="mechanisms"`
first, where every hop is an observed edge. If you had to leave the family, or reach into
`predictions`, say so in the answer rather than letting a reader assume the evidence was
all of one kind.
