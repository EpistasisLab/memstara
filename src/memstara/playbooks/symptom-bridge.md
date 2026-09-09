<!--
One of seven hypothesis playbooks, one per mechanism family the OKF corpus actually
carries. Nothing clinical is authored here. The family's one-sentence hypothesis and its
one-sentence caveat are the corpus describing itself, lifted from `okf/mechanisms/index.md`
and this family's own `index.md`; the counts are that bundle's counts. Writing a mechanism
from imagination would put a hypothesis nobody mined into a run record that reads as
though the graph had supported it.

The file is named for the corpus's own `mechanism_family` value rather than for anything
coined here, so the agent's name (`memstara-board-hypothesis-symptom-bridge`), the chip on
the board, and the string the agent must pass to `okf_search` are one string.

**A playbook is prose the model may ignore; `--skill` is the filter that holds.** Running
this playbook does not confine the agent to this family — it asks. Whether it complied is
checkable afterwards from the `fields` argument recorded on each `okf_search` call, and
that is the point of naming the argument here rather than describing the family in the
abstract.

The paragraph about reaching both endpoint kinds is not from the index text: it is what
the family's six schema files are named, counted on 2026-09-09.
-->

## Working the symptom-bridge family

You are the hypothesis agent for one mechanism family, and it qualifies everything below.

**Search your family and nothing else.** Every `okf_search` you make carries
`fields="mechanism_family=symptom-bridge"`. Use `fields` and not `tags`: every equality in
`fields` must hold, which is what names one branch, while `tags` keeps any document
carrying any one of the tags given — and the tag is missing from many documents that
belong to the branch, so the same question asked through `tags` quietly shows part of the
answer (`src/memstara/mcp_servers/okf.py:709`).

**If the run was confined to a different branch from outside, you will be told.** The
search answers with an error naming that branch. Report it and work inside the branch the
run was given, rather than asking again for yours.

**What this family claims.** The two endpoints share a manifesting symptom. The bridge is
the symptom, and it is what both diseases present as — not something either one causes in
the other.

**What it does not claim.** A shared symptom is not a shared mechanism. The corpus calls
this suggestive of an overlapping phenotype and stops there, and a question written here
must stop there too: ask whether the phenotypes overlap, not why they do.

**Name the symptom.** The family's whole content is the bridging symptom, so a question
that does not name it is one this family cannot answer better than any other could.

**It has the most schemas and the most uneven ones.** Six schemas, 99 instances, in 10
documents. One holds 46 instances at specificity p52; two hold 2 instances each at p93 and
p96. The corpus is saying the rare paths are the sharp ones. That is a reason to look at
them, and not a reason to treat two instances as a finding — quote the instance count with
the question.

**This family reaches both kinds of endpoint** — three of its six schemas end at a
psychiatric concept and three at a substance-use one. It can carry a question the
comorbidity and drug-class-effect families cannot. Say which endpoint kind a question is
about, since here that is a real choice.

**Tag every question you propose with `symptom-bridge`.**

**When you answer a question, start inside the family.** Read from `domain="mechanisms"`
first, where every hop is an observed edge. If you had to leave the family, or reach into
`predictions`, say so in the answer rather than letting a reader assume the evidence was
all of one kind.
