# Shared code for study deployments

Both local deployments use `chore/release-governance`, tracking
`origin/chore/release-governance` in `HyunjunA/memstara`.

| Local folder | Port | Study |
| --- | --- | --- |
| `memstara` | 8070 | HIV |
| `memstara-clean-check-2` | 5173 | Heart Failure |

Study selection is configuration, not a separate code branch. Registered research
inputs retain their own CSV, OKF, target, and frozen execution artifacts. The OKF
index digest selects the corpus profile in `src/memstara/corpus_skills.py`;
neither the folder name nor the port selects it. An unrecognized corpus uses the
general profile.

The HIV menu offers the five HIV hypothesis skills. The Heart Failure menu keeps
its Heart Failure skills. Results, CSV exports, input validation, and skill
management share the same implementation.

Develop and commit common changes in one checkout, push the shared branch, then
run `git pull --ff-only` in the other clean checkout. Do not make independent
commits in both folders for the same change. Rebuild/restart each deployment
separately to load updated code; a Git push does not update running services.

Local settings, ignored research data, outputs, and photos are not synchronized
by Git. Keep their existing per-deployment locations. The former
`chore/heart-failure-results` branch remains as history; ongoing development uses
the shared branch. `main`, `develop`, and the `upstream` remote are unchanged by
this consolidation.
