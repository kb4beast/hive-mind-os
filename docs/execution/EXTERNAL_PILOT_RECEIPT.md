# N32 two-repository external pilot receipt

Status: `BLOCKED_CAPABILITY`, `BLOCKED_AUTHORITY`, and `BLOCKED_EVIDENCE` --
two candidate repositories are selected; admission is not sealed and the 72-hour
pilot has not started.

## Reconciled observation

- Observed on `2026-09-21` against Hive Mind OS base candidate
  `213392dbf74d879a02fb2c613f809a3eb83cf31b` (tree
  `6a0be6658160b4421eba378c941628b940b68a53`). The N32 scope is adapted by
  ADR-090 to the runtime's existing two-repository `external` mode. Roblox remains a
  separately qualified optional domain and is not claimed by this receipt.
- Coupon Hive is selected at `main@f9b695d90ec74764709a1547d60821910ece5705`
  (tree `9582c2410f20c916b580d7d4704b6263360c0631`). PR #2 is merged and the
  repository records an MIT license.
- Reese's Rainbow Web is selected at PR #1 head
  `fb5d9a84780dd9f6e4c3f46352bdd3beec141d4e` (tree
  `af67971e1b7f9f920a01cc59176435fba142edf9`). Its dependency-free Node tests
  and Chrome playthrough passed during candidate preparation.
- The selected commits and test results are preparation evidence only. They were not
  produced inside a sealed Whole-OS host lease and cannot be relabelled as N32 pilot
  attempts or independently attested runtime receipts.
- The canonical continuation launcher re-observed a quiescent control plane but
  withheld its stale dispatcher release after the GitHub snapshot changed. It
  released no N32 work.

## Typed blocking obligations

1. `missing-whole-os-host` -- attest and seal the configured Whole-OS host used for
   the exact pilot candidate.
2. `missing-delivery-authority` -- issue target-scoped branch, pull-request, cleanup,
   and rollback grants for both repositories. Merge and deployment remain excluded
   unless separately granted.
3. `missing-benchmark-candidate` -- independently admit an exact N30 candidate before
   the pilot starts.
4. `missing-targets` -- seal host-issued target receipts for both selected commit/tree
   pairs, including owner goal, acceptance profile, runtime, rights, and isolation.
5. `missing-runtime-evidence` -- reproduce both targets from clean checkouts on the
   admitted host and retain independently verified runtime receipts.
6. `BLOCKED_EVIDENCE:OBSERVATION_WINDOW` -- after every prerequisite predates the
   start timestamp, complete the real 72-hour two-tenant observation, restart case,
   rollback evidence, and accepted changes covering both targets.

The target candidates are concrete and Roblox is no longer an N32 prerequisite.
Production, superiority, general hostile-repository support, public deployment, and
the elapsed pilot are not claimed. Resume by sealing the host, target, authority,
runtime, and N30 receipts, then invoke the committed N32 launcher. No checked-in note,
ambient credential, prior manual PR, or synthetic fixture can manufacture those
receipts.
