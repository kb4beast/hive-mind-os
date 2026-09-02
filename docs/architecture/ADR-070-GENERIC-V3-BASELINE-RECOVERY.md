# ADR-070: Squash-proof Generic V3 baseline recovery

Status: proposed adapt; implementation candidate pending independent court and CI

Date: 2026-09-02

## Context

Pull request 154 carried the complete Generic V3 history through commit
`28463ae6dd842b0b316fcf99eab98804cdaf9735`. GitHub squash-merged its tree as
single-parent commit `59a5364501c5e49ceb28574aad7a4ac1512291b9`. The trees are
identical, but the earlier V3 commits are not ancestors of `main` and the source
branch was deleted. The V3 regression suite then attempted to switch a child clone
to `9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8`. A normal clone of `main` cannot
resolve that object, so every Linux unit leg in the first post-merge Constitutional
CI run failed before the verifier was imported.

Windows exposed two independent lexical-path defects in test harnesses. Current
Windows Python also exposes a third defect: path `stat` and retained-handle `fstat`
can report different or changing `st_ctime_ns` values for the same executable while
file ID, size, modification time, creation time, native image, and bytes remain
stable.

The published V3 bytes and their adverse history remain immutable evidence. This
record defines a versioned successor correction; it does not retroactively qualify
or authorize V3.

## Atomic claims and testimony

1. A Git bundle is an offline repository transport containing refs and objects.
   `git bundle verify` checks its format and required prerequisite objects. The
   repository therefore carries a raw, SHA-256-pinned thin bundle for the severed
   range, with `44224532dc25b94a95c3184054ec81762a258259` as prerequisite and
   `28463ae6dd842b0b316fcf99eab98804cdaf9735` as its sole advertised tip.
2. Python documents `st_birthtime_ns` as creation time on Windows from Python 3.12
   and deprecates Windows `st_ctime_ns`; Microsoft separately defines `ChangeTime`
   as metadata-change time and `LastWriteTime` as data-stream write time.
3. Windows executable continuity therefore binds device, file ID, size,
   modification time, and birth time. On pre-3.12 Python, the legacy creation-time
   value in `st_ctime_ns` is the compatibility fallback. Raw Windows change time is
   retained for diagnostics but is not an acceptance field.
4. POSIX continuity continues to bind device, inode, size, modification time, and
   ctime. The exception is not global.
5. Native-image parsing and SHA-256 of the exact one-read bytes remain mandatory at
   initial configuration, before and after every process boundary, and at final
   success. A ctime-only exception cannot authorize changed bytes.

Explorer `/root/baseline_explorer` reconstructed the squash failure and the two
path-alias defects. Architect `/root/verifier_architect` specified the scoped
continuity key and adversarial matrix. Integrator/Curator `/root/pr_integrator`
cross-examined the open pull requests and rejected using any of them as the V4
baseline. `/root` is the Builder and cannot judge or promote its own candidate.

## Decision

Adapt the evidence and implementation as follows:

- authenticate and hydrate the exact V3 history from the checked-in bundle before
  any historical switch;
- fail on a missing prerequisite, malformed bundle, wrong advertised ref, wrong
  digest, or missing required commit;
- canonicalize only the two test expectations that production already
  canonicalizes;
- use the platform-specific executable continuity key both within a bounded read
  and across verification boundaries;
- retain full native-format and byte-digest authentication;
- add Windows Python 3.14 to Constitutional CI while retaining 3.12;
- preserve the published V4-manifest payload as a remanded predecessor and create a
  schema-V5 correction directly above commit `28463ae6...`; and
- make that correction independently testable as an exact eleven-path delta: seven
  modified predecessor files plus this ADR, ADR-071, the history bundle, and its
  provenance record. Those four additions may be untracked only during the bounded
  authoring check and must be regular stage-zero files in the committed candidate.

## Rejected alternatives

- A restored remote branch is mutable and can disappear again.
- A no-op ancestry merge works only if GitHub preserves a merge commit; this
  repository also permits squash and rebase merges.
- Fetching a hidden pull-request ref makes CI network topology part of the proof.
- Ignoring all ctime values would weaken POSIX continuity.
- Retrying, sleeping, or digest-only validation would hide races or discard file
  identity.
- Mutating ADR-069 in place would rewrite the published decision record.

## Threats, limits, and rollback

The bundle restores historical availability, not trust in the old candidate. Its
SHA-256, prerequisite, advertised ref, contained commits, and expected trees are
independently checked. A malicious write-and-restore wholly between observation
points remains unobservable, as do executable ACLs, alternate data streams,
dependency closure, and loader state. Activation still requires external read-only
custody, a distinct court, and the existing signature/nonce gates.

Rollback is `git revert` of the eventual candidate commit. Removing the bundle
without replacing the historical transport must make tests fail closed. Reverting
the Windows continuity correction restores the reproduced false rejection and is
not a valid promotion state.

## Acceptance

- A clone with only canonical `main` ancestry verifies and imports the bundle, then
  resolves every pinned V3 commit without a remote or hidden ref.
- Bundle digest, tamper, advertised-ref, prerequisite, and commit/tree tests pass.
- Windows ctime-only drift passes only when all continuity fields and bytes remain
  stable; altered bytes fail before `Popen`.
- Each Windows continuity field and POSIX ctime remain load-bearing.
- The four short-path-sensitive tests pass on Windows Python 3.12.
- Full Constitutional CI passes on Linux 3.11/3.12/3.14 and Windows 3.12/3.14.
- A distinct Judge issues the final `adopt`, `adapt`, `defer`, `reject`, or
  `quarantine` disposition before promotion.
