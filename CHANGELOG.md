# Changelog

## v0.1.0 — First MVP release

- Create experiments from CSV research inputs and selected agent skills.
- Configure missing-value handling, train/test splitting, execution order and replicates.
- Configure Azure Foundry models using server defaults or a checked experiment connection.
- Monitor execution and use saved progress for supported pause/resume recovery.
- Browse completed Interpretation outputs, Explanation outputs and usage by pipeline and replicate.
- Install the Docker application with the included Heart Failure demonstration and Motoro 0.13.0.

### Validation and scope

The release uses local backend, frontend, browser and container checks. GitHub
Actions is currently prevented from starting by the repository owner's account
billing/spending-limit restriction; this release does not claim a successful
hosted CI run. A new paid end-to-end LLM run was not performed for this tag.

This is an initial MVP, not a promise of stable APIs or validated clinical use.
Existing release-readiness records retain outstanding review and evidence items;
tagging does not mark those records approved.
