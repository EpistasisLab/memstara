# HIV Hypothesis Skills — Overview

This inventory covers the four hypothesis perspectives selected in the existing
HIV experiment and every Markdown file currently in `docs/skill-drafts/`.
All perspectives preserve the configured HIV outcome and map eligible predictors
to the supplied CSV definitions. The No Knowledge condition uses no retrieved OKF.
Knowledge-using perspectives retrieve the selected sources; the proposed hybrid
explicitly separates general-knowledge predictors from graph-grounded additions.

## Four perspectives selected in the existing experiment

| Skill | One-line summary | File |
|---|---|---|
| Addiction KB — Psychiatric disorders | Uses documented psychiatric disorders, symptoms and comorbidities to select CSV predictors and develop a hypothesis about the fixed HIV outcome. | [addiction-psychiatric.md](../src/memstara/playbooks/addiction-psychiatric.md) |
| Addiction KB — Substance use disorders | Uses OKF evidence about substance use, related disorders and treatment context to develop an HIV outcome hypothesis with available CSV predictors. | [addiction-substance-use.md](../src/memstara/playbooks/addiction-substance-use.md) |
| HIV — No Knowledge | Generates a hypothesis from the LLM's general biomedical knowledge and CSV feature definitions without retrieving OKF, literature or other external evidence. | [hiv-no-knowledge.md](../src/memstara/playbooks/hiv-no-knowledge.md) |
| HIV — Whole Knowledge Graph | Explores the entire selected OKF without a preselected clinical specialty and verifies that the proposed hypothesis has eligible CSV predictor mappings. | [hiv-okf-whole-graph.md](../src/memstara/playbooks/hiv-okf-whole-graph.md) |

The table uses the application-facing names. Some original Markdown headings differ
from their catalog display titles. Adding a catalog option does not add it to the
existing experiment's frozen combination plan.

## Files in `docs/skill-drafts/`

| Skill / document | One-line summary | Registration status | File |
|---|---|---|---|
| HIV — Medication and Treatment Pathways | Develops medication-centered hypotheses using documented treatment, toxicity and drug-class relationships mapped to available CSV predictors. | Draft only. | [hiv-medication-treatment-pathways.md](skill-drafts/hiv-medication-treatment-pathways.md) |
| HIV — Shared Symptom Patterns | Uses documented shared symptom relationships and corresponding CSV measurements to test a coherent manifestation-based HIV outcome hypothesis. | Draft only. | [hiv-shared-symptom-patterns.md](skill-drafts/hiv-shared-symptom-patterns.md) |
| HIV — Anemia-Associated Findings | Focuses on documented anemia-related paths and eligible hematologic measurements to develop a hypothesis about the fixed HIV outcome. | Draft only. | [hiv-anemia-associated-findings.md](skill-drafts/hiv-anemia-associated-findings.md) |
| HIV — Complication-Linked Pathways | Starts from documented HIV-related complication anchors and maps their clinical relationships to measurable predictors without assuming causation. | Draft only. | [hiv-complication-linked-pathways.md](skill-drafts/hiv-complication-linked-pathways.md) |
| HIV — Integrated Clinical and Knowledge Perspectives | Combines outcome-focused general clinical reasoning with immune, treatment, psychiatric, substance-use and complication perspectives, verified against selected OKF evidence and CSV definitions. | Registered in source as an additional HIV hypothesis option; production deployment not confirmed. | [hiv-integrated-clinical-knowledge.md](skill-drafts/hiv-integrated-clinical-knowledge.md) |
| HIV — Whole Knowledge Graph: CSV-Guided Discovery (V2) | Begins candidate discovery with CSV feature definitions and general biomedical reasoning, then checks support across the selected OKF while allowing graph evidence to introduce alternative candidates. | Draft only; separate from the original Whole Knowledge Graph skill. | [hiv-okf-whole-graph-csv-guided-v2.md](skill-drafts/hiv-okf-whole-graph-csv-guided-v2.md) |
| HIV — Model Knowledge with Graph Augmentation | Freezes a general-knowledge CSV predictor set, then proposes source-grounded additions from the whole OKF for comparison against the unchanged initial candidate. | Registered in source with a two-phase driver and training-CV candidate selection; production deployment and HIV performance superiority are not yet verified. | [hiv-model-knowledge-with-graph-augmentation.md](skill-drafts/hiv-model-knowledge-with-graph-augmentation.md) |
| Medication and Treatment Pathways — Korean translation | Provides a Korean translation of the medication-centered draft for personal review, with the same research perspective as its English original. | Review translation; not a separate experimental condition. | [hiv-medication-treatment-pathways.ko.md](skill-drafts/hiv-medication-treatment-pathways.ko.md) |

There are **eight draft-folder files representing seven distinct skill perspectives**;
the Korean translation is not an additional perspective. The registered Integrated
skill also has a matching runtime copy at
[src/memstara/playbooks/hiv-integrated-clinical-knowledge.md](../src/memstara/playbooks/hiv-integrated-clinical-knowledge.md).

## Main distinctions

| Comparison | Main distinction |
|---|---|
| No Knowledge vs. original Whole Knowledge Graph | No Knowledge relies on general model knowledge and feature definitions; Whole Knowledge Graph adds retrieved graph evidence and source attribution. |
| Original Whole Knowledge Graph vs. CSV-Guided Discovery (V2) | The original starts by mapping and exploring the graph; V2 explicitly develops provisional candidates from CSV definitions before broad graph verification and refinement. |
| Integrated Clinical and Knowledge Perspectives vs. CSV-Guided Discovery (V2) | Integrated explicitly considers complementary clinical perspectives; V2 emphasizes the order and interaction of CSV-based candidate discovery and unrestricted graph exploration. |
| Model Knowledge with Graph Augmentation vs. Integrated / V2 | The hybrid preserves a frozen general-knowledge candidate without requiring a graph source for those initial predictors, then measures the additional value of separately grounded graph additions using its dedicated driver. |
| Domain drafts vs. broad perspectives | Medication, symptoms, anemia and complications each supply a focused starting perspective; the broad perspectives do not preselect one specialty. |

These are behavioral instructions for hypothesis generation, not changes to CSV
contents, missing-value handling, splitting, model fitting or evaluation. A new
perspective does not imply improved predictive performance without a suitable
comparative evaluation.

## Implemented hybrid execution

The runtime copy is
[hiv-model-knowledge-with-graph-augmentation.md](../src/memstara/playbooks/hiv-model-knowledge-with-graph-augmentation.md).
Its protocol is `model_knowledge_graph_augmentation_v1`.

1. The driver creates a separate agent from the frozen No Knowledge instructions.
   Its only tools are predictor-catalog lookup and `freeze_hybrid_candidate`.
2. The accepted initial mappings and their checksum are saved in
   `hybrid_baseline_<wave>.json`; retries reuse the same record.
3. The graph-enabled agent proposes the original mappings followed by an optional
   coherent augmentation. General-knowledge mappings retain blank source IDs;
   additional mappings require selected OKF source IDs. Both are rechecked at task creation.
4. The ML worker compares baseline and expanded predictors with the same outer
   split, training-CV folds, parameters and threshold. At least two CV folds and
   one outer split per Loop are required. These comparisons use the existing
   preprocessing and missing-value handling.
5. Mean training-CV AUROC chooses the expanded candidate only when it improves by
   more than 1e-12; ties or lower CV scores retain the baseline. Held-out scores do
   not select the candidate. The selected model is refitted, its predictions checked
   for reproduction, and its actual feature list is recorded.
6. `hybrid_selection` and `comparison` preserve the candidate identities, CV scores,
   held-out results and chosen candidate. The selected model's reproducibility
   bundle includes `hybrid-selection.json` and its integrity hash.

All Combinations supports this skill as a separate condition with one hypothesis
and one task per Loop. It does not alter an existing frozen schedule. Synthetic
offline checks establish execution and selection behavior; they do not establish
an improvement on the HIV dataset.

## Runtime diagnostics and retry identity

Read-only scheduler polls use `read_board(state_only=True)` so they do not repeatedly
transfer every historical match trace, model evaluation and narrative. Full evidence
remains available through the ordinary read/export paths. Python timeouts and MCP's
explicit response-timeout code 408 receive bounded read-only retries. Invalid
arguments, permanent errors and non-idempotent actions are not blindly replayed.

| Record | Information retained |
|---|---|
| `board_read_events.jsonl` | UTC time, correlation ID, operation/server/tool, original Loop identity, timeout, attempt, elapsed time, retry delay and outcome; controller tool failures also include nested exception metadata. |
| `failure_frames.json` | UTC failure time, original Loop, last recorded call, source locations and nested exceptions with MCP codes, database SQLSTATE/errno and provider correlation metadata when available. |
| `pipeline_status.json` | Terminal state, failure classification/message, original controller Loop and the diagnostic filename. |
| `stop_events.jsonl` | Append-only stop incidents with UTC time, event ID, reason code, original Loop, last recorded call and nested exception metadata. Resume does not erase earlier incidents. Pause, cancellation, startup rejection, ownership loss and cleanup warnings are distinguished. |
| `iteration_outcomes.json` | Outcomes indexed by original scheduled Loop IDs, including sparse retry selections. |

Diagnostics omit exception payload text, locals, credentials, prompts and patient
records. A last completed agent call is context, not proof that the agent caused
the controller failure. Unrecoverable transport failures remain visible failures,
not fabricated completed analyses.

The exception tree marks any diagnostic depth or child-count truncation explicitly.
The journal cannot capture an operating-system hard kill, power loss or an inability
to write the output filesystem; an absent terminal record is incomplete evidence,
not proof of a normal stop.

For a retry that begins at Loop 29, the 22nd attempted selected Loop is Loop 50.
Attempt counts must never replace original IDs when closing or completing a run.
Historical progress written with the count is corrected in the API presentation
using the execution manifest, with `recorded_iteration` and `identity_source`
retained. Retry counts exclude phantom ordinals outside the saved selection;
historical files are not overwritten by that presentation repair.
