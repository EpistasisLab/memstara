# Third-party materials

This inventory identifies known incorporated material. It does not select a license
for Memstara-authored code or grant rights to separately supplied research assets.
A project-wide release license and complete redistribution review remain pending.

## afc-forge matcher code and test fixtures

Parts of the semantic matcher were ported from afc-forge's
`ade_forge/tools/impl/` modules. The incorporated material is identified by `SOURCE`
and `PORT NOTE` headers in:

- `src/memstara/matcher/catalog.py` (mixed original and ported functions).
- `src/memstara/matcher/embedder.py` (adapted port).
- `src/memstara/matcher/matcher.py` and `vocab.py` (ports with documented changes).
- `tests/test_matcher.py` and the identified fixtures in `tests/conftest.py`.

Those headers retain the detailed origin and modification record; they are not
replaced by this summary. Other matcher modules identify project-owned integration
code or copied configuration defaults in their own headers.

The donor repository contains the Apache License, Version 2.0. Its full text is
preserved in [licenses/afc-forge-LICENSE.txt](licenses/afc-forge-LICENSE.txt).
The copied license bytes were checked against donor revision
`aa6b4e383e4b62e2c43d70464fb39b1ecaacb06c`; SHA-256:
`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
This identifies the inspected license, not the exact original revision of every
ported code fragment. No root-level donor NOTICE file was present at that revision.
Notices attached to separate donor datasets are not clearance to distribute them.

The wheel includes this notice and that license under `memstara/third_party/`.
They must remain present in redistributed artifacts containing the ported material.

## Runtime and frontend dependencies

Motoro and the other Python and frontend packages are dependencies with their own
licenses. The lockfiles identify selected versions; this notice does not replace
those packages' license files or establish a complete dependency-license audit.
Dependency source code is not relicensed by Memstara.

## Research examples and contributed instructions

The generated CSV and OKF example in `examples/research-inputs/` declares CC0-1.0
in its README. That declaration applies to those synthetic example materials only.
It does not apply to user datasets, clinical data, supplied corpora, contributed
skills, external papers or archived research projects. Preserve their original
files and obtain applicable redistribution clearance before including them in a
public release. Successful hash verification establishes integrity, not permission.
