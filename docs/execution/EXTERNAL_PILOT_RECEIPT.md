# N32 two-repository external pilot receipt

Claim scope: `bounded-operational-production-pilot`. The alternative
`full-autonomy-or-superiority` scope additionally requires N30/N31.

Status: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, `BLOCKED_AUTHORITY`, and
`BLOCKED_EVIDENCE` -- two candidate repositories are selected; the successor
production candidate and admission are not sealed, and the 72-hour pilot has not
started.

## Reconciled observation

- Reconciled on `2026-09-21` against merged Hive Mind OS
  `main@ed96ffde57304d6b1ab7923e4d219640ac96b44f` (tree
  `34f0332108193851117e159b200c30bacfdbe1e8`). ADR-090 adapts N32 to the
  runtime's existing two-repository `external` mode, and ADR-091 separates this
  bounded claim from the N30/N31 full-autonomy path.
  Roblox remains a separately qualified optional domain and is not claimed by this
  receipt.
- Coupon Hive is selected at `main@f9b695d90ec74764709a1547d60821910ece5705`
  (tree `9582c2410f20c916b580d7d4704b6263360c0631`). PR #2 is merged and the
  repository records an MIT license.
- Reese's Rainbow Web is selected at
  `main@44b22e5f88a3f3a9e6656a48cea7787c5d20ab4e` (tree
  `af67971e1b7f9f920a01cc59176435fba142edf9`), the merge commit for PR #1.
  Its tree is identical to the reviewed PR head
  `fb5d9a84780dd9f6e4c3f46352bdd3beec141d4e`; its dependency-free Node tests
  and Chrome playthrough passed during candidate preparation.
- The selected commits and test results are preparation evidence only. They were not
  produced inside a sealed Whole-OS host lease and cannot be relabelled as N32 pilot
  attempts or independently attested runtime receipts.
- The canonical continuation launcher re-observed a quiescent control plane but
  withheld its stale dispatcher release after the GitHub snapshot changed. It
  released no N32 work.
- A real trusted-host bootstrap completed for exact clean baseline `ed96ffde` with
  distinct Curator and Builder sessions and 16 passing focused tests. Receipt:
  `%LOCALAPPDATA%\HiveMindOS\whole-os-codex-host-ed96ffde\startup-receipts\20260921T230947644290Z-b23f561d.json`;
  SHA-256 `fa9df5d1714a8e5fdcb2496e6cf2e68ca7526f55175466bfcb3488773047e8b7`.
  This validates the trusted local host for that baseline. It does not qualify a
  later successor candidate or prove hard isolation.
- An exact-baseline N30 attempt returned typed `blocked` before any lane or external
  effect because admission, custody, comparator, rights, manifest, signature, and
  lease inputs were absent. ADR-091 retains that blocker only for the full scope.

## Typed blocking obligations

1. `missing-production-candidate` -- independently qualify and seal the exact
   post-merge candidate that will enter the pilot.
2. `missing-whole-os-host` -- rerun and seal the configured Whole-OS host for that
   exact successor candidate; the baseline host receipt cannot be replayed.
3. `missing-delivery-authority` -- issue target-scoped branch, pull-request, cleanup,
   and rollback grants for both repositories. Merge and deployment remain excluded
   unless separately granted.
4. `missing-targets` -- seal host-issued target receipts for both selected commit/tree
   pairs, including owner goal, acceptance profile, runtime, rights, and isolation.
5. `missing-runtime-evidence` -- reproduce both targets from clean checkouts on the
   admitted host and retain independently verified runtime receipts.
6. `BLOCKED_EVIDENCE:OBSERVATION_WINDOW` -- after every prerequisite predates the
   start timestamp, complete the real 72-hour two-tenant observation, restart case,
   rollback evidence, and accepted changes covering both targets.

For `full-autonomy-or-superiority` only, `missing-benchmark-candidate` and the N31
self-pilot also remain blocking inputs. They are not prerequisites for this bounded
pilot.

The target candidates are concrete and Roblox is no longer an N32 prerequisite.
Bounded production still requires exact candidate, host, authority, target/runtime,
72-hour observation, restart, and rollback receipts; full scope also requires N30/N31.
Production, superiority, general hostile-repository support, public deployment, and
the elapsed pilot are not claimed. Resume by sealing the host, target, authority,
runtime, 72-hour observation, and rollback receipts, then invoke the scoped N32
launcher. For the full scope, also seal N30 and N31. No checked-in note,
ambient credential, prior manual PR, or synthetic fixture can manufacture those
receipts.
