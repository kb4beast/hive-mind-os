# Multi-Execution Runtime Repair Matrix

Status: implementation baseline, not a promotion receipt.

- Candidate commit: `e57bd586a39056f88e1c08581c66eda8bc8f0686`
- Candidate tree: `1ce053b47bd1a49948144617fa5104e4f5e83ff3`
- Mission source: `pasted-text.txt`, SHA-256 `F2D48BCAF10D82D1EA1249B9BBE485AF9FED17306AA0932E328944869835139F`
- Plan: `hive-mind-os-verifiable-hive-cortex-v1`
- Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`

Relevant implementation hashes at this baseline:

- `controller.py`: `91556ECD992EB955A21CD883BA654F52C4F5BD2EDB70F10E35B8A875805C2EDE`
- `autopilot.py`: `12F2B3C4C8882552A8205EAD7FFDBF96670245CB9A22A2F48B143C0271E1D5EF`
- `host_execution.py`: `28E4511B03B58C38AF39743834FB4B41B71CC51C0C3FAE34F3334B976FD0A2CB`
- `orchestration.py`: `83D2D3020DB73A2186565399C75D081300141C43ACAEDD7D82371DD273E267E2`
- `app_server_host.py`: `902279A2B489F61A06A43132D3AB644AC0EA0442F2F13E6CEF2297069807BD08`
- `execution_supervisor.py`: `A3DDCD9CCB2AC81A3B6E3E7CBEAF3C927D34C18EB2F2BB4E79A296819D5804CD`

## Confirmed and open

1. **Host-kernel writer generation is not sealed.** The canonical per-user host directory has no controller/schema/interpreter generation that fences host-global writes from another repository running different Hive Mind OS bytes. Provider generation covers the App Server provider, not the reducer that mutates capacity, reservation, registry, and provider histories.
2. **Execution-local adapter provenance is not end-to-end.** The App adapter has a full execution-local identity record, but reservations, launch bindings, host-effect events, lifecycle observations, and cross-repository recovery carry only the machine-global provider coordinates. A changed execution config/model/adapter can therefore be substituted within one global provider generation.
3. **Host JSONL authority is not power-loss and reparse safe.** Registry, capacity, provider, and reservation histories use append/read paths without complete Windows link/reparse/open-handle identity enforcement. Torn final records fail-stop without immutable tail evidence and authenticated prefix repair.
4. **Execution-kernel upgrades have no transition.** Runtime identity correctly rejects a different kernel bundle, but no zero-activity, append-only CAS upgrade can move an existing execution namespace to newer trusted bytes. Normal software evolution therefore strands durable frontier state.
5. **Host scheduling is not yet fair across executions.** Per-execution batching is work-conserving and no longer re-releases completed members after a capacity change, but the host kernel has no deterministic weighted/deficit scheduler or typed `WAITING_FOR_CAPACITY` queue across independent executions. The required 13-ready-on-4 and wide-versus-small fairness receipts do not yet exist.
6. **Migration command modes are incomplete.** The crash-resumable semantic legacy reconciliation court and runtime authority migration exist, but the operator surface does not yet provide explicit dry-run, apply, verify, and rollback-before-READY modes over one preserved manifest.
7. **The default Python environment is not authoritative.** `C:\Python314\python.exe` currently imports `hive_mind_os` from the foreign editable checkout `C:\Users\beesp\.codex\worktrees\1a44\hive-mind-os`. Authoritative tests must use isolated startup and prove the candidate import path before discovery.

8. **Lock ownership is tracked but order is not asserted.** `runtime_file_lock` provides cross-process exclusion and same-thread reentrancy, but at this baseline it does not reject a direct or indirect acquisition that reverses host kernel → repository arbiter → execution → node/effect/binding. The mission explicitly requires runtime inversion rejection, including cleanup and recovery paths.

## Already fixed in current bytes

1. Three-tier host/repository/execution roots, transport-keyed repository registry, checkout adoption, and execution-scoped decision state are implemented.
2. Host-effect recovery uses one canonical reducer; live contention waits/adopts without fencing the valid owner, and ambiguous effects block false quiescence.
3. Optional sidecar capacity shortage records a durable skip instead of aborting unrelated primary work.
4. Snapshot/publication evidence is clone-portable under `refs/heads/hive-mind-evidence`; install rechecks source refs; publication has durable PINNED/VALIDATED/PUBLISHING/PUBLISH_UNKNOWN boundaries and preserves ambiguous effects.
5. Branch-keyed target watermarks retain replayable source evidence and terminal sealing reobserves current remote target truth.
6. Same-policy host-capacity renewal has a crash reducer and authenticates old issuance records through the current renewal lineage.
7. Supervisor journals are plan-bound, public `run` reobserves durable waits, and exact unknown attempts have a reconciliation path.
8. Malformed DAGs fail before admission. Capacity repacking no longer re-releases completed barrier members.
9. Migration separates immutable archive proof from mutable post-READY execution state, and conflicting legacy worktree authority has an executable semantic reconciliation manifest.
10. Generated worker/operator commands carry absolute repository/state/host roots, execution namespace, and authenticated host identity; template bytes are part of the execution kernel bundle.
11. Receipt validation walks the raw linear commit history and rejects add-then-revert scope poisoning.

## Historical or falsified

1. The `knowledge-projection-dag` result (420 pass, 3 skip, 16 timing errors, 439 total) is preserved historical evidence, not validation of this candidate.
2. Prior clone-local publication evidence, CWD-filtered false absence, sidecar self-fencing, weak duplicated host-effect parsing, terminal publication omission, and migration whole-file immutability findings are retired at the hashes above.
3. Seven repository-local attended `BOUND` rows are stale legacy records, not proof that seven external Codex sessions are live. No authoritative process/session API currently proves the exact number of live external chats.
4. Runtime slot count and a frontier wider than capacity are resource observations, not integrity failures or external-authority blockers.

## Requires external authority

1. **Crash-exact fresh task creation.** Installed Codex App Server `thread/start` exposes no atomic caller idempotency token or durable absence/tombstone proof. The adapter therefore honestly advertises `autonomous_launch=false`. Repository code can safely adopt an exact observed singleton, but cannot prove that retry-on-absence will not duplicate a task. A provider/protocol upgrade or separately fenced exact-create launcher is required.
2. **Adversarial publication-test isolation.** The current Windows host cannot independently attest that candidate tests have no network, ambient credentials, or access to the authoritative repository/runtime. The validation broker correctly fails closed. Promotion requires an externally enforceable sandbox/container/OS identity boundary; weakening the broker is not an acceptable repository-local alternative.

No item moves categories without a new exact file hash and an executable receipt.
