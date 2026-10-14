# Release readiness

This is a preparation checklist, not an approval or announcement. The same source
branch supports the public example and paper experiments; use separate input
profiles, run directories and immutable receipts, not divergent research-only code.
An experiment must record its exact revision rather than just the branch name.

## Included and excluded material

- [x] Synthetic CSV and toy OKF knowledge source under `examples/research-inputs/`.
- [x] Application source, prompts, built-in playbooks and preserved legacy playbooks.
- [x] Byte-preserving copies of six current contributed documents with a SHA-256 manifest under `src/memstara/resources/contributed/`.
- [ ] Obtain redistribution permission for contributed documents; the manifest currently records pending approval.
- [ ] Confirm the final demonstration dataset and knowledge source. The existing synthetic example is a provisional runnable fixture, not the approved replacement for any proposed external cardiac dataset.
- [ ] Select/confirm the project license and all third-party rights before publication.
- [ ] Verify the final Git tree and distributions exclude real HIV/cohort data, credentials, private notes and run artifacts. A textual HIV specialist skill is not the private HIV dataset.

Copies preserve original bytes and never use archived specialist files. A deployment
can override the specialist directory with `MEMSTARA_SPECIALIST_SKILLS_DIR`.
An explicit incomplete directory does not silently fall back to bundled files.
The optional ML reference and legacy results document can be configured with the
existing shared-document variables; see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

## Before release

- [ ] Record final source SHA, dependency locks and model/skill/input identities.
- [ ] Complete human file/function review and disposition all blocking findings.
- [ ] Validate all four input modes and affected lifecycle paths at the final candidate.
- [ ] Install and inspect a built wheel and extracted source distribution in clean environments.
- [ ] Run the documented toy route with configured model credentials and databases; save actual evidence. An offline configuration check is not this live run.
- [ ] Confirm UI/API state, report persistence and truthful actual/estimated cost presentation.
- [ ] Record required CI results; do not reuse an older candidate's live sign-off.
- [ ] Verify the exact published assets, tag, checksum and download smoke test.

```bash
python scripts/check_release_readiness.py
python scripts/check_release_readiness.py --publication
python scripts/check_public_tree.py
```

The first command checks bundled content integrity without network or model calls.
The publication mode deliberately fails while rights or owner decisions are pending.
It is not a substitute for human review, security assessment or final live acceptance.
Existing distribution and installation checks remain required; see
[tests/README.md](tests/README.md).

## Decision record

Record reviewer, reviewed SHA, evidence, unresolved issues, accepted risks and
approve/hold decision in the PR. Keep private meeting dates, participant notes and
unredacted evidence in the local planning packet. Merge, tagging and publication
require an explicit owner decision after gates are satisfied. Do not automatically
run all 64 combinations as part of release preparation.
