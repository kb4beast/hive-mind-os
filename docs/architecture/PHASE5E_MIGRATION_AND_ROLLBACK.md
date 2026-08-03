# Phase 5E migration and rollback

1. Freeze the existing four-output Integrator intake and its inventory digest.
2. Add future contract inventory, dependency, lineage, adapter, ordering, rollback, and receipt
   outputs under new schema versions; never reinterpret old envelopes.
3. Run old/new compatibility and installed-wheel checks before any consumer migration.
4. Keep activation, external calls, and release authority false throughout migration.
5. Roll back by reverting the additive version and restoring consumers to the frozen intake.

No migration was executed by this record. Unknown compatibility, licensing, and authority evidence
remain release-blocking.
