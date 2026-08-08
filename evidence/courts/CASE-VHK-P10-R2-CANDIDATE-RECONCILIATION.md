# Phase 10 r2 candidate reconciliation

- **Date:** 2026-08-08
- **Scope:** local Phase 10 evidence reconciliation only; no runtime or court disposition
  change.
- **Terminal state:** `COURT_DISPOSED_DEFER`; `phase_11_authorized: false`.

## Frozen candidate

The retained reproduction packet is
`C:\Repos\HiveMind\phase10-candidate-20260808-r2.zip`, with SHA-256
`0d7fcc0c1fd0a7050d135497b589e1f435bf23b18de6e90d03bc8c6b4dacbf01`.
Its manifest binds base commit
`7c027df5e553cad086dbf432720b71fb28c740b2`, 25 overlay files, and required
reference `refs/tags/archive/evidence-corpus-2026-08-03`. That reference currently
peels to `489fe2da2f986e9e488dce1568a3e4941c42b2be`.

The current `HEAD` is the same base commit. Of the packet's 25 overlay files, 22
match the current bytes, including every Phase 10 executable source and test file.
The packet therefore remains a valid technical exhibit for its frozen candidate; it
is not silently reclassified as a receipt for the current uncommitted worktree.

## Post-packet supplements

The following three tracked Phase 10 records were supplemented after r2. Their
current bytes and the r2-manifest bytes differ; the differences record the retained
human-run Windows reproduction exhibit and its limitations, not a runtime change.

| Path | r2 SHA-256 | Current SHA-256 |
| --- | --- | --- |
| `docs/plan/verifiable-hive-kernel/PHASE_10_LOCAL_COMPATIBILITY_FIREWALL.md` | `ab63a5e8a2bf77d43912f86faa8958d0eb52682699016dbf2decc320c62c9983` | `a0aec40f9ccceb7c4ca7a7be0d06b87a2b91d742d912b222a3d49371cadb226a` |
| `evidence/courts/CASE-P10G-WINDOWS-SANDBOX-LIVENESS.md` | `cd04805d5c7b37e4ef7037cad892d6305671e776c55ef8b34dbf7418769e220c` | `6b6ce43b7ed9988ffaca9c9c4a83c9f2dd95255aa844c91c4a3b4e943c41744d` |
| `evidence/courts/CASE-VHK-P10-LOCAL-COMPATIBILITY-FIREWALL.md` | `ba1b30b443d53047732b4bffc555c8aebd4e75528b7c78c91616ee4b6e204ce0` | `8d37a78fb8abf0aa129bf07cbfac3c571569173064bb26cd14819de8c88cd345` |

`prompts/phase10_to_phase12_autonomous_handoff.txt` is an additional, out-of-packet
continuation brief (SHA-256
`01cb1062e35911894c43bd0973ea293129f279f4f6101c2cfba87907831f2ffa`). It is not
part of the frozen candidate and cannot change a court disposition.

## Current technical check and authority boundary

On the current source tree, the focused command
`C:\Repos\HiveMind\hive-mind-os\.venv\Scripts\python.exe -m unittest
tests.test_brain_kernel_compatibility tests.test_brain_kernel_closeout
tests.test_sandbox -v` passed 32 tests with one expected POSIX-only skip. This is
same-control deterministic technical evidence only.

The P10 and P10.G Judges remain at `defer`. The retained Windows receipt does not
establish separately controlled execution or an authenticated witness, and no distinct
Judge disposition has changed the result to `adopt` or `adapt`. Under
`HUMAN_AUTHORITY_GATES.md` G8 and the Phase 10 continuation brief, Phase 11 remains
ineligible. No Phase 11 or Phase 12 implementation action is authorized by this record.

## Next eligible action

Retain this reconciliation beside r2. A separately controlled Windows witness must
provide an attested control boundary and complete transcript for the frozen candidate;
a distinct Judge may then assess the two Phase 10 cases. Reissuing r2 or changing its
historical bytes is not authorized by this reconciliation.
