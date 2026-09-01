# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. It documents the port;
#   it is not part of it. The SOURCE-tag convention is defined below.
"""memstara.matcher — afc-forge's semantic matcher, ported into memstara.

`vocab.py`, `matcher.py`, `embedder.py` and the top half of `catalog.py` are ports
of afc-forge (`ade_forge/tools/impl/*`); each carries a PORT NOTE listing every
edit, so it stays checkable against upstream with a diff. `config.py`,
`service.py` and the bottom half of `catalog.py` are sandbox code written for
EcoXAI's 1,393 wide columns. All comments and docstrings, ported or not, are in
English.

HOW TO TELL WHOSE CODE YOU ARE READING
---------------------------------------
Every file in this package, plus `src/memstara/mcp_servers/matcher.py`, `scripts/*.py` and the
matcher's tests, opens with a `SOURCE:` comment. Four values, and they are
greppable — `grep -rn "^# SOURCE:" .` prints the whole map:

    PORTED FROM afc-forge        a copy of reviewer's file. Upstream path and line
                                 count are named. Every edit is listed in the
                                 PORT NOTE that follows. Prose inside such a
                                 file is upstream's own words, including its
                                 "FE_Demo2" and "§6.x" references.
    PORTED WITH EDITS            upstream's logic, with the listed changes.
    SANDBOX-ORIGINAL             written here. Not reviewer's.
    MIXED                        both, in one file; each top-level symbol below
                                 carries its own SOURCE tag.

Ported files are copies rather than imports on purpose: importing afc-forge's
`matcher.py` pulls in pandas, yaml, the descriptor system and the leakage
package. As copies, the only runtime dependency is numpy.

The claim "this is a copy" is meant to stay verifiable, so keep it that way — do
not add sandbox code to a PORTED file, and do not tidy upstream's wording in
one. Both turn a one-command check into a manual reading:

    diff <(sed 's|ade_forge.tools.impl|memstara.matcher|g' \\
             ../shared/afc-forge/ade_forge/tools/impl/matcher.py) \\
         src/memstara/matcher/matcher.py

As of 2026-09-01 that diff is 35 lines for `matcher.py`, 47 for `vocab.py` and
58 for `embedder.py`. Most of each is the banner and PORT NOTE themselves, which
is why the total grew when the restructure added a line to each of them. The
check that matters is the diff with comments dropped, which leaves only what the
PORT NOTEs declare — 7 lines, 27 and 32 respectively:

    diff <(sed 's|ade_forge.tools.impl|memstara.matcher|g' <upstream>) <file> \\
      | grep '^[<>]' | grep -v '^> *#'

For `matcher.py` those 7 lines are one import and two rebuild hints, and nothing
else. If that command ever prints a line the PORT NOTE does not account for, the
file is no longer a copy and this docstring is wrong.

WHAT THIS PORT DOES NOT CARRY — read before trusting it
-------------------------------------------------------
In afc-forge, `catalog.py` is the single choke point for leakage control: the
descriptor declares which concepts are off-limits for a given label, and no
feature reaches an agent without passing it. That layer cannot move here without
the descriptor system, so it did not move.

Concretely: this catalog exposes 28 antiretrovirals (MED__BIKTARVY, MED__TRUVADA,
MED__DOLUTEGRAVIR, MED__RITONAVIR, ...) plus LAB__CD4 and LAB__CD4:CD8 to an agent
predicting HIV viral suppression. That is not outcome-column leakage — the outcome
column is excluded and re-checked at load — but it is near-tautological signal, and
the matcher hands it over on a query as innocent as "antiretroviral therapy".

The matcher works exactly as afc-forge's does. It is not a leakage guard, and
nothing else in this sandbox is one either.
"""
