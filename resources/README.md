# Research input resources

This is the official repository-local layout for research inputs. Runtime outputs,
traces and generated caches belong in `outputs/`, not in this directory.

| Location | Purpose |
|---|---|
| `datasets/hiv/dataset.csv` | Supplied HIV study dataset |
| `datasets/heart-failure/dataset.csv` | Supplied HeartFailure dataset |
| `datasets/active/dataset.csv` | Exact previously configured analysis dataset, when distinct from the supplied dataset |
| `knowledge/hiv/` | Existing HIV study OKF corpus; entry point `index.md` |
| `knowledge/heart-failure/` | HeartFailure OKF corpus; entry point `index.md` |
| `knowledge/heart-failure-charter.yaml` | Supplied HeartFailure corpus scope specification |
| `knowledge/hiv-suppression/` | Separate HIV suppression corpus, without an implied dataset binding |
| `manifests/materials.local.json` | Local source paths and copy hashes |
| `manifests/sources.local.json` | Local dataset/corpus path inventory |

Clinical input directories and local manifests remain Git-ignored pending separate
publication decisions. They are not automatically available in a clone. The
synthetic example in `examples/research-inputs/` remains the included public fixture.
Inventory files are not complete or validated research configurations.

Use these paths in new research registrations or the deployment's local environment.
Existing registrations and historical snapshots are immutable and retain their
original references. Restart services between executions to adopt environment changes.
Explicit settings continue to take precedence; there is no automatic dataset switch.

Agent skills stay in `src/memstara/playbooks/` and contributed instructions in
`src/memstara/resources/contributed/`, so installed packages can resolve them.
Contributor originals are preserved. Model credentials never belong here.
