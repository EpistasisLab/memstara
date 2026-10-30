# Development and release workflow

## Branches

`main` is the stable integration point for releases. `develop` holds reviewed
changes for the next release. The default branch remains `main`; installations
should use a published release when they need a fixed version.

| Change | Start from | Pull request target | Merge method |
|---|---|---|---|
| Feature, fix, refactoring | `develop` | `develop` | Squash |
| Release preparation | `develop` | `main` | Merge commit |
| Urgent production fix | `main` | `main` | Merge commit |
| Bring a hotfix or release-only change back | `main` | `develop` | Merge commit |

Use a separate topic branch per bounded change. Release merges retain ancestry;
do not squash or rebase `develop` into `main`. After a hotfix, merge `main` back
into `develop` through a reviewed PR before continuing the next release.
Existing governance bootstrap PRs opened against `main` can finish there; then
bring those changes into `develop` through a PR. Do not bypass required review.

Both branches require eight CI jobs, one independent approval of the latest
push, an up-to-date base and resolved conversations. Force pushes and deletion
are blocked. Branch routing in the table is a contributor procedure, not a
source-branch-name restriction enforced by GitHub.

The develop rules payload is [develop-ruleset.json](../.github/develop-ruleset.json).
Applying a JSON file through the GitHub API activates protection; merely
committing it does not. Official upstream enforcement is active. The private
origin mirror cannot enforce rules under its current GitHub plan. It must not
be treated as an alternate path around upstream review.

## Immutable releases

Immutable releases are enabled in both repositories for future publications.
Prepare a **draft** release first. Upload every intended archive and checksum,
verify the version, commit identity and contents, and only then publish it.
Published assets cannot subsequently be added, replaced or removed on an
immutable release. Corrections require a new version; never move an old tag.

1. Merge the reviewed release candidate into `main` and verify its CI result.
2. Confirm the release version matches the installed package and container.
3. Create a new version tag at that exact reviewed commit.
4. Build archives from that commit and calculate SHA-256 checksums.
5. Upload and validate all assets on draft releases in both repositories.
6. Publish only after the candidate and assets have been reviewed.
7. Read back the release's `immutable` field and verify tag and asset digests.

Enabling the repository setting does not retroactively make an existing release
immutable. Existing `v0.1.0` is retained unchanged; its protection status must
not be inferred from the repository setting. No release is published, replaced
or retagged by this governance change.

Publication does not deploy an application. Back up and upgrade installations
through a separately verified deployment procedure.

## Verification and references

The develop branch starts at the accepted `main` commit, not at an unreviewed
feature branch. Verify remote commit IDs and retrieve the installed rules with
`gh api repos/OWNER/REPO/rules/branches/develop`. Verify release policy using
`gh api repos/OWNER/REPO/immutable-releases` and individual releases using
`gh api repos/OWNER/REPO/releases/tags/VERSION`.

- [GitHub release immutability](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
- [GitHub repository API](https://docs.github.com/en/rest/repos/repos#enable-immutable-releases)
