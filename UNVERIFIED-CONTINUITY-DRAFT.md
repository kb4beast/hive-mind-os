# UNVERIFIED continuity-controller draft

This is a local draft implementation. Its tests have been authored for later
execution. No tests, compilation, Ruff, Pyright, independent review, CI or live
campaign launch have been performed for this draft.

The owner requested direct draft implementation without tournament or courtroom
preimplementation gates. No formal court selection, superiority verdict or
production approval is claimed.

## What is included

- `src/hive_mind_os/campaign_continuity.py`: opt-in bounded campaign-selection and
  restart/reconciliation library; execution belongs to a supplied adapter.
- `tests/test_campaign_continuity.py`: acceptance specifications, **not executed**.
- `docs/architecture/ADR-UNVERIFIED-CAMPAIGN-CONTINUITY.md`: proposed contract,
  threats, compatibility, migration, rollback and remaining validation.
- `docs/architecture/UNVERIFIED-CONTINUITY-MANIFEST.json`: base and artifact digests.

No production entry point enables this library. Existing promotion authentication
and continuation-packet behavior are unchanged. The draft does not supply a real
authority adapter, authenticated journal storage, scheduler, Git publisher or
promotion mechanism.

## Exact starting point

- Worktree: `C:\h\continuity-draft1`.
- Branch: `codex/unverified-campaign-continuity`.
- Base commit: `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`.
- Base tree: `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0`.
- Base delivery: [PR #176](https://github.com/kb4beast/hive-mind-os/pull/176).

GitHub reports that `kb4beast` merged the delivery on 2026-09-13 at 05:22:43 UTC.
The automation did not perform that merge. Delivery qualification is separate
from this draft; passing checks on the base do not validate the new controller.

## Before any activation or publication

Execute focused and full acceptance tests; inspect the implementation and its
failure modes independently; run static/type checks and applicable Linux/Windows
Python versions. Verify every crash boundary, process concurrency, replay and
identity/authority substitution with a real idempotent adapter. Review journal
tampering, storage outages, clock changes and evidence provenance. Record actual
results and unresolved findings before making any verified capability claim.

Rollback is to stop the opt-in caller and preserve its journal and receipts.
Reconcile any in-flight operation through its original adapter before transferring
ownership. Do not erase pending intents to simulate a clean rollback.
