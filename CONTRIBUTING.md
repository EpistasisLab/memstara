# Contributing

Create one topic branch per independently reviewable change. Open a pull request
against `main` in the official repository. Do not push changes directly to `main`.

The main-branch rules require:

- All eight CI jobs to pass against an up-to-date base branch.
- One approval from another reviewer, including approval of the latest push.
- Resolution of all review conversations. New commits dismiss stale approvals.
- No force pushes, branch deletion, or configured bypass actors.

The reproducible ruleset is [main-ruleset.json](.github/main-ruleset.json).
A repository administrator must apply it through GitHub's repository rules API;
committing this file alone does not activate protection. Private repositories
require a GitHub plan that supports repository rules. Failed or unavailable CI
must be resolved; it must not be bypassed to merge a change.

Use the pull request template to describe behavior, review scope, actual checks,
and remaining limitations. Never include credentials, private datasets, or raw
private execution traces. For detailed review guidance, see
[REVIEW_GUIDE.md](REVIEW_GUIDE.md).

## Independent improvement branches

Implement these changes sequentially, with a separate PR for each bounded change.
Create each branch from the accepted base; do not silently stack unrelated work
or merge unreviewed changes to begin the next phase.

| Branch area | Scope | Completion evidence |
|---|---|---|
| `chore/pr-ci-guardrails` | Required PRs, review and CI | Applied rules read back from GitHub; all required checks pass |
| `chore/release-governance` | Development/release branch workflow and immutable releases | Branch-policy and release-setting verification |
| `fix/build-provenance` | Accurate build version and commit identity | Installed package and container identity tests |
| `feat/upgrade-backup` | Backup before schema changes | Failed-backup gating and isolated restore tests |
| `test/released-schema-upgrades` | Released-version upgrade and migration replay | Preserved records and repeatable schema assertions |
| `refactor/experiment-provenance` | Versions, attempts, resolved settings and terminology | Retry identity and reproducibility contract tests |
| `refactor/result-read-model` | Bounded reads, summaries and consistent aggregation | Projection rebuild, pagination and total consistency tests |
| `refactor/api-ui-contracts` | Response validation, shared query behavior and component tests | Malformed response, stale response and state-transition tests |
| `refactor/durable-execution-control` | Durable commands, deduplication and recovery | Interrupted-command and duplicate-request tests |

Each area can produce several smaller branches and PRs. Preserve existing
Motoro integration, encrypted credentials, checkpoints and evidence records.
Changes to inference behavior, data preprocessing, or scientific evaluation are
not implied by infrastructure refactoring. Multi-server workers and multi-user
authentication remain conditional on an actual hosted-service requirement.

Do not redeploy or restart active experiments as part of a documentation or
repository-policy change. A PR's checks are evidence for that candidate, not a
claim that a running installation has been upgraded.
