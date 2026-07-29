# Court record: Phase 3 item 5 Obsidian vault refresh

- Case: `P3-OBSIDIAN-REFRESH-001`
- Disposition: pending
- Subject implementation: `ee09e4cb9a4bc5fd0711e738249039507a194e43`
- Runtime: Obsidian Desktop `1.12.7`, Windows `10.0.26200`

## Claims

| Claim | Evidence | Disposition |
|---|---|---|
| Core Obsidian reflects item-1 external replacement in an already-open pane. | Fourth run, count `6 -> 7`, `4.315128s`. | pending |
| Core Obsidian reflects item-3 external replacement in an already-open pane. | Fourth run, total `7 -> 8`, `4.185468s`. | pending |
| Core Bases recomputes after a new generated idea note appears. | Fourth run, `1 -> 2` rows, `8.940211s`. | pending |
| The generated Canvas parses and renders embedded Bases. | Fourth-run Canvas screenshot and preserved target bytes. | pending |
| Generated item-4 bytes remain owned after runtime observation. | Fourth run unloads Canvas, waits at least 300 seconds, preserves both observed targets plus the complete item-4 namespace, and requires final item-4 `unchanged`. | pending |
| The behavior generalizes to other hosts, versions, profiles, Git remotes, or Sync. | No evidence. | defer |

## Advocate

The Explorer and Architect supported a real-projector, disposable-vault black-box
test. The candidate protocol binds visible outcomes to projector timestamps and
hashes and uses no plugin or watcher.

## Cross-examination

The first run disproved the initial integrity claim when Obsidian canonicalized Base
YAML. The second run's immediate check was also insufficient: Obsidian rewrote the
Canvas about four minutes later. The third run passed for its own subject but became
non-promotable when production YAML hardening advanced. All remain append-only
evidence. The fourth run covers the sealed production subject.

Remaining weaknesses:

- the Obsidian process and user profile predated the run;
- no official refresh latency guarantee exists;
- screenshots prove only the recorded host and fixture; and
- `.obsidian` and vault registration are local side effects, not product state.

## Independent roles and judgment

Cross-Examiner, Curator, Steward, Expert Witness, and distinct Judge identities will
be recorded only after the fourth run and final candidate bytes exist. Until then,
judgment is pending and no passing conformance claim is admitted.

The original item-5 byte-freeze instruction conflicts with runtime-discovered Base
and Canvas canonicalization. Any final `adapt` disposition must explicitly authorize
only the minimal serialization changes, preserve the preceding item-4 inventory and
rollback, and reject any semantic, namespace, filter, schema, or authority redesign.
