# ADR-070: Squash-proof Generic V3 baseline recovery

Status: adapted as an immutable, non-activatable V4 predecessor

Date: 2026-09-02

## Context

Pull request 154 carried the complete Generic V3 history through commit
`28463ae6dd842b0b316fcf99eab98804cdaf9735`. GitHub squash-merged its tree as
single-parent commit `59a5364501c5e49ceb28574aad7a4ac1512291b9`. The trees are
identical, but the earlier V3 commits are not ancestors of `main` and the source
branch was deleted. The V3 regression suite then attempted to switch a child clone
to `9b1cbcfe500e2253c70cb407b6c5e0493b63aaa8`. A normal clone of `main` cannot
resolve that object, so every Linux unit leg in the first post-merge Constitutional
CI run failed before the verifier was imported. The archived pull-request and CI
observations are `SRC-V3R-PR154-001` and `SRC-V3R-CI32674854589-001`.

Windows exposed two independent lexical-path defects in test harnesses. Current
Windows Python also exposes a third defect: path `stat` and retained-handle `fstat`
can report different or changing `st_ctime_ns` values for the same executable while
file ID, size, modification time, creation time, native image, and bytes remain
stable.

The published V3 bytes and their adverse history remain immutable evidence. This
record defines a versioned successor correction; it does not retroactively qualify
or authorize V3.

## Atomic claims and testimony

1. A Git bundle is an offline repository transport containing refs and objects,
   and `git bundle verify` checks its format and required prerequisite objects
   (`SRC-V3R-GIT-BUNDLE-001`; `CLM-V3R-001`, `CLM-V3R-002`). It does not establish
   publisher authenticity (`CTR-V3R-001`). The repository therefore carries a
   raw, SHA-256-pinned thin bundle for the severed range, with
   `44224532dc25b94a95c3184054ec81762a258259` as prerequisite and
   `28463ae6dd842b0b316fcf99eab98804cdaf9735` as its sole advertised tip.
2. Python documents `st_birthtime_ns` as creation time on Windows from Python 3.12
   and deprecates Windows `st_ctime_ns` (`SRC-V3R-PYTHON-STAT-001`;
   `CLM-V3R-003`, `CLM-V3R-004`). Microsoft separately defines `ChangeTime` as
   metadata-change time and `LastWriteTime` as data-stream write time
   (`SRC-V3R-MICROSOFT-FILE-BASIC-INFO-001`; `CLM-V3R-005`, `CLM-V3R-006`).
   Timestamp availability, resolution, and point-observation limits remain
   explicit (`CTR-V3R-002`, `CTR-V3R-003`).
3. As an architecture inference from those sources and the reproduced tests,
   Windows executable continuity therefore binds device, file ID, size,
   modification time, and birth time. On pre-3.12 Python, the legacy creation-time
   value in `st_ctime_ns` is the compatibility fallback. Raw Windows change time is
   retained for diagnostics but is not an acceptance field. Timestamp continuity
   never replaces native-image and exact-byte authentication (`CTR-V3R-004`).
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
The cited claims, counterclaims, immutable upstream identities, retrieval times,
licenses, byte counts, and raw SHA-256 observations are preserved in
`evidence/audits/generic-v3-baseline-recovery/SOURCE-INTAKE.json`. That record
binds a deterministic raw-exhibit archive containing the exact technical sources,
their licenses, PR metadata, CI run/job metadata, and the downloaded CI logs.

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
- make that correction independently testable as an exact seventeen-path delta: eight
  modified predecessor files plus this ADR, ADR-071, the history bundle, its
  provenance record, the external-source intake, the two predecessor qualification
  reports, the published-parent assessment, and the raw-source archive. Those nine
  additions may be untracked only during the bounded authoring check and must be
  regular stage-zero files in the committed candidate.

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
- The strict source-intake schema binds all five source records, all ten archived
  raw exhibits, their immutable or point-in-time identities, licenses, atomic
  claims, and counterclaims.
- Windows ctime-only drift passes only when all continuity fields and bytes remain
  stable; altered bytes fail before `Popen`.
- Each Windows continuity field and POSIX ctime remain load-bearing.
- The four short-path-sensitive tests pass on Windows Python 3.12.
- Full Constitutional CI passes on Linux 3.11/3.12/3.14 and Windows 3.12/3.14.
- A distinct Judge issues the final `adopt`, `adapt`, `defer`, `reject`, or
  `quarantine` disposition before promotion.

## Final bounded judgment

Distinct Curator `/root/v3_r2_curator` and Judge `/root/v3_r4_judge` independently
reviewed exact commit `ce692c0145d9c7611b34383974fde1c78903c5ef`, tree
`86e502763fcfd924094ba8194dd0c31b114652a9`. The Judge issued `ADAPT`: R4 is
adequate only as immutable historical recovery and a non-activatable V4 predecessor.
The exact qualification receipt is
`evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json`.

The court retained a material P2 dissent: the green R4 build-evidence job generated
and attested only its wheel because three configured Anchore inputs were unsupported;
it did not retain or attest an SBOM. Pull-request-only dependency and license review
was also skipped. V4 must correct and remotely prove both gates before any release
claim. External custody, signatures, dependency closure, lease, nonce, activation,
deployment, protected merge, A5, and superiority remain unclaimed and unauthorized.
