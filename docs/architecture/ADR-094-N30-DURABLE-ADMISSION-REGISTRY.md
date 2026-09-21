# ADR-094: Durable host-owned N30 admission registry (SQLite adapter)

- Status: **ADAPT implementation candidate (second Builder revision), reversible.** Not
  adopted, not admitted, not qualified. Independent exact-source Curator reproduction and
  normal CI are required. **Nothing in this revision has been executed by its author** (see
  Honest status).
- Date: 2026-09-21
- Base: `8a9dda3e2a7fce8482d2cdc9b54e1b51212d5553`, branch `codex/n30-durable-registry-20260921`
  (root later propagated only a test/ADR clock-fixture correction, HEAD `c208196`).
- Builder: independent Builder (not Architect, Curator or Judge). Judge: unassigned and
  explicitly not this Builder. No self-adoption.
- Scope: `src/hive_mind_os/n30_host_registry.py`; narrowly shared contracts in
  `campaign_metrics.py` and `benchmark_adapters.py`; N30 tests and synthetic helper; this ADR.
  No broker, launcher, signer, live benchmark, grant, fixture fallback or superiority claim.
- Controlling inputs: the accepted design chain (Architect proposal, Judge conditions 1–6,
  Architect amendment SHA-256 `075048485bda4cf60072403ccc0b4c1ce6dbb8d4b124791b31f742124cd1f396`,
  FINAL Judge `6aac02ec26afefe2700331f26b6fc827f7fd2913f8a5715a1a66f15f8050550c`); the
  independent Curator REMAND (SHA-256 `0d78c7d7bb480e7972a5e25a6ff28d945cacb17ac4e7449c56fb8ff0d60ecbdb`);
  the R3/R4 author amendment (SHA-256 `f90e7267454e1c00c86061ceb814ea0be4ae0598dc263c1b353ac9813fdc78ca`);
  and the CONTROLLING independent Judge ADAPT on it (SHA-256
  `f9de8b0a51665cad5e6ee7f7ec0d3b25d769e0171b5d8adabac942c9dd37a0dd`). Earlier accepted
  design/authority/measurement conditions remain binding. First-run evidence:
  `n30-first-focused.log` (54 tests, 53 pass, 1 error), `n30-first-ruff.log` (1 × E731),
  `n30-first-pyright.log` (10 errors). No full CI pass exists.

## Case and provenance

`campaign_metrics.AdmissionRegistry` defines nine methods and had no production
implementation beyond the in-memory, `id()`-keyed test fixture. This ADR records a durable
implementation of exactly that protocol on standard-library SQLite. The original
implementation was sent back by four independent remands plus first-run failures; this
revision answers all of them together and corrects two claims of the first revision that
were false or overstated (below).

## Curator remand: findings and dispositions

| Finding | Frozen counterexample | Disposition | Where |
| --- | --- | --- | --- |
| **R1** Fresh time reused stale authority: `_recheck` re-sampled the clock but reused `auth.status`; `apply`→`consume_round` (rows 0→2), `record_aggregate` (aggregates 0→1) and `resolve_aggregate` returned positive results after revocation that occurred before the last provider returned. | `probe_boundaries.py` | **Fixed (ADAPT).** Every public call whose result depends on provider dependencies now performs a **final authority read** (`_final_read` → `_authorize`) after the last dependency and *outside* any write transaction (no provider call ever holds the SQLite write lock; `_authorize` opens its own short observation transaction, so it is never nested). Freshly sampled trusted UTC, exact source/evidence binding, generation/clock regression, status freshness and lease expiry are re-validated; `_recheck` then re-validates that read inside the commit transaction. Unknown/unavailable/stale/future/regressed answers raise `AuthorityBlocked`; only a confirmed revocation/expiry raises `LeaseExhausted`, with no consumption, aggregate or positive evidence. Immutable issuance provenance is untouched; only observations are appended. Recovery no longer hands back usable receipts/aggregate receipts under confirmed exhaustion. **No atomicity is claimed for a revocation after the final read.** | `_final_read`, `consume_round`, `record_aggregate`, `resolve_aggregate`, `recover`; `FinalAuthorityReadTests` |
| **R2** Public `schedule` missed exhaustion at an ordinary terminal commit (seven legitimate rounds, then revocation at the `one_survivor` commit → `LeaseExhausted`, no closure). | `late_terminal` probe | **Fixed.** `BracketState.schedule` now wraps the ordinary terminal commit in the same confirmed-exhaustion closure as the rest of the call, so `schedule` and empty `apply` return authenticated `lease_exhausted` closure with counters, quarantine and consumed history unchanged; an existing terminal reason is never relabelled; unknown authority stays an error; nonempty expired `apply` still rejects; a direct inappropriate positive `commit_bracket` is still rejected. The seven-round input is retained as a regression. | `campaign_metrics.BracketState.schedule`; `LateTerminalClosureTests` |
| **R3** The global canonical-digest key change silently changed identity: nonempty inconclusive histories differ old→new in all eight hash seeds (old: two variants; new: one); my first-revision claim of a *behavior-preserving extraction* was **false**. | `probe_lifecycle_digest.py` | **Correct the claim; adopt the Judge's deliberate NARROW VERSIONED codec.** See Digest contract. | `campaign_metrics` codec; `test_n30_bracket_codec.py` |
| **R4** Timeout is bounded waiting, not bounded worker lifetime: `ThreadPoolExecutor.submit` + `Future.result(timeout)`; `cancel` cannot stop a running thread; `close` did not join; four non-daemon threads remained; a noncooperative provider prevents exit. | provider-child probes | **Adopt the Judge's trusted, read-only, self-bounded adapter contract; hard termination is DEFERRED and deployment-blocking.** See Provider lifecycle. | `_call`, `_ProviderCall`, `_StoreGuard`; `test_n30_provider_lifecycle.py` |
| First-run test error (`test_conflict_idempotency_immutable_history_and_audit_only_reads`) | focused log | The control submits direct evaluator outcomes, so it now uses an explicit, truthful **SYNTHETIC** reviewed remit (`outcome_dependency="direct_permitted"`). The production `aggregates_required` gate is untouched and is still exercised by the tests that use the default. | `tests/test_n30_host_registry.py` |
| Ruff E731; ten Pyright errors | static logs | Lambda replaced by `def`. Pyright: real narrowing/validation — `_rowid` (validated `lastrowid`), `_Interner.text_key/bracket_key` (validated handle keys, no casts), `_snapshot` (no `cast` of an optional snapshot), `StatusObservation.revoked_by` (no `cast(int, ...)`), typed `Mapping[str, Any]` status history, distinct names for the two conflicting `chain` variables, and removal of the `type: ignore` lines in reopen verification. No blanket ignore and no `Any` bypass were added. A targeted `# type: ignore[arg-type]` on the `decide_match(registry=self)` call and `cast(Any, …)` in `decode_protocol` predate this revision and were **not** verified removable without running Pyright; they remain and are flagged for the Curator. | module |

## Digest contract (R3): deliberate compatibility break, no migration

**Correction of the first revision.** The first ADR called the digest change an
"extraction … behavior-preserving". That was false. Replacing global mapping-key encoding
changed the identity of every bracket/transition with inconclusive matchups (and the round
plan, issuance, request and audit digests that embed them). This revision:

1. **Restores** the historical global behaviour of `canonical_document`/`canonical_digest`
   (`str(key)`). It makes **no claim** that generic frozenset-key hashing is deterministic —
   `str(frozenset)` follows the per-process hash seed. Every unrelated campaign document keeps
   its legacy digest (asserted against an independent re-implementation of the old function).
2. Defines a **narrow, explicit, versioned bracket representation**
   (`BRACKET_CODEC_ID = "hive-mind-os.bracket-state/v1"`). `BracketSnapshot.to_document()` and
   `BracketTransition.to_document()` emit a domain, a type (`bracket-snapshot` /
   `bracket-transition`), an integer `version`, and inconclusive matchups as sorted, typed
   `{"pair": [a, b], "count": n}` entries with `a < b`. No frozenset ever reaches the general
   canonicalizer as a mapping key, and a JSON-looking string key can never be reinterpreted as a
   pair. SHA-256 and the campaign JSON rules are unchanged; only this preimage is versioned.
3. Uses that one representation everywhere: `bracket_digest` (CAS), plan `bracket_digest`,
   issuance, request digests, audit result digests, the stored bytes and the decoder.
4. **Decoder** `bracket_from_document` is strict: versionless/legacy documents, unknown
   domain/type/version (including boolean/string versions), extra or missing fields,
   duplicate or unsorted entries, malformed pairs, unsorted/duplicate lists and mixed
   representations are refused before any write. The version is never inferred from an empty
   history or from a successful parse. Loading a legacy bracket for positive use **blocks**
   until a reviewed migration exists.
5. **Store binding.** SQLite `user_version`/`meta.schema_version` is now `2` and
   `meta.bracket_codec` must equal the codec id. A schema-1 store (the removed identity), any
   unknown version, or a missing/other codec is refused for operation and never recreated,
   rehashed, aliased or migrated.
6. `legacy_document()` exists on both classes **only** as retained evidence; it is never used
   for identity, storage or decoding.

**Intentional break.** New empty-bracket digests differ from the legacy empty digest because
the domain/version is in the preimage; no covert exception preserves the old empty hash. Old
digests are not aliases. There is **no** automatic migration, guessed `PYTHONHASHSEED`,
in-place rehash or transparent conversion. This is an unreleased adapter: any earlier database
must be retained read-only as evidence and only a separately named synthetic store may be
recreated. If real legacy artifacts must become operational, that needs a separately designed
legacy record type carrying original canonical bytes/digest and append-only conversion
lineage — explicitly deferred.

**Retained losing evidence** (Curator, `lifecycle-digest-results/digest-results.json`): the old
empty digest `c49319d0…50dd` and two seed-dependent old nonempty digests (`cc39e337…9b52` for
hash seeds 0,2,3,7; `4b279028…c540` for seeds 1,4,5,6) are pinned in
`tests/test_n30_bracket_codec.py`. New pinned goldens are deliberately **absent** because they
could not be computed without execution; the tests assert cross-seed stability and difference,
and the first independent run should record the new goldens.

## Provider lifecycle (R4): trusted self-bounded adapters; termination deferred

The three ports are **trusted, read-only, self-bounded adapters**, not sandboxes. Each call
receives the sampled trusted UTC `now`, an **absolute `time.monotonic()` deadline** and finite
`PortLimits(max_bytes, max_rows)`. A reviewed adapter must enforce bounded I/O, cancellation
and prompt release itself and must never call back into the registry, touch SQLite, mutate,
acquire credentials or spawn work. Monotonic time only schedules the call; authority freshness
always uses a **newly sampled trusted UTC time after return**.

- **Qualification is a reviewed pin, not a flag.** `ReviewedMapping` carries
  `adapter_id`, `qualification_ref` and `max_response_bytes`; a port must declare identical
  `adapter_id`/`qualification_ref`. A missing, unqualified or mismatched adapter blocks every
  call (a caller-set `bounded=True` is ignored). The pin references an external qualification
  record; it does not prove boundedness.
- **Shape and size before use/persistence.** Answers must be the exact typed evidence and
  within row/aggregate/issuer counts and the reviewed byte limit (NaN/unencodable answers are
  refused); otherwise `AuthorityBlocked`.
- **One in-flight call per registry, no backlog.** A concurrent submission is refused at once
  (`AuthorityBlocked`); a host sharing an instance across threads must serialize itself. There
  is no executor and no queue.
- **Timeout atomically poisons the instance.** Later submissions and every positive operation
  are refused without reaching the provider; the late answer is discarded even if valid (an
  answer completing after the deadline is treated as late); committed rows, counters and
  history are preserved (negative observations may append under the existing contract).
- **`close()` is idempotent and honest.** It returns `CloseReport` with the outstanding
  provider-call count and poison reason; it never claims a provider stopped. A call in flight
  at close is abandoned (no credit) and handed to the guard.
- **Process-local ownership guard.** A module-level, normalized-alias-aware guard outlives
  every instance: while an abandoned (timed-out or closed-during-call) worker is alive,
  `create/open` of the same store and provider submissions by sibling instances are refused, so
  closing, collection or reopening cannot create a worker farm. The guard is process-local
  only.
- **Non-daemon threads on purpose.** Daemonization or `Future.cancel` is not termination and
  would hide a live worker that may still touch external resources. The original failure is
  therefore **retained as an explicit expected limitation**: a noncooperative provider still
  prevents interpreter exit. `test_noncooperative_provider_still_blocks_process_exit` asserts
  that (the child reaches its end but only the test's own watchdog can end it), and the
  Curator's original result directory is unchanged evidence.

**Deployment blockers (not solved, not weakened):** cross-process custody of a provider, and an
externally supervised process boundary with bounded IPC and verified kill/reap for any
noncooperative provider. The registry gains no broker and issues no admission.

## Architecture (unchanged parts, condensed)

SQLite (WAL, `synchronous=FULL`, foreign keys, bounded busy timeout, `BEGIN IMMEDIATE`) on one
host-owned local filesystem; canonical bytes + source digest; UNIQUE identities and exact-content
idempotency; version/digest CAS; single consumption; hash-chained audit; immutable request
results for authenticated recovery; per-instance interned opaque wrappers; three injected
ports with reviewed mappings; separate immutable issuance provenance and fresh current-use
observations; status-generation/clock-regression rejection; reopen verification of schema,
integrity, digests, references, lineage and audit. Network filesystems, coherent privileged
rollback detection and migrations remain unsupported. Nine-method semantics are as in the first
revision, with the final authority read added for `consume_round`, `record_aggregate` and
`resolve_aggregate`, and confirmed-exhaustion closure across the whole public `schedule`/`apply`.

### Shared-helper contracts and exact coverage

- `campaign_metrics`: `plan_next_round`, `transition_after_round`, `check_seal_append`,
  `build_aggregate_evidence`, `validate_admission_snapshot`, the versioned bracket codec, and
  `BracketState._close_exhausted`. These are **extractions of existing logic plus the
  intentionally versioned bracket identity described above** — not "behavior-preserving" as a
  whole. Coverage: unchanged `tests/test_campaign_metrics.py` (fixture regression oracle),
  the new codec tests, and the N30 conformance tests.
- `benchmark_adapters.build_admitted_invocation` is a **behavior-compatible** extraction from
  `AdmittedBenchmarkRunner.plan` (same checks, same order, same request/binding fields; the
  runner now calls it). Coverage: `tests/test_benchmark_adapters.py` —
  `test_admitted_runner_generates_exact_request_and_reconciles_retry`,
  `test_runner_rejects_unsealed_variant_manifest_drift_and_revoked_lease`,
  `test_runner_requires_execute_operation_and_exact_repetition`,
  `test_runner_revalidates_lease_after_planning_before_broker` — plus the N30 measurement
  tests that call it through `_binding_for`.

## Acceptance, metrics and rollback

Acceptance is executable in `tests/test_n30_host_registry.py`,
`tests/test_n30_host_registry_durability.py`, `tests/test_n30_bracket_codec.py` and
`tests/test_n30_provider_lifecycle.py` (synthetic authority in `tests/n30_synthetic.py`), plus
the unchanged campaign/benchmark suites. New controls: the three frozen R1 paths and every
unknown/unavailable/stale/future/regressed/revoked mode; all direct entries after confirmed
revocation and positive-recovery behaviour; the seven-round late-terminal input through
`schedule` and empty `apply`; pinned legacy goldens, eight-seed new-digest stability,
pair-order/noncollision, unrelated-document equality, strict decoder rejections,
reopen/CAS/receipt lineage (also under different hash seeds), previous-schema/codec/legacy/
unknown/mixed store refusal with no writes; provider qualification pins, response gates,
timeout poison, late answers, single in-flight, close-during-call, same-store and alias reopen
refusal, exceptions, cooperative recovery, and bounded process exit (plus the retained
noncooperative limitation). Passing is storage/contract conformance only.

**Rollback:** disable the adapter and **retain every database and its audit** as evidence. There
is no migration and no automatic conversion. Rollback never selects the in-memory fixture, or
any default registry, for production; `campaign_metrics` still has no minter, key or fallback.
Source rollback is the parent commit; note the bracket identity change is *not* reversible
against a store written by this codec (that store is retained, not read by older code).

## Ownership, roles and stages

Adapter, schema and tests: this Builder until an independent Curator reproduces. Reviewed
mappings, adapter qualification records, metric/gate definitions, freshness limits, outcome
dependency policy and trust pins: the host operator through explicit review. Store custody,
backup and any checkpoint: the host operator. Only the Builder role/`build` stage has evidence
here; Curator reproduction (validate), E1 composition and broker (integrate), store operations
(maintain) and benchmark courts (grow) remain pending. None is claimed.

## External obligations (blocking; none created here)

- **O1 Reviewed N30 mapping:** purposes, field schemas, evaluator remit, trust pins, freshness
  limits, metric units/denominators/gate definition, response byte limits **and a qualified
  adapter identity/qualification record for each port**. None is approved; production use is
  blocked until it is.
- **O2 E1 composition gap:** the intended providers reuse E1's ReceiptStore/verifier/current-
  authority seam, which is absent from this checkout and separately conditioned; only the
  normalized injectable interfaces exist. A reviewed mapping to E1 remains owed. No E1 code was
  imported or copied.
- **O3 Current authority** (independent lease/revocation/status with generations, signed
  StageEvidence/LeaseRecord envelopes), **O4 evaluator/measurement evidence** from a real broker
  (not part of this change), **O5 store custody** (protected storage, backup, an independently
  retained checkpoint if rollback detection is wanted).
- **O6 Provider process custody:** cross-process ownership and an externally supervised
  kill/reap boundary for any noncooperative provider (DEPLOYMENT BLOCKER).
- Also open: comparator rights/bytes, sealed disjoint tasks, bounded lease, protocol closure
  (the checked-in protocol remains OPEN and untouched).

## Residual limits

- **L1** Privileged coherent database rollback is not detected without an external checkpoint.
- **L2** Network filesystems unsupported (only a UNC prefix is mechanically refused).
- **L3** Revocation after the final authority read but before/after commit is not prevented.
- **L4** A noncooperative provider cannot be stopped and blocks interpreter exit; the guard and
  poison contain new work but do not terminate it.
- **L5** The process-local guard does not span processes.
- **L6** Concurrent use of one registry instance is refused rather than queued.
- **L7** Wrapper interning retains strong references for the life of the instance; status and
  audit rows grow with use (no retention policy); `resolve_aggregate` re-authenticates every
  measurement (up to 90 provider calls; `decide_match` costs three passes).
- **L8** New bracket goldens are not pinned (see R3). The lifecycle subprocess tests use
  wall-clock windows and may be timing-sensitive on a loaded host.

## Honest status

The author had no execution tools in this revision (read/glob/grep/edit/write only). **No test,
Ruff or Pyright run has been performed on this revision**; nothing here is claimed to pass. The
two earlier reported runs (54 tests: 53 pass, 1 error; Ruff 1; Pyright 10) are for the *first*
revision and are not evidence for this one. Expect first-run defects, most likely in tests.

## Required verification

```powershell
python -m unittest tests.test_n30_host_registry tests.test_n30_host_registry_durability tests.test_n30_bracket_codec tests.test_n30_provider_lifecycle -v
python -m unittest tests.test_campaign_metrics tests.test_benchmark_adapters -v
python -m unittest discover -s tests -v
ruff check src/hive_mind_os/n30_host_registry.py src/hive_mind_os/campaign_metrics.py src/hive_mind_os/benchmark_adapters.py tests/test_n30_host_registry.py tests/test_n30_host_registry_durability.py tests/test_n30_bracket_codec.py tests/test_n30_provider_lifecycle.py tests/n30_synthetic.py
pyright
```

For the frozen replays: copy the **unchanged** `probe_boundaries.py` and
`probe_lifecycle_digest.py` into a fresh review directory holding the newly sealed snapshot
(`PYTHONPATH=<review>/snapshot/src;<review>/snapshot`). `probe_boundaries.py` should now show
fail-closed behaviour on all four cases. `probe_lifecycle_digest.py` asserts the *old observed*
behaviour (equal empty digest, one new nonempty digest, release exit, noncooperative
watchdog); its empty-digest equality and the old pool-of-four expectations are superseded by
this ADR and must be adapted explicitly, keeping the original script and results as negative
evidence.

## Second Curator remand (`n30-curator-remand1`): two lifecycle races

**Why the previous result was not enough.** Root and the independent Curator both reported
83 focused tests passing (and Ruff/Pyright clean). That did **not** close concurrency: the
suite tested poison, late answers, close and reopen only in sequential orders. The Curator's
`probe_poison_interleavings.py` / `_v2.py` (retained byte-identical, results retained) pause
existing internal seams and found two defects that violated the accepted R4 contract. This
section records the repair. It is **not** a full-CI, delivery, admission or production claim.

- **Repair A (an operation paused before poison committed after it).** Actual public
  `record_aggregate`, paused after the unmodified `_final_read` returned, committed 12
  measurements and 1 aggregate after a second public call timed out and poisoned the same
  instance. An extra early check would not fix that, so poison/close are now **linearized
  with every positive commit and return**:
  - every write transaction takes the instance lifecycle lock (`_state_lock`) *after* it holds
    the SQLite write lock and keeps it from a poison/closed/abandoned check **through COMMIT**
    (fixed order `_lock` → `_state_lock`; the lock is never held while waiting on a provider
    or on SQLite's busy timeout);
  - poison publication and close take the same lock, so poison and a positive commit are
    totally ordered: a commit that started first is linearized before the poison, and any
    transaction that starts later is refused with a typed `AuthorityBlocked`;
  - positive returns that involve no write (`resolve`, `resolve_bracket`, an existing
    `admit`, an idempotent terminal `commit_bracket`, `recover_bracket`, `recover`) are
    linearized at a final `_ensure_live()` check. `open_bracket`, `issue_round`,
    `consume_round`, non-idempotent `commit_bracket`, `append_seals`, `record_aggregate`
    and `resolve_aggregate` are covered by their transactions.
  - A call whose timeout/close decision is already published (`abandoned`) counts as poison
    before the poison text is written.
  Consequences: a *deliberately serialized* concurrent operation on the same instance can
  now get a bounded typed refusal instead of committing (the no-queue contract is unchanged;
  nothing waits on a provider); a poison publisher may wait for one in-flight local
  transaction (bounded by the SQLite write and busy timeout). Independent SQLite connections
  are unaffected: cross-connection CAS/once-only consumption stay in SQLite, and the existing
  two-connection race tests remain meaningful.
- **Repair B (same-store reopen gap).** `_call` released the instance lock after setting
  poison and only then adopted the call into the store guard, so a public same-store `open` +
  `admit` started a second worker while the first timed-out worker was outstanding. Now the
  guard **owns every provider call from before its thread starts** (`_StoreGuard.start` is an
  atomic check-and-own that refuses while any abandoned worker of *any* instance on the
  normalized store is alive), and `abandoned` is a flag the call carries, set under the
  call's lock in the same critical section that decides the timeout or the `close()`. There
  is no instant at which an outstanding worker is invisible to `open` or to another
  instance's submission, including close-during-call and normalized/hard-link aliases.
  The guard entry is released only when the worker actually finishes (never on close or
  collection), so a legitimate fresh reopen after release still works. `adopt` remains as an
  idempotent confirmation only.
- **Tests** (`tests/test_n30_provider_lifecycle.py::PoisonLinearizationTests`) use the
  Curator's unchanged pause points through public APIs with events: `record_aggregate` and
  `consume_round` paused after `_final_read`, five read-only returns paused after
  `_authorize`, and the pre-`adopt` handoff with same-store open (paths, `..` alias, hard link),
  an existing sibling instance and exactly-one-worker accounting; plus close-during-call and
  positive release/reopen controls. All 83 prior tests and the 54 prior names are kept.
  Exact new-codec goldens from `additional-controls/new-codec-goldens.json` are pinned with
  their full preimages in `tests/test_n30_bracket_codec.py`; the original legacy hash
  controls remain.
- **Still unprovided (deployment blockers, unchanged):** cross-process provider custody and an
  externally supervised kill/reap boundary for noncooperative providers; real adapter
  qualification/remit (the local `adapter_id`/`qualification_ref` strings provision none);
  E1 composition; external status/evidence providers; protected storage. This repair claims no
  hard termination, daemon/`Future.cancel` semantics or new broker. **Unrun by its author.**
  Replay `probe_poison_interleavings_v2.py` unchanged against a freshly sealed snapshot: it
  should now show no positive first operation after poison and no second provider/handle
  during the handoff gap (its `open_registry()` in the gap now raises instead of returning,
  which the Curator must read as the repaired outcome, not a harness fault).
