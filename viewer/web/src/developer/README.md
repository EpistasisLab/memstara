# Code Atlas

For configuration, model routing, execution controls, and debugging procedures,
see the [developer operations guide](../../../../DEVELOPER_GUIDE.md). This document
focuses on the code exploration interface.

Open `/developer.html` on the viewer origin. This is a separate React entry point,
not a research-workspace panel. It never executes runs. Source views make no API calls. Pipeline internals reads execution APIs only after explicit selection, with optional refresh.

## Refresh the inventory

From the repository root, using the project's Python 3.12 or 3.13 environment:

```sh
.venv/bin/python scripts/build_code_atlas.py
.venv/bin/python scripts/build_code_atlas.py --check
npm --prefix viewer/web run build
```

Rebuild and replace the web container to update a Docker-served viewer. Refresh the
inventory after source changes or a new base commit. The displayed fingerprint
identifies the generated snapshot; the page does not read a developer's filesystem.

## Explore

- **System map** groups source by responsibility and opens each layer's entry point.
- **Source explorer** searches file paths, extracted declarations and literal API paths.
- **Dependencies** shows resolved imports and importers around the selected file. The
  diagram limits each side to 12 neighbors; the inspector retains the complete lists.
- **Reading paths** provides curated entry points for four cross-layer workflows.
- **File inspector** lists symbols and path references, links to the base Git commit,
  and copies a relative path for opening a local working copy. Local changes are marked.
- The selected file is encoded in the URL so a view can be bookmarked or shared.

## Coverage and interpretation

The inventory contains metadata for Memstara runtime, viewer code, runtime prompts,
tests and repository scripts. It excludes credentials, runtime records, data, personal
notes, external library internals and deployment configuration. Source bodies are not
embedded in the page. GitHub access remains subject to repository permissions.

Python imports/declarations are parsed with AST. JS/TS literal imports and top-level
named declarations use lexical scanning, not a TypeScript compiler or runtime trace.
Conditional and type-only imports may appear; computed imports, external dispatch,
HTTP relationships and prompt-loading relationships are not inferred as import edges.
Endpoint references are distinguished from decorated HTTP route declarations.

Layer descriptions and reading paths are curated. Import arrows mean `importer ->
imported file`, not a function invocation or execution order. Tests in the inventory
are not evidence that those tests have run. Commit links may differ from local edits;
new local files may not exist at the base commit.

## Pipeline internals

The Execution blueprint explains the board runner in this checkout, including
launch, checkpoints, provisioning, combination selection, question contracts,
feature grounding, task ownership, data/ML tools, interpretation fan-out, reports,
archival, conditional repair and pause/resume. Solid edges are logical handoffs;
dashed edges are conditional paths. These are source-reviewed documentation, not
an automatically inferred call graph. The blueprint must be reviewed after runner
changes. The historical `phil-pipeline` implementation is not substituted for this
checkout's data/ML agent path.

Inspect an execution explicitly loads the read API. Select an execution and optional
loop, then an invocation, then a stored step. Metadata is paginated in groups of 50;
full step fields load individually. Tool cards display recorded arguments/results,
with the complete underlying fields expandable below. Loop attribution discloses
recorded, boundary-derived or unassigned provenance. Stored call status does not
prove process liveness. No missing payload, step or timestamp is synthesized.

Read API routes: `/api/developer/execution` and `/api/developer/steps`. The latter
verifies invocation membership in the selected execution before touching the core
history. They use the existing SELECT-only database pool; there are no control
commands. Raw execution evidence can contain private research content and should
be viewed on the existing authorized local deployment. It is not bundled into the
static source inventory. This interface inspects persisted records; it does not
provide breakpoints or unrecorded Motoro internals.

## Animated Agent Explorer

Open `/developer.html?view=agents` for an eight-chapter explanation that is fully
expanded by default: knowledge, question, hypothesis, data, ML, interpretation,
explanation and memory. Each chapter shows inputs, processing, outputs, a fictional
teaching example and storage responsibility. Question/hypothesis examples explain
the server-owned fixed-target templates rather than implying unconstrained model
text. All content remains visible when motion is paused. Intersection and page
visibility gate animations; reduced-motion preferences disable them.

The optional technical explorer below retains the educational walkthrough of 20 components:
five agent roles, knowledge and data files, MCP tools, runtime/control/read API,
and the separate Memstara and Motoro databases. The complete investigation has
47 logical transfers, including model request/response boundaries for every role.
Question generation is a phase of Hypothesis, not an additional agent.

Four scenarios cover normal investigation, question repair, pause/resume and all
combinations. Play/pause, previous/next, restart, a position slider, speed selection,
component inspection and transfer focus work without API calls or model execution.
Mobile defaults to a two-component transfer view; all components remain reachable
through the component selector. Reduced-motion preferences disable moving packets;
hiding the page pauses playback. Timings, animation positions and sequence are
illustrative, not measurements of a real execution. Logical return paths and
cross-cutting persistence are labeled explicitly.

Actor profiles list responsibilities, inputs, outputs, allowed tools and recovery
boundaries. Tool permissions are checked against the Python runner definitions in
`tests/test_agent_explorer.py`; source links are also checked. Narratives are
source-reviewed and must be updated when orchestration changes. The role boundaries
come from current prompts, including factual Interpretation versus Explanation.
The recorded-execution button opens the existing read-only inspector; records are
loaded only after the user requests them. No clinical examples or patient records
are bundled with the animation.

## Focused OKF-to-hypothesis lesson

`/developer.html?view=agents&lesson=hypothesis` shows an eight-step plain-language
retelling of one locally recorded run. English/Korean selection uses `lang=ko`.
The initial assignment and AI/software exchanges are paraphrases, not verbatim
model dialogue or private reasoning.

`detail=1` opens a paginated detailed lesson. Exactly one of eight stages is mounted.
Previous/Next, the stage list and Start again control navigation. Stable stage IDs
in `step=` persist across reload and browser back/forward; old `#hyp-...` links
still select their stage. Navigation moves keyboard focus to the lesson heading.
Original records and general implementation diagrams are collapsed until requested.
The four knowledge categories are optional and displayed one at a time.

Search defaults to the current implementation, with five navigable substeps:
category discovery, AI request, validation, metadata scoring and candidate return.
Each identifies the actor, a plain-language example and the handoff. Historical
search descriptions remain in a separate collapsed disclosure in both views; the
current walkthrough is not presented as a newly completed LLM experiment.

The gitignored `/local-examples/hypothesis.json` is loaded once. It contains curated,
allowlisted bilingual `story`, `walkthrough` and optional `categories`, with original
excerpts and trace references. Data is not embedded in tracked source or the metadata
inventory. Missing data produces an explicit message and no invented recorded output.
Source-derived files and builds containing them must be reviewed before distribution.

Schematic diagrams use fictional Marker A/B and outcome Y, distinct from actual
recorded examples. Source interpretation is not treated as verified scientific fact.
Recorded document counts and conflicting corpus evidence labels are explicitly
explained. Selecting a category does not imply the agent read it during the run.

Tool/function names and common fields have bilingual hover, focus and tap help.
Original strings remain unchanged. Animations support pause and reduced motion;
changing lesson pages does not invoke application APIs or run any agents.
