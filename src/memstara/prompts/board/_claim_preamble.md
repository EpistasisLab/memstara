<!--
Not an agent — a fragment, included by `{{_claim_preamble}}` on a line of its own in
data.md, ml.md and interpreter.md. It has no front matter because it has no goal.

It is the text given to the three stages that **take** work from the board. It is not
given to the hypothesis stage: that stage does not take work, it **creates** it.

The most important sentence is number 2: when there is nothing to take, **stop.**
Without it written down, an agent invents work that does not exist or takes a task of
somebody else's type.

The runs of spaces inside the numbered items are not a typo. This text was a Python
string literal until 2026-09-02 and the continuation indent of each source line was
inside the quotes. They are preserved exactly, because moving this text to a file was
not allowed to change one character of what an agent is told. Removing them is a
prompt change, and a prompt change is an experiment: its own commit, its own evidence.
-->

Your work comes from a shared board, not from this message.

1) Call claim_task with your own type, **the run_tag you were given in this    message**, and **the worker name you were given in this message**. It hands you    one task from that run and marks it taken, under your name, so nobody else picks    it up. Passing the run_tag matters: without it you may be handed a task left    behind by an unrelated run, and the work you do will be filed under that run    instead of this one.
2) If it answers with a null task_id, there is nothing for you. **Stop there.** Do    not invent work, and do not claim a task of another type — that is somebody    else's job and taking it breaks the arrangement.
3) Do your part on the task you were handed.
4) Call submit_result with what you produced, **and with the same worker name**.    That records it and passes the task to whoever comes next.

There may be several of you working the same board at the same time, which is why the name in step 1 and the name in step 4 must be the same one. If a task of yours sat untouched long enough to be presumed abandoned, it is returned to the queue and somebody else may already be doing it. The name is how submit_result can tell you that instead of letting you write over their work. Give no name and it cannot tell you anything.
