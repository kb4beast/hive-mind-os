# Multi-Execution Runtime Repair Matrix

Status: immutable implementation candidate pending final verification and promotion.

- Preservation baseline commit: `e57bd586a39056f88e1c08581c66eda8bc8f0686`
- Preservation baseline tree: `1ce053b47bd1a49948144617fa5104e4f5e83ff3`
- Implementation commit: `4bdb82f0fed40661f65cd5dba127bf071b28e25d`
- Implementation tree: `8b72b7d057bdc209a2d439d0187556413c862a56`
- Mission source: `pasted-text.txt`, SHA-256 `F2D48BCAF10D82D1EA1249B9BBE485AF9FED17306AA0932E328944869835139F`
- Plan: `hive-mind-os-verifiable-hive-cortex-v1`
- Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`

Implementation hashes:

- `controller.py`: `17F23FD82A754E8E9F5914E43B2E1F8BD1E0DA1535984261F1323C7BF525AA5D`
- `autopilot.py`: `7FFF44B917CFF8E20C616577FD181440FE343893829C38180BD9B87E52D73F2E`
- `host_execution.py`: `046449420E79926D89DD35208FEF49E754E4C9F7E29E4BD403E0AB552CA204CC`
- `orchestration.py`: `872B180C70A5F44D2F5192E2EFDD6C2B50F0325DD1F08154C834B7CE962C21B6`
- `host_scheduler.py`: `665568777AD4700213692A5689A32C99AA69A2A4AE4FE4242FA0E01FFEE8DFEC`
- `app_server_host.py`: `902279A2B489F61A06A43132D3AB644AC0EA0442F2F13E6CEF2297069807BD08`
- `execution_supervisor.py`: `F5BE9132418616B86B8D93699C54CEB8C71A85194B66D256F29CB86FCA10F096`

## Confirmed and open

No repository-local defect in the confirmed repair matrix remains open at the
implementation commit. The two unavailable authorities below deliberately keep
fresh autonomous launch and adversarial private publication fail-closed.

## Already fixed in current bytes

1. The per-user host kernel now has one append-only writer generation, immutable
   provider attestations, strict capacity/reservation histories, zero-activity
   upgrade CAS, loaded-code fencing, Windows link/reparse-safe authority I/O, and
   content-addressed torn-tail recovery.
2. Repository authority is keyed by authenticated Git transport, shared across
   linked worktrees, branch-keyed for target watermarks, and backed by replayable
   snapshot/publication transition evidence. Private evidence uses compact
   `refs/heads/hme/{s,b,t,p}/<digest>` refs that survive the originating clone.
3. Execution identity and every mutable DAG ledger are namespace-isolated and
   plan/kernel bound. Execution-kernel upgrades require an append-only, zero-activity
   transition; terminal execution fences do not block a new independent execution.
4. The host scheduler has typed durable DEMAND/SCHEDULE/GRANT/EXPIRY events,
   deterministic weighted round-robin, single-use grant capabilities, and a public
   `WAITING_FOR_CAPACITY` observation. A 13-node barrier progresses at capacity four
   while downstream barriers remain closed and a small peer execution is not starved.
5. PRIMARY, SIDECAR, VALIDATION, and host-effect authority binds the exact host-kernel
   generation, capacity lineage, provider attestation, execution-adapter identity,
   repository transport, execution namespace, and immutable terminal/recovery evidence.
6. Lock acquisition is asserted at runtime in the canonical order: outer
   snapshot/supervisor coordinator, host, bootstrap, repository arbiter, execution
   dispatcher, then binding/sidecar/claim/validation/attended leaves. Direct and
   indirect inversions fail before mutation.
7. Same-policy capacity renewal is crash-reduced across history, current-record,
   and per-permit cuts. Expired validation and never-launched permits require typed
   evidence; ambiguous external effects stay charged as reconciliation obligations.
8. Supervisor journals are plan-bound. Public `run` reobserves authenticated durable
   waits, repairs an exact expired validation lease once, and reconciles unknown
   attempts without replaying a completed external effect.
9. Snapshot install freshly reobserves target and every source ref before the final
   CAS. Publication enforces PREPARED -> PINNED -> VALIDATED -> PUBLISHING, preserves
   ambiguous outcomes, and never admits a second publisher over an unresolved effect.
10. Migration exposes idempotent `dry-run`, `apply`, `verify`, and
    `rollback-before-ready` modes. Rollback is intentionally abort-and-preserve:
    append-only fenced/quarantined legacy authority is never unsafely reactivated.
    Archive and retired-evidence layouts use bounded digest components, retain the
    full identities in their sealed manifests, and reject any compact-path collision.
11. Generated commands and all governed prompt templates carry absolute repository,
    state, host-runtime, namespace, plan, and host coordinates. Healing and snapshot
    child processes authenticate the returned execution identity.
12. Hermetic validation detects foreign editable imports before discovery, records a
    new immutable receipt for a changed test vector, and classifies bounded timing
    exhaustion without erasing authenticated progress.
13. Receipt validation walks every raw commit edge from claim to final commit and
    rejects nonlinear, replacement/graft, out-of-scope, and add-then-revert history.

## Historical or falsified

1. The `knowledge-projection-dag` result (420 pass, 3 skip, 16 timing errors,
   439 total) remains preserved historical evidence; it is not a receipt for this
   candidate and no completed shard was replayed.
2. The foreign editable checkout, stale sealed test counts, clone-local evidence,
   CWD-filtered false absence, sidecar self-fencing, default-namespace child commands,
   and whole-file migration immutability were real historical failures but are not
   present in the hashes above.
3. Legacy attended `BOUND` rows are not evidence of live App Server threads. Exact
   thread/effect identifiers and immutable lifecycle evidence, not list absence or a
   working-directory filter, govern recovery.
4. Runtime slot count, a frontier wider than capacity, and timing-budget exhaustion
   are resource observations, not integrity failures or external-authority blockers.

## Requires external authority

1. **Crash-exact fresh task creation.** Installed Codex App Server `thread/start`
   exposes no atomic caller idempotency token or durable absence/tombstone proof. The
   adapter therefore advertises `autonomous_launch=false`. Repository code can adopt
   an exact observed singleton but cannot prove retry-on-absence will not duplicate a
   task. A provider/protocol upgrade or separately fenced exact-create launcher is
   required.
2. **Adversarial publication-test isolation.** The current Windows host cannot
   independently attest that candidate tests have no network, ambient credentials,
   or access to authoritative repository/runtime paths. The validation broker fails
   closed before minting `VALIDATED`. Promotion needs an externally enforced
   sandbox/container/OS-identity boundary; weakening the broker is not acceptable.

No finding moves category without a new exact file hash and executable receipt.
