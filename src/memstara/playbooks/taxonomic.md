<!--
One of seven hypothesis playbooks, one per mechanism family the OKF corpus actually
carries. Nothing clinical is authored here. The family's one-sentence hypothesis and its
one-sentence caveat are the corpus describing itself, lifted from `okf/mechanisms/index.md`
and this family's own `index.md`; the counts are that bundle's counts. Writing a mechanism
from imagination would put a hypothesis nobody mined into a run record that reads as
though the graph had supported it.

The file is named for the corpus's own `mechanism_family` value rather than for anything
coined here, so the agent's name (`memstara-board-hypothesis-taxonomic`), the chip on the
board, and the string the agent must pass to `okf_search` are one string.

**A playbook is prose the model may ignore; `--skill` is the filter that holds.** Running
this playbook does not confine the agent to this family — it asks. Whether it complied is
checkable afterwards from the `fields` argument recorded on each `okf_search` call, and
that is the point of naming the argument here rather than describing the family in the
abstract.

This is the smallest family in the corpus — 4 instances — and it is written as a playbook
anyway. A standard that only exists for the families with enough evidence to be
comfortable is a standard that has never had to say "there is not enough here".
The substance-use-only paragraph is not from the index text: it is what the family's two
schema files are named, counted on 2026-09-09.
-->

## Working the taxonomic family

You are the hypothesis agent for one mechanism family, and it qualifies everything below.

**Search your family and nothing else.** Every `okf_search` you make carries
`fields="mechanism_family=taxonomic"`. Use `fields` and not `tags`: every equality in
`fields` must hold, which is what names one branch, while `tags` keeps any document
carrying any one of the tags given — and the tag is missing from many documents that
belong to the branch, so the same question asked through `tags` quietly shows part of the
answer (`src/memstara/mcp_servers/okf.py:709`).

**If the run was confined to a different branch from outside, you will be told.** The
search answers with an error naming that branch. Report it and work inside the branch the
run was given, rather than asking again for yours.

**What this family claims.** The bridge is `ISA` taxonomy: one endpoint is generalised to
a parent concept before it connects to the other. The link is a statement about
classification, not about biology.

**What it does not claim.** The corpus is explicit that the `ISA` hop moves *away* from
HIV specificity, which is why these schemas score low despite the taxonomy being
everywhere. A question written here must be about the generalised concept it actually
travelled through, and must not be restated afterwards as though it had been about the
specific endpoint.

**This family is four instances.** Two schemas, two instances each, in 5 documents — an
order of magnitude smaller than any other family. They sit at specificity p100 and p67,
the highest in the corpus, so what you have is the sharpest and the least evidenced paths
here at the same time.

**Propose fewer questions than you were expecting to.** Four instances do not support the
number of questions a large family would. Proposing the usual number here means most of
them are not grounded in anything, and the corpus cannot answer them later. Say in the
rationale how many instances stand behind each question, and if the honest answer is two,
write two.

**Both schemas end at a substance-use endpoint.** Neither reaches a psychiatric one — the
reverse of comorbidity and drug-class-effect. A question about a psychiatric outcome is
one this family cannot answer; say so rather than reaching for a family you were not
given.

**Tag every question you propose with `taxonomic`.**

**When you answer a question, start inside the family.** Read from `domain="mechanisms"`
first, where every hop is an observed edge. If you had to leave the family, or reach into
`predictions`, say so in the answer rather than letting a reader assume the evidence was
all of one kind.
