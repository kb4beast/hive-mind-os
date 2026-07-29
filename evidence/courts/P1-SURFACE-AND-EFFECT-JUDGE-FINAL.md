# Phase 1 Surface and Effect Final Judge Disposition

- Judge identity: `/root/phase1_judge`
- Repaired candidate commit:
  `2585e112e0e6876ff70124b65e8cb5fd70670059`
- Supersedes for publication eligibility:
  `evidence/courts/P1-SURFACE-AND-EFFECT-JUDGE.md`
- Case:
  `evidence/courts/P1-SURFACE-AND-EFFECT-COMPLETENESS.md`
- Decided: 2026-07-28

This disposition does not erase the earlier judgment or the later adverse
GitHub evidence. It decides only whether the repaired candidate renews
eligibility for stacked draft publication.

## Disposition

- Stacked draft publication: `adapt`
- Public-signature obligation:
  `adapt — remains closed within declared scope`
- Machine writer/event obligation:
  `adapt — remains closed within declared scope`
- Exact-head green delivery: `defer pending a new GitHub run`
- Phase 1 completion: `defer`
- ADR-018/019/020 adoption: `defer`
- Source admission: `defer`
- Phase 2 implementation, host support, and superiority claims: `defer`

The Python 3.11 enum repair is justified. `inspect.signature(EnumClass)`
exposed incompatible interpreter implementation signatures: seven metaclass
construction parameters on Python 3.11 and `(*values)` on Python 3.12 and
3.14. The supported portable behavior is enum value lookup, recorded as
`enum-value-lookup(value)`. Canonical enum member names and values remain
separately frozen. Generation zero currently has no enum aliases; the artifact
does not claim alias-inclusive `__members__` coverage.

## Independently reproduced evidence

- Candidate:
  `2585e112e0e6876ff70124b65e8cb5fd70670059`
- Python 3.11, 3.12, and 3.14 focused characterization:
  4 of 4 passed on each interpreter.
- All three interpreters produced structurally identical, byte-exact
  artifacts and passed JSON round-trip.
- Inventory digest:
  `sha256:57ad3e54934f2f1315f71e1d994253ce5d9100e2f161d430354039592e6ec037`
- Scanner SHA-256:
  `c4459820703dd34cad67ea1351c97c73965b1402dae909437078bc1561f3e0dd`
- Artifact SHA-256:
  `2977cc4e7f2b30b63c5dcf55d3d86cd3a1f648049d8872f1a599131899d48919`
- Test SHA-256:
  `385590b0debb572e3575533632e94ca9784ca6c003a10707adc260abfabb3163`
- Fixture SHA-256:
  `b679d4dd105df0a4efdd6cbf79b86d2a4aa1ca6255f36982d6a40004d58dd407`
- Ruff passed.
- Pyright over `src`, the scanner, and the characterization test reported
  0 errors and 0 warnings.
- Counts remain 48 sinks, 53 producers, 47 literal event types, 224 bounded
  effect sites, and zero unknowns under the published static rules.
- No `src/hive_mind_os` production source changed.

## Preserved adverse evidence and publication condition

GitHub run `30415956672`, Python 3.11 job `90462402862`, failed exact evidence
head `784264b49e1bf14ad6c9e76cb0d736db209200ca`. All 423 pre-existing tests
passed; only the new inventory comparison failed. Python 3.12, Python 3.14,
security, static, dependency, secret, and provenance jobs passed.

That failure remands the earlier green-publication expectation; it is not
erased by local repair. The repaired candidate may update only the existing
stacked draft. Green delivery requires a fresh exact-head GitHub matrix that
includes Python 3.11.

Any material change to the scanner, generated artifact, fixture, test, or
characterized production source requires fresh independent review.

## Dissent, rollback, and appeal

Static matching does not prove arbitrary Python or operating-system effects.
Aliases, reflection, generated or native code, subprocess behavior, adapter
semantics, and unlisted sinks can evade the registry. All governance, Windows,
source, privacy, architecture, migration, concurrency, and recovery blockers
remain open.

Rollback removes the additive scanner, generated artifact, fixture-v2 link,
tests, and characterization records without changing production state.

This is a new-evidence disposition, not an appeal. Any appeal requires a
different Appeals Judge identity.
