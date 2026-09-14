# N32 external and Roblox pilot receipt

Status: `BLOCKED_SOURCE`, `BLOCKED_CAPABILITY`, and `BLOCKED_AUTHORITY` --
admission was attempted; no external pilot was started.

## Reconciled observation

- Observed on `2026-09-14` against candidate
  `428af931342820d8f7350bf0f7664115b6257302` (tree
  `8a3c9f7e08fb182de3eb61451157df6a264de0ef`).
- The canonical continuation launcher reconciled the historical control plane but
  withheld its stale release. It released no N32 work and reported no active host
  binding or validation lease.
- Private repositories visible to the host were not admitted as N32 subjects. An
  ambient authenticated forge session is capability, not target-owner authority.
- A signed Roblox Studio installation was observed. No admitted Roblox project,
  gameplay brief, rights-cleared assets, test universe, runtime account capability,
  Rojo toolchain, multi-client harness, mobile device, or production profile was
  present. Installation discovery is not Studio/game/runtime evidence.
- N30 returned `defer` without running a measured lane because its frozen protocol
  remains `OPEN_EXTERNAL_EVIDENCE_BLOCKED`. N32 therefore has no admissible measured
  candidate.

## Typed blocking obligations

1. `BLOCKED_SOURCE:ORDINARY_TARGET` -- admit a non-Hive application with an exact
   owner goal, pinned repository snapshot, acceptance profile, and reuse rights.
2. `BLOCKED_SOURCE:ROBLOX_TARGET` -- admit a rights-cleared Roblox project, gameplay
   brief, assets/licenses, fixtures, and test data.
3. `BLOCKED_CAPABILITY:ROBLOX_RUNTIME` -- supply an attested dedicated Windows Studio
   host, exact toolchain, Roblox Player or multi-client execution, persistence,
   network/security harnesses, and the declared target devices.
4. `BLOCKED_AUTHORITY:TARGET_PROFILES` -- supply host-issued repository profiles,
   brokered account/test-universe capabilities, bounded resource and cleanup leases,
   and scoped code-PR and lessons destinations for both subjects.
5. `BLOCKED_EVIDENCE:N30_CANDIDATE` -- close the frozen tournament inputs and obtain
   a candidate-bound measured disposition before either pilot begins.

External-pilot contracts and tenant boundaries are implemented. Focused static
qualification passed on the exact candidate, but static adapters and mocked tests
are not relabeled as runtime or production evidence. Resume only after the inputs
above are sealed; then run the N27 runtime matrix, the N30 measured tournament, and
the 72-hour two-tenant N32 observation. No branch was pushed, no target PR or lesson
draft was opened, and no external repository, Roblox account, asset, or device was
mutated during this admission attempt.
