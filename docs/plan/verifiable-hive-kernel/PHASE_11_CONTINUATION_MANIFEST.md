# Verifiable Hive Kernel: Phase 11 continuation manifest

- **Date:** 2026-08-08
- **Governing phase:** Phase 11 — compatibility migration and convergence.
- **Authorization:** the repository owner, acting as designated Judge, authorized a
  Phase 10 `adapt` disposition and local Phase 11 execution on 2026-08-08. See
  `CASE-VHK-P10-LOCAL-COMPATIBILITY-FIREWALL.md` and
  `CASE-P10G-WINDOWS-SANDBOX-LIVENESS.md`.
- **Base and candidate:** `becd317a8105da7c711315bbee8c0e32e60d1046`; commit tree
  `211521a44bea52da1f1ab3d85a157f9d8666f759`; worktree was clean before this
  manifest.

## Governing sources and boundaries

1. `AGENTS.md`
2. `prompts/phase10_to_phase12_autonomous_handoff.txt`
3. `docs/architecture/HUMAN_AUTHORITY_GATES.md`
4. `docs/plan/HIVE_MIND_OS_VERIFIABLE_HIVE_KERNEL_STANDALONE_HANDOFF.md`, Phase 11
5. `evidence/courts/CASE-VHK-P10-LOCAL-COMPATIBILITY-FIREWALL.md`
6. `evidence/courts/CASE-P10G-WINDOWS-SANDBOX-LIVENESS.md`

Allowed candidate paths are a narrowly selected legacy route and its kernel adapter,
its parity/migration/rollback tests, the Phase 11 migration map and evidence records,
and additive CLI/documentation wiring. Legacy state must remain readable; no old database
is mutated in place, no provider/network/Git effect is introduced, and no historical
receipt is changed.

## Roles and authority

| Role | Identity/control fact |
| --- | --- |
| Owner/Judge | Interactive user directive; declared authority for this local `adapt` disposition. |
| Orchestrator, Architect, Builder, Curator, Integrator, Steward, Optimizer | Procedurally separated local agent roles; not externally authenticated identities. |
| Expert Windows witness | Still absent for separate-control/hard-isolation claims. |

## Active gates, rollback, and verification

The current disposition is `adapt`; Phase 11 is eligible for local reversible work.
G1 is resolved. G2 (real model), G3 (external signing), G4 (external retention), G5
(production), G6 (comparator execution), G7 (source licensing), and general G8
(independent-human promotion) remain blocked or ungranted. Phase 11 must not claim any
of them resolved.

Rollback keeps the legacy route authoritative and removes only the additive adapter and
its migration records. Any created kernel state must use a separate versioned state root;
rollback restores reads to the pre-migration legacy state without deleting it.

Before each route changes, establish a failing parity or rollback regression. Then run the
route's regression, focused kernel/legacy tests, pre-existing retry tests, and finally:

```powershell
python -m unittest discover -s tests -v
```

Required evidence includes a route map, old/new behavior fixture, versioned migration and
rollback receipt, exact candidate/tree digest, command stdout/stderr digests, and an
independent procedural Curator reproduction. A route does not become default until those
artifacts exist.
