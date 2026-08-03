# Phase 5L debt reconciliation audit ledger

## Entry 1 — frozen inputs

- Release subject: `0ff332249e7830464724ca9b5a0ebcc6fc43c741`.
- Source registers: `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md` and
  `docs/plan/PHASE5J_CARRIED_FORWARD_DEBT.md`.
- Historical debt rows, adverse runs, packet snapshots, and active lists are preserved.
- Reconciliation is additive and carries no runtime, provider, tool, scheduler, store, authority,
  activation, adoption, or release binding.

## Entry 2 — evidence dispositions

- Stabilization commit `af9ac00a5959b96260fb3bcdfb0958ce0640ae04` and runs
  `30771264748`/`30771265827` support `P5D-DEBT-01`, `-02`, and `-04`.
- Worker repair commit `8ede2414f45210b3b6139850d7d0578e080a08d9`, its receipts, and failed
  PR #64 run `30772864947` remain preserved. Refined successor
  `349f717aaee0deb3b65ab761e16307ca48ad57db`, 100 consecutive local repetitions, and exact-head
  runs `30773159161`/`30773160521` support `P5D-DEBT-03` closure.
- Exact release runs `30772648692`/`30772650299` support `P5D-DEBT-05` and the five
  integrated-validation debt exits.
- Result: 10 resolved and 25 active; the partition is machine checked and digest bound.

## Entry 3 — dissent and limits

- Hosted Linux success does not satisfy `B-OPS-08`; the failed 946-test Windows result is retained.
- One assistant performed the procedural court roles. Authenticated independence is not claimed.
- No external evidence, trust anchor, signature, retention account, provider authority, deployment
  authority, or permitting disposition was supplied.
- ADR-015 adoption and P14/P20 eligibility remain false.
