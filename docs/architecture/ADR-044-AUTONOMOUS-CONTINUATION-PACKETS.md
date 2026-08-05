# ADR-044: Local Governed Autonomous Continuation Packets

- **Status:** Proposed for independent Curator disposition
- **Date:** 2026-08-05
- **Case:** `CASE-CONTINUATION-PACKET-LOCAL-BOUNDARY`
- **Origin:** P03–P05 follow-on local work order; historical phase evidence is preserved

## Court record and decision

- **Advocate:** a short, versioned, content-addressed packet lets a replacement session
  resume bounded local work without being given raw conversation or model output.
- **Cross-examiner:** packets can be tampered with, point at path escapes or symlinks,
  become stale after a commit, imply remote authority, or be mistaken for approval.
- **Expert evidence:** focused deterministic tests create and validate clean local Git
  fixtures, then reject tampering, unsafe paths, unclean/stale worktrees, unsafe text,
  and remote authority grants.
- **Judge:** a separately identified Curator must decide the exact committed candidate.

**Decision: adapt.** Add a separate `continuation-packet` schema and local validator;
do not mutate `mission-state` or the legacy `handoff` contract. A packet binds a full
40-hex local HEAD, a clean worktree, safe relative artifact paths with SHA-256 digests,
bounded scope, fixed forbidden authority, a single next action, success/stopping
conditions, blockers, an independently recorded exact decision, and a decision. Its canonical digest covers every field except
the digest wrapper. Export requires caller-provided stable ID and time, so it is
deterministic for identical clean inputs.

## Threats, controls, and acceptance

| Threat | Control |
|---|---|
| Tampering or unknown fields | Strict schema plus canonical SHA-256 verification |
| Path escape, symlink, or artifact drift | Portable-path, regular-file, link, and digest checks |
| Stale or dirty repository | Exact HEAD and porcelain-status verification on export and resume |
| Accidental authority expansion | Fixed forbidden authority set; grants are local-only enum values |
| Raw output or secret retention | Only bounded plain-English summaries are accepted; secret-like markers and multiline/free-form structures are rejected |
| Historic evidence mistaken for delivery | Decision is recorded exactly, does not create approval, and must be independently verified again |

Acceptance is a successful focused export/validate round trip and deterministic rejection
of the threats above. An `approved` decision has no reason; a non-approval may retain only
a short safe summary. The offline CLI writes only an explicitly requested new local packet;
a packet by itself performs no external action.

## Rollback and limits

Revert this additive module, schema, CLI route, and ADR together. Existing mission state,
legacy handoffs, P03–P05 historical evidence, and receipts remain untouched. This does not
approve, deliver, push, merge, open a PR, obtain credentials, or satisfy the historical
P03–P05 exact-candidate Curator and CI gates. It cannot prove that a human-provided short
summary was not derived from raw output; it restricts stored form and requires independent
review. A full repository CI gate remains an explicit later delivery blocker.
