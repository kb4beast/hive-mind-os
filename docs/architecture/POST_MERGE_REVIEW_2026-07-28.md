# Consolidated Post-Merge Review — 2026-07-28

## Boundary

- Exact reviewed `main`: `ac906dbb02c6620936fa439a1811de75e2ccf33c`
- Included merge commits, in order:
  - P07 / PR #18: `e231f546ccee8d1a698941d0cfd8dc32c7cf3e51`
  - P08 / PR #17: `17b1832ca3c6274f92c3c97e762f6405aef5336d`
  - P09 / PR #16: `b6adc8d3c9a161bfc25120c9484064f1cc81eccc`
  - P12 / PR #15: `f9a88b8616eb5fa7426a362bf9ffc11be618c359`
  - P13 / PR #19: `ac906dbb02c6620936fa439a1811de75e2ccf33c`
- Local consolidated gate: Ruff passed; Pyright reported zero errors, warnings, or
  information findings; pytest passed 320 tests with 2 skips and 1,744 subtests.

## Independent dispositions

- Curator: **BLOCK**. The committed P13 `raw-results.jsonl` digest matched the Git blob,
  but a clean Windows checkout rewrote LF to CRLF because benchmark evidence lacked a
  byte-preserving attribute. The Curator also identified stale P08 and remote-protection
  truth records. All other focused integrity, source-block, dissent, and phase checks
  passed.
- Judge: **adapt — PERMIT** continued safe phased work, conditioned on reconciling P08's
  stale blocker and ADR status. The permit explicitly excluded production, release,
  superiority, source-completeness, authenticated-independence, and deployment claims.
- Orchestrator: **PERMIT** continued phased work. P10 and P11 are dependency-unblocked,
  but both integrate with `src/hive_mind_os/cli.py`; merge P10 first and update P11 once.
  The Orchestrator also identified duplicate ADR numbers, stale completed-phase blockers,
  and the inaccurate four-track/no-conflict wording.

The Curator's reproduced byte-integrity counterexample controls delivery of the reviewed
boundary. The other permits remain preserved as dissent about severity and sequencing;
they do not erase the block.

## Batched repair

The follow-up repair:

1. marks `evidence/benchmarks/**` as byte-preserved and non-diffable;
2. adds a regression binding checked-out raw bytes to both `summary.json` and
   `verdict.json`;
3. reconciles P05, P06, P07, and P08 truth records while retaining narrower external,
   distributed, production, and identity blockers;
4. adds a qualified ADR registry without renaming historical evidence paths; and
5. corrects track-count and file-overlap sequencing language.

This record and the repair do not authorize release readiness, production operation,
source completeness, authenticated independence, hostile-code isolation, or superiority.
