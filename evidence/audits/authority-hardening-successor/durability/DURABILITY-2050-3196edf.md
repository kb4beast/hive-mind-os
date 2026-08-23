# DURABILITY-2050 Steward receipt

- Candidate commit: `3196edf00cdbb8e52388b8a98afabc8bfb833cad`
- Candidate tree: `36f477e03a803286e300e73e0d1daa88d35fbe5a`
- Steward identity: `steward_durability_audit` (independent and read-only)
- Disposition: **ADAPT — accept local durable recovery; defer external-root custody**

## Reproduction

With inherited `GIT_*` variables removed and `PYTHONPATH=src`, the independent
Steward ran:

```powershell
python -m unittest tests.test_mission_store tests.test_hive_cortex_durability -v
```

It passed **87 tests in 534.770 seconds**: 66 MissionStore recovery cases and 21
kernel-durability cases. The candidate paths were unchanged afterwards.

## Local evidence adopted

- WAL-backed durable intents; atomic, fsync-backed receipt writes; and canonical
  digest/idempotency validation.
- All 54 before/after intent/effect interruption cases resume without duplicate
  adoption.
- Append-only kernel-event replay, snapshot-corruption recovery, write-ahead outbox
  intent, authoritative reconciliation witness, and crash/lease recovery.
- Ambiguous external outcomes never blind-retry; they remain reconciliation-required.

## Dissent retained

The registry root, revocations, grant-ledger anchor, and issuance state are still
in-memory/process-local. There is no production root/ledger anchoring path, external
signer/verifier, custody, rotation/revocation policy, or recovery authority. Local
hashes demonstrate integrity records, not external authorship. An ambiguous remote
effect can safely wedge awaiting reconciliation but cannot prove liveness or absence.

This receipt unblocks scoped local Curator/Judge work only. It does **not** complete
`ROOT-3000` or permit `PROMOTION-3990`.
