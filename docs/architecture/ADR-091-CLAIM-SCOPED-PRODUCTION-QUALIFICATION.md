# ADR-091: Claim-scoped production qualification

## Status and source

`ADAPT`, 2026-09-21. The source is the owner's directive to simplify the
qualification path and make that protection general: "make sure that the
overcomplcation is much more simple ... even if its not related to roblox." The
owner then removed Roblox from the current pilot. The independent court record is
`ADR-091-CLAIM-SCOPED-PRODUCTION-QUALIFICATION-REVIEW.md`.

## Decision

Every pilot, stage envelope, and closeout manifest declares one closed scope:

- `bounded-operational-production-pilot` qualifies operation only for the exact
  declared candidate and targets.
- `full-autonomy-or-superiority` retains the N30 tournament, N31 self-pilot, N32
  external pilot, and N33 closeout burden.

The bounded path runs host bootstrap, N32, and N33. It does not run N30 or N31.
It still requires adopted N28 and N29 evidence, an independently qualified exact
production candidate, a candidate-bound host receipt, a pilot-bound authority
receipt, admitted target and runtime receipts for every subject, a real 72-hour
observation, restart evidence, accepted delivery receipts, and tested rollback.
The closeout may support only the declared targets and observation window. It does
not satisfy B-OPS-04 by itself, decide general release readiness, or support full
autonomy or superiority.

The full scope adds an exact N30 benchmark candidate and N31. Production evidence
cannot satisfy N30, and N30 evidence cannot replace production evidence. Roblox is
optional domain evidence and is never an implicit generic external-pilot
prerequisite.

## Contract and migration

`QualificationClaimScope` is the Python enum. PowerShell uses the same two literal
values in closed parameter sets. Pilot state stores the scope with its plan; release
manifests and stage/process envelopes use schema version 2 and store it directly.
Schema-version-1 release manifests and retained stage state without a scope load as
`full-autonomy-or-superiority`. They cannot be silently downgraded. Reusing a state
root under another scope fails closed.

The digest-bound V2 campaign plan remains historical and keeps its original full
N30-to-N32 dependency. This ADR does not rewrite sealed plan bytes. The scoped
PowerShell launcher and qualification contracts are the versioned bounded-path
overlay; a future plan compiler may encode the same enum in a successor plan.

Candidate, host, and independent-production receipts bind the exact candidate
digest. Supervisor and delivery-authority receipts bind the pilot identity, and the
authority receipt digest must equal the plan's authority digest. Target and runtime
receipts must cover every declared external subject. Evidence references remain
subject to host authentication; a label or unit fixture cannot create authority.

## Threats and acceptance

The main threats are scope omission, a bounded-to-full claim escalation, candidate
or pilot substitution, stale retained state, benchmark-only substitution, an
incomplete observation window, and missing rollback. Closed enums, conservative
legacy loading, exact identity checks, claim-specific prerequisites, and negative
tests fail these cases closed. Any pause or unaccounted gap prevents the observation
receipt from attesting the full window; the window must restart or be extended until
72 actual qualified hours exist.

The Steward owns runtime and recovery evidence, the Integrator owns exact bindings
and schema compatibility, the Curator independently reproduces the candidate and
receipts, and the Optimizer owns outcome measures. Bounded closeout measures the
declared targets' accepted outcomes, duplicate effects, avoidable owner questions,
restart recovery, and rollback. General production or release readiness remains a
separate B-OPS-04 adjudication.

## Evidence and rollback

The observed baseline is `ed96ffde57304d6b1ab7923e4d219640ac96b44f`, tree
`34f0332108193851117e159b200c30bacfdbe1e8`. The trusted-host receipt at
`%LOCALAPPDATA%\HiveMindOS\whole-os-codex-host-ed96ffde\startup-receipts\20260921T230947644290Z-b23f561d.json`
reported complete non-synthetic startup, the exact clean head/tree, distinct
Curator and Builder sessions, and 16 focused tests. Its receipt SHA-256 is
`fa9df5d1714a8e5fdcb2496e6cf2e68ca7526f55175466bfcb3488773047e8b7`.

The N30 stage receipt at
`%LOCALAPPDATA%\HiveMindOS\whole-os-codex-host-ed96ffde\n30-tournament\stage-current.json`
reported typed `blocked`: authenticated admission, evaluator custody, a bounded
lease, comparator recipes and rights, candidate bytes, manifests, signatures, and
custody were absent. No lane or external effect ran. These observations justify the
scope split; neither closes the bounded pilot for a future successor candidate.

Rollback reverts this ADR and the matching implementation while retaining all
receipts, blockers, dissent, and prior strict interpretations. A later appeal needs
new evidence or a versioned successor and cannot reduce either scope's burden.
