# ARCH-100 architecture contract evidence

The canonical architecture is documented in
`docs/architecture/ADR-055-VERIFIABLE-HIVE-CORTEX.md`; its executable migration
map is `docs/execution/CANONICAL_RUNTIME_MIGRATION_MAP.md`.

Assertions checked by the node:

- `brain_kernel` is the sole authority-bearing event spine for new missions.
- cognition, deterministic control, effects, verification, learning, and
  delivery are separate boundaries.
- `HiveKernel`, `RepositoryMission`, `MissionLoop`, `AutonomousBrain`, and the
  scheduler/worker path have explicit retain/adapt/migrate/retire dispositions.
- migration has no-dual-write, compatibility, replay, shadow, cutover, and
  rollback gates.
- the repository's role-first consultation and anti-cheating rules remain
  normative through the existing control-plane policy.
