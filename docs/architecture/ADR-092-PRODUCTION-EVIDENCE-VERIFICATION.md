# ADR-092: Production evidence verification boundary

## Status

Adapted implementation candidate for a narrowed, verification-only slice. It is
reversible code preparation, not an admission, a pilot, a delivery, a custody claim or a
production verdict. **Every test named here is UNRUN by the Builder** (no execution was
available); the parent must run them and a separate Curator must reproduce the claims.
No superiority claim is made.

The design court is preserved outside the repository under
`production-closeout-20260920/` (`production-evidence-boundary-proposal.md`,
`production-evidence-design-judge-review.md`,
`production-evidence-design-author-response.md`, and the controlling
`production-evidence-design-appeal-judge.md`, SHA-256
`f8536d1b4839540fca0ce9012b700ac10bc2619cfbee8fa84da3a6da23555622`, verdict ADAPT,
narrowed). Where the proposal differs from the appeal, the appeal controls. The reviewed
source was `1373d13`; this branch is based on `8a9dda3`, which differs only in worker-test
cleanup.

## Originating claims and dispositions

| Claim | Disposition | Where it lands |
| --- | --- | --- |
| Label enums (`EvidenceKind`) are not authority; a fake `EXTERNAL_RECEIPT` satisfies structural readiness | adapt | receipts are resolved from bytes; labels are ignored except that `SYNTHETIC` is refused |
| Guards must be composition, not convention | adapt | mode fixed at controller construction; guards inside `begin_attempt`, `complete_attempt`, `record_attempt`, `record_controls`, `record_observation`, `report` |
| Signed-message domain is unseparated | adapt | own kind/schema/`ed25519`, explicit prefix, signature excluded from the preimage, separate verifier instance, keys distinct from promotion pins |
| Administration independence is only strings | adapt | builder/judge/evaluator are configured principals with distinct administration and key digests ("configured separation") |
| One temporal rule for all evidence | adapt | GATE vs RECORD per purpose in a schema table; `observed_at <= issued_at <= now` |
| Payload meaning per purpose | adapt | closed claim schema per purpose; requirement/node/role/stage claims are digest-bound attestations, never proof of truth |
| Final judge and manifest circularity | adapt | detached judgment bound to the recomputed `whole_os_qualification.canonical_digest` |
| Failure after durable begin is unrecoverable | adapt | resolve before begin and again before dispatch; no-effect close only in the runner's own frame; crash recovery is inconclusive |
| Existing seams are narrower than claimed | adapt | `HostLease` named as `host_adapter.HostLease`; H1's `ProfileRegistryAdmission` untouched |
| Bounded fetch, digest before parse, strict JSON | adopt | `PinnedEvidenceResolver` |
| Defer everything until a real issuer exists | reject | dissent preserved: the interface and failure semantics are separable |
| Guards only in the runner and closeout | reject | public bypasses would remain |
| Wait for a full host composition first | reject | would leave label-only acceptance in place meanwhile |

Blocked/deferred (not implemented, not faked): real issuer and key custody, real receipt
storage, the real `HostLease` source and the candidate-to-lease mapping, an archival
status policy, real supervisor and evaluator grants, `HostProfileRegistry` capability
authorization for the actual admitted profile.

## Accepted architecture

One new module, `src/hive_mind_os/production_evidence.py`, and guards in
`pilot_runtime.py`, `pilot_orchestration.py` and `release_closeout.py`. No registry,
signing service, CLI or generic framework; no private-key API.

**Evidence document.** A closed JSON object: `kind` (`hive-production-evidence`),
`schema_version` 1, `algorithm` `ed25519`, `purpose`, `issuer_id`, `key_id`, `subject_id`,
`operation_id`, `candidate_digest`, `observed_at`, `issued_at` (integer UTC seconds;
bool/float rejected), `claims`, `signature`, plus `authority_digest` for pilot purposes.
The signed bytes are `b"hive-mind-os/production-evidence/v1\n"` + the canonical
(sorted, compact, ASCII) payload without `signature`. The signature is checked through a
separate `Ed25519SignatureVerifier` instance holding only evidence pins, using
`PrincipalBinding` stage `receipt` (the promotion stage enum and policy are not changed).
Public keys are stored as raw 32-byte pins; the adapter checks the digest of the actual
bytes. A missing `cryptography` provider is a typed `crypto-unavailable` blocker.

**Digest functions, one per field, never mixed.** Evidence preimage and use/policy
digests: this module's own encoder. Manifest digest: `whole_os_qualification.canonical_digest`
over `{"schema_version": 1, **asdict(manifest)}` excluding `manifest_digest` (never the
kernel encoder, never file bytes). Host lease: `runtime_contracts.canonical_digest` over the
actual `HostLease.to_document()`. Local audit and ledger: the ledger's own function.

**Purpose schema table** (`PURPOSE_SCHEMAS`), each row naming mode, closed claims, window
rule and the issuer roles allowed:

| Purpose(s) | Mode | Window on `observed_at` |
| --- | --- | --- |
| pilot host, supervisor, delivery authority, benchmark, target, runtime capability | GATE | `<= plan.starts_at` (prerequisites may precede the pilot) |
| attempt delivery, attempt runtime | RECORD | `[attempt.started_at, plan.ends_at]` |
| pilot restart, observation | RECORD | `[plan.starts_at, plan.ends_at]` |
| pilot rollback control | RECORD | `<= plan.ends_at` |
| closeout requirement, node, role, stage, startup, rollback | RECORD | `<= issued_at <= now` only |
| closeout judgment | RECORD | `sealed_at <= observed_at <= issued_at <= now` |

GATE purposes carry an explicit per-purpose maximum age in the trust policy (there is no
default, and none of them is the promotion verifier's one hour). RECORD purposes have no
maximum age, so a valid 72-hour historical record and a post-pilot judgment verify, but
their *current status* is still checked. Every use fixes purpose, subject, operation
(attempt id for attempts, pilot id for prerequisites and controls, release id for
closeout), candidate, authority (pilot purposes) and exact claims; a receipt for another
purpose, subject, attempt, candidate, authority or claim set is a `context-mismatch`.

**Resolution order** (`PinnedEvidenceResolver.require`): typed dependency check (trust
policy, receipt store, current authority) → reference and use validation → URI allowlist →
bounded read (`max+1`, oversize rejected) → exact SHA-256 against the reference **before**
JSON → strict parse (UTF-8, duplicate keys, NaN/Infinity and floats rejected, depth 6,
512 nodes) → closed schema → exact use match → configured issuer, key and remit → time
ordering and window → GATE age → Ed25519 over the prefixed preimage → fresh current status.
`CurrentEvidenceStatus` echoes the use digest, issuer, key, receipt digest, policy
generation and (GATE) lease digest, must be no older than the configured status age and not
older than the receipt, and issuer, key and receipt must all be `ACTIVE`. `REVOKED` is
`evidence-revoked`; `RETIRED`, `ROTATED` and `UNKNOWN` block (`status-not-active`) until a
reviewed archival policy exists; the code infers none. Nothing is cached: every public
invocation resolves again, including copied contexts and threads. `EvidenceResolution` is an
audit observation, not a token. `require_all` rejects the same bytes counted twice and one
issuer counted as several witnesses for one use; identical evidence for the identical use
may be revalidated any number of times, and several separately authorized witnesses for one
use remain legal.

**Injected ports.** `ReceiptStore` (a deterministic in-memory conformance adapter ships;
it is not a custody backend), `CurrentEvidenceAuthority` (no shipped implementation; the
tests use a double), `HostLeasePort` (no shipped implementation). Absence of any of them
is a typed blocker: `trust-store-missing`, `receipt-store-missing`,
`current-authority-missing`, `host-lease-mapping-missing`. Lease expiry and validity are
delegated to the current authority, which must echo the lease digest; the pilot candidate
to `HostLease.candidate_*` mapping stays an external, fail-closed binding.

**Pilot guards.** `PilotController(store, plan, production=...)`: the mode is fixed by
construction and is not a request field. `PilotState.evidence_mode` is persisted only as a
consistency check; a missing value loads as `legacy-unspecified` and can never be reopened
as production, and a production state cannot be reopened without its context
(`evidence-mode-mismatch`). Every ordinary public entry re-checks plan and mode.
Prerequisite obligations are re-derived from the frozen plan on each `report()`, so an
edited empty list clears nothing, and every relied-upon receipt is resolved afresh; a
failure becomes a typed obligation (report never raises for evidence failure), so a
blocked report cannot read as positive.

- `begin_attempt` (also its idempotent early return): all prerequisites resolved against
  the actual per-attempt host lease before any durable effect.
- `complete_attempt` / `record_attempt` for `accepted` (also idempotent replay of a
  completed attempt): current prerequisites, the actual lease, the delivery receipt and each
  runtime receipt, bound to the attempt id. Non-accepted closes and records need no live
  admission and no lease.
- `record_controls` / `record_observation`: only evidence being accepted is resolved;
  recording an obligation or counter needs none, so recovery works while the authority is
  down.

**Runner.** `WholeOSPilotRunner.run_once` resolves before `begin_attempt` (inside it) and
again immediately before `service.run_once`. If that recheck fails, only this call frame
knows the service was never called, so it may close the attempt `blocked` without effect.
After the host was called, a failed completion leaves the attempt active. In production,
`reconcile_from_observation` closes any active attempt as `inconclusive` through
`complete_attempt`: no accepted credit, refund or retry, no evaluator call, no service
call (a read-only observation does not prove no effect), no live admission needed
(`PilotRunResult.observation` is `None` on that path). If the real end time falls outside
the plan window, the timestamp is never fabricated or clamped: the attempt stays active and
a typed `pilot-attempt-<id>-unresolved` obligation is recorded
(`pilot-attempt-unresolved-after-window`).

**Closeout.** `verify_production_closeout(manifest, digest, judgment, context)` recomputes
the manifest digest, requires the seal not to be in the future, requires builder and judge
to be configured principals of those roles with distinct administration and key, walks
**every** nested reference (requirement and node assessments including negative
dispositions, roles, stages, startup, rollback) and the detached final judgment, which
binds the manifest digest, release, candidate, previous release, `sealed_at`, disposition
and judge id and must be issued by the sealed judge. `write_verified_release_manifest` and
`load_verified_release_manifest` verify before writing or returning, so the existing-file
fast path cannot bypass. The raw `CloseoutBuilder.seal`, `write_release_manifest` and
`load_release_manifest` remain honest structural views.

**Audit.** Every guarded resolution batch appends a success or failure record to
`QualificationLedger` (scope, context digest, use and resolution digests, blocker). It is
local audit only, not externally signed evidence. Appends are serialized by an in-process
per-path lock; the ledger itself is not redesigned and is not safe across processes. An
unwritable audit record is `audit-unavailable` and yields no positive result; an audit
failure while recording another failure is raised with the original blocker named, never
masked.

## Decisions the Builder made that reviewers should check

- Receipts do not bind a policy digest; the current status binds the policy *generation*.
  Adding an issuer therefore does not invalidate history, but a generation bump requires
  the authority to agree.
- Closeout purposes carry no `authority_digest` (there is no closeout authority to invent).
- The judge's `observed_at` must be `>= sealed_at`, slightly stricter than "signing >=
  sealed_at", because the judgment binds a digest that exists only after sealing.
- A blocked no-effect close keeps the attempt's resource units charged (no refund).
- Local (`production=None`) behavior is unchanged, including `report()` returning the
  persisted obligations. New local states persist `evidence_mode = trusted-local`.
- `PilotRunResult.observation` became nullable to represent the production recovery close.
- `HostProfileRegistry` capability/destination authorization for the admitted profile is
  not implemented here; it belongs to the host composition and remains an obligation.

## Acceptance map

All in `tests/test_production_evidence.py` (real Ed25519, synthetic throwaway keys):

| Acceptance criterion | Test |
| --- | --- |
| Fake `EXTERNAL_RECEIPT`, nonexistent or off-namespace URI, synthetic label | `test_fake_external_receipt_with_valid_labels_and_no_bytes` |
| Tamper, signature, missing prefix, unsigned | `test_tampering_and_signature_failures` |
| Key injection | `test_key_injection_is_rejected` |
| Wrong subject/operation/candidate/authority/purpose/claims/attempt | `test_wrong_context_fields_purpose_and_claims`, `test_forged_cross_attempt_and_wrong_issuer_delivery_receipts_are_refused` |
| Stale, future, ordering, windows, bool/float | `test_time_ordering_windows_and_gate_freshness` |
| 72-hour record outlives freshness; status still current | `test_record_evidence_outlives_freshness_but_status_must_still_be_current` |
| Revoked, retired, rotated, unknown, unavailable, stale, mismatched status | `test_current_status_is_required_exact_active_and_fresh` |
| Bounds, depth, duplicate keys, NaN, unknown fields/schema/purpose | `test_bounds_and_strict_json` |
| Configured identity, administration, key and promotion-pin separation | `test_configured_identity_and_pin_separation`, `test_detached_judge_binding_time_and_configured_separation` |
| Remit and missing dependencies typed | `test_issuer_remit_and_missing_dependencies_are_typed`, `test_missing_trust_store_receipt_store_authority_and_lease_are_typed_blockers` |
| Same-use replay, multiple witnesses, no double counting | `test_same_use_replay_multiple_witnesses_and_no_double_counting`, `test_multiple_witnesses_are_legal_but_one_issuer_is_not_counted_twice` |
| No cross-call, copied-context or thread cache | `test_no_cached_authorization_across_calls_copied_contexts_or_threads` |
| Revocation before dispatch, before completion, on reload, on repeated calls | `test_revocation_between_begin_and_dispatch_closes_blocked_without_effect`, `test_revocation_before_completion_then_recovery_is_inconclusive_without_admission`, `test_reload_and_repeated_public_calls_revalidate_and_never_replay_cached_success`, `test_revocation_and_unavailable_status_fail_each_repeated_verification` |
| Recovery is inconclusive, needs no admission, is never no-effect | `test_revocation_before_completion_then_recovery_is_inconclusive_without_admission`, `test_crash_recovered_attempt_is_never_credited_or_closed_no_effect` |
| No fabricated or clamped end time | `test_recovery_after_the_pilot_window_is_not_clamped_or_fabricated` |
| Mode fixed by construction, checked on every entry, legacy never production | `test_mode_is_fixed_by_construction_and_checked_on_every_entry` |
| Hand-edited obligations do not clear blockers | `test_hand_edited_empty_obligations_do_not_clear_rederived_blockers` |
| Non-accepted records need no admission; accepted needs lease | `test_nonaccepted_records_need_no_admission_or_lease_but_accepted_needs_both` |
| Controls and observation authenticated | `test_controls_and_observation_evidence_are_authenticated` |
| Exact manifest digest (not kernel, not file bytes); post-pilot judge | `test_positive_closeout_after_the_pilot_with_exact_manifest_digest` |
| Every nested closeout reference walked | `test_every_nested_reference_is_walked_including_negative_dispositions` |
| Existing-file and raw-load fast paths cannot bypass | `test_label_only_manifest_is_structurally_valid_but_never_production_positive` |
| Audit fails closed; ledger serialized | `test_unwritable_audit_never_yields_a_positive_result`, `test_concurrent_audit_appends_keep_the_ledger_chain_valid` |
| Lease digest uses `runtime_contracts.canonical_digest`; trusted-local unchanged | `test_accepted_attempt_is_resolved_at_every_boundary`, `test_label_only_prerequisites_never_reach_the_host` (local half) |

The existing pilot and closeout suites are unchanged and must still pass.

## Limitations

- These are in-process checks by trusted host code. A caller holding the interpreter, the
  raw `PilotStore`, `WholeOSService` or `write_release_manifest` is not stopped; external
  host effect leases own authority. This is not arbitrary-Python isolation.
- Revalidation before dispatch is not atomic with the effect.
- A resolution says which bytes were supplied and who signed them, not that the claim is
  true. Configured issuers' remit and real administrative independence are external.
- The conformance store is not custody; the current authority and lease port are absent
  until a host supplies them, so production dispatch and accepted attempts stay blocked.
- Retired, rotated or unknown issuer/key/receipt state blocks even old RECORD evidence.
- A generation change or key rotation needs the external authority to agree; no
  archival effective-time rule exists yet.
- Each `report()` performs one store read and one status call per relied-upon receipt and
  one audit append; it is not designed for high-frequency polling.
- A crash-recovered attempt can never earn accepted credit in production; credit needs a
  new attempt.
- Legacy pilot state cannot be upgraded in place to production.

## Migration and rollback

Additive and default-off. Existing pilots and closeouts are untouched. The persisted
`evidence_mode` key is ignored by older code.

Rollback disables production composition: stop constructing `ProductionEvidenceContext`
in the host and stop invoking production dispatch. That does **not** restore label-only
production acceptance: nothing in this code labels a trusted-local run as production, and
a production-mode state refuses to reopen without its context. If the code itself is
reverted, older code would read a production state's obligations and labels structurally;
therefore quarantine production pilot directories and audit ledgers as historical
artifacts and never treat them as production evidence after reversion. Evidence receipts,
audit ledgers and state files are retained, never deleted or rewritten.

## Ownership

Builder: this change and its tests. Curator (separate identity): reproduction. Steward:
the qualification-only dependency and the CI wiring. Integrator: the `ReceiptStore`,
`CurrentEvidenceAuthority` and `HostLeasePort` adapters. Architect: the archival status
policy and candidate-to-lease mapping. Orchestrator: scheduling of the external
obligations below. Explorer and Optimizer: none in this slice.

## Roles and lifecycle stages

This ADR does not claim any role or stage as satisfied. Evidence that already exists is the
external design-court record (Explorer/Architect/Judge participation for discover and
design). Everything else is a pending obligation:

- Orchestrator: schedule parent execution, independent review and external obligations.
- Explorer: pinned primary-source intake for the `cryptography` qualification pin (pending).
- Architect: archival status policy; candidate-to-`HostLease` mapping (pending).
- Builder: this change (evidence: source and tests, UNRUN).
- Curator: independent reproduction of every acceptance row (pending).
- Integrator: real store, current-status and lease adapters (pending).
- Steward: dependency pin, CI job and contract-test amendment (pending).
- Optimizer: no metric or challenger is claimed (nothing pending in this slice).
- Discover / design: design-court record (external). Build: this change. Validate, grow,
  maintain, integrate: pending.

## External obligations and open conflicts

### Qualification integration addendum (2026-09-21)

The dependency and contract items below describe the Builder's original handoff. They
are superseded for code preparation by two separate independent ADAPT dispositions:
dependency Judge `0be22be4d254ee76e79363d9f300a56c0cafb03b482152daf3857162060169f0`
and CI exception Judge `e2c60bdfbbb4eb66d02bd1dde60d779ea2ea97aeae272d332eb4a38a124d32d3`.
Primary-source intake `2e9932e7278d3ca2962d6b627cd1a9a882c4062dc73494289bb46be3f9ab7e3f`
retains PyPI metadata, nine published wheel hashes and license notices. Qualification
uses cryptography 50.0.1, cffi 2.1.1 and pycparser 3.0 from
`requirements/production-evidence-crypto.txt`, installed with `--only-binary=:all:` and
`--require-hashes`. Runtime `dependencies=[]` is unchanged. This is no admission of
other platforms, source builds, live key custody, or redistribution license audit.

The deliberate contract amendment permits only `tests/test_production_evidence.py` to
import the top-level `cryptography` package. The all-module import scan and every other
third-party prohibition remain. This is an explicit exception to the old blanket rule,
not a dynamic-import evasion. The module requires the exact three distribution versions
and the loaded provider version at import, with hard failures and no skip. Actual
subprocess controls exercise missing distributions, each wrong distribution version
and a wrong loaded provider; real signature positive/wrong-key/tamper controls remain.

Both existing unit-job definitions install the hash-locked provider unconditionally
before the unchanged full test discovery. The five existing combinations remain
Linux 3.11/3.12/3.14 and Windows 3.12/3.14. Contract tests bind the full admitted wheel
set, installation order, flags, matrix and absence of conditional/error-swallowing
steps, with negative fixtures for omitted or weakened installation. Dependency/license
security gates and protected-check policy are unchanged. Local and remote qualification
results must still be recorded separately; this amendment does not assert them.

To reproduce qualification in a fresh environment, install the local package and then
run `python -m pip install --only-binary=:all: --require-hashes -r
requirements/production-evidence-crypto.txt` before the normal full CI command. Removing
this exception requires an equally real mandatory verification path; skipping E1 is
not a valid rollback. Production composition remains disabled until independently
qualified and supplied with the external authorities listed below.

1. **Dependency (pending).** No `production-evidence-crypto-dependency-intake.md` existed
   when this was written, so no version or hash was chosen. Root must install the exact
   qualification-only `cryptography` pin (hash-locked, like
   `requirements/spdx-validator-linux-py312.txt`) wherever the test module runs. Missing
   `cryptography` makes `tests/test_production_evidence.py` fail at import; it never skips.
   `pyproject.toml` (`dependencies = []`) and `.github/workflows/ci.yml` are unchanged.
2. **Contract conflict (unresolved, deliberately not weakened).**
   `tests/test_ci_contract.py::test_no_test_module_imports_third_party` forbids any
   third-party import in `tests/*.py`, and the real-signature controls require
   `cryptography`. Until root adds a reviewed, module-scoped allowance for exactly this
   file and package, that contract test fails. It was not edited, and the import was not
   hidden behind `importlib` to evade it.
3. External: real issuer and key custody with independent administration, revocation and
   rotation; provisioned receipt storage and actual receipt schemas and pins; a real
   `HostLease` source and its candidate mapping; a real current-status service; real
   supervisor and evaluator grants; `HostProfileRegistry` capability authorization.

## Remand addendum: two Curator boundary counterexamples (2026-09-21)

Earlier text is kept as written. **Every test named here is UNRUN by the Builder.** An
independent Curator's `probe_boundary_v1.py` (results in `e1-curator/boundary-v1/`)
confirmed two material gaps in the first candidate; the original design and appeal
conditions remain binding.

### R1. Accepted credit with absent required prerequisites

Threat: `_require_completion` resolved only the prerequisites that were *present*. With any
or all of host, supervisor, delivery authority or benchmark absent from the frozen plan, a
public `record_attempt` durably credited an accepted delivery, appended a success audit
record and replayed successfully, while `report()` still showed the blockers.

Repair (`pilot_runtime.py`): `_require_structural_admission` re-derives
`plan.prerequisites.blockers(plan.mode)` from the frozen plan (stored obligations are never
consulted) and raises a typed, **audited failure** (`incomplete-evidence`, naming each
missing prerequisite) before any lease lookup, resolution, success audit or durable write.
It runs for every accepted positive path, `record_attempt` and `complete_attempt`, ahead of
the idempotent early returns, so replay and reload of already-credited state are refused
too, and it is shared with `require_dispatch_gate` (begin and pre-dispatch recheck), which
previously raised the same blocker without an audit record. Non-accepted closes and
records are unchanged: they need no admission, no lease and no structural check, so
crash-inconclusive recovery stays possible. Nothing is closed as no-effect on this path.
Not changed: `record_controls` and `record_observation` still resolve only the evidence
they accept; a control receipt does not credit an attempt, and `report()` stays blocked
while prerequisites are missing.

### R2. Mutable manifest mappings laundered through a real judge

Threat: `CloseoutManifest` keeps public mutable `dict`s. After construction, clearing
nodes, requirements, roles or lifecycle evidence changed the digest; a genuine fresh judge
then signed that digest and `verify_production_closeout` and
`write_verified_release_manifest` returned positive with as few as three resolutions and
wrote a file the loader rightly rejects as corrupt.

Repair (`release_closeout.py`): `snapshot_manifest` rebuilds a deep, typed copy through the
**unchanged** `CloseoutManifest` constructor, so every existing schema and acceptance rule
is re-applied (all requirement/node/role/stage sets, keys against subjects, attested
evidence, candidate bindings, positive-release rule). Any failure is
`manifest-malformed`, audited as a failure. `verify_production_closeout`,
`write_verified_release_manifest` and `load_verified_release_manifest` each snapshot once,
before any resolution, audit success or file write, and then use that same frozen content
for resolution, judge binding, digest and the written bytes; the caller's mutable object
is not read again, so mutation during resolution cannot change what is verified or
written. The load path returns the verified snapshot. A cryptographically valid judgment
over a malformed manifest is rejected. `CloseoutBuilder.seal` already constructs through
the validating constructor from copied dicts, so it needs no separate wrapper; mutation
after sealing is caught at the next production boundary. The raw `write_release_manifest`,
`load_release_manifest` and `manifest_digest` remain explicit local structural views and
publish nothing as production evidence.

### Remand tests (UNRUN by the Builder)

`ProductionPilotTests.test_accepted_credit_replay_and_completion_rederive_every_structural_prerequisite`
(each of host, supervisor, delivery authority, benchmark and all four absent: fresh
accepted record, active completion, hand-edited durable replay and reload, unchanged state
and no new success audit, inconclusive recovery still allowed without admission, the
runner never reaching the host, plus the valid complete-plan positive and replay);
`ProductionCloseoutTests.test_mutated_manifest_cannot_launder_a_malformed_shape_through_a_real_judge`
(each set and all four removed, real freshly signed judge, verify and write both rejected
before resolution, success audit or file),
`test_nested_mutations_and_wrong_types_are_rejected_before_resolution`, and
`test_verified_content_is_stable_against_mutation_during_resolution` (mutation of the
caller's manifest during resolution; the written file and returned snapshot match the
verified digest).

### Rollback for this remand

Independent of the rest: reverting R1 restores missing-prerequisite credit; reverting R2
restores acceptance of mutated manifests. Neither deletes evidence or audit records.

### R3. Concurrent identical completions double-credited durable state

**Every test named in R3 is UNRUN by the Builder.** The Curator's `probe_boundary_v2.py`
(`e1-curator/boundary-v2/`, `REMAND.md`) scheduled two real public `complete_attempt`
calls of the same valid accepted attempt. Both read the active attempt in their
pre-check; one committed; the other's `_update` re-read the fresh state, but its transform
appended without repeating the identity and active-binding checks. Both returned
success, the durable identities were `['same', 'same']`, two rows were accepted and
`report()` raised `QualificationError`. This is inherited transition code, not introduced
by the verifier, but it defeated the accepted-replay and no-phantom-credit claims.

Repair (`pilot_runtime.py` only; the `PilotStore` compare-and-swap contract and the
`expected_revision` check inside its lock are unchanged, and no revision or timestamp is
invented):

- Completion: the duplicate/idempotence and current-active-binding predicate is one helper,
  `_already_completed`, used for the fast pre-check **and again inside the transform** over
  the state the transition is actually compared to and committed over. An identical
  completion that landed meanwhile returns that same committed state unchanged (one
  attempt, one resource charge, no extra revision or history line). A different payload
  raises `attempt identity already has different content`, and a vanished or mismatched
  active lease raises; neither appends nor replaces the earlier result. The check runs
  before the delivery-rate check, so an idempotent duplicate is never charged again.
- Begin: the same treatment through `_already_active`. Concurrent identical begins charge
  once; a conflicting begin is refused; an identity that completed meanwhile is never
  reopened as active (previously `PilotState` did not check attempts against active
  leases). The concurrency and daily-budget checks still run over the committed state.
- `record_attempt` composes these two paths and inherits both. `_update` treats a
  transform that returns its input state as an idempotent no-op and writes nothing.
- A racing writer that commits *between* a caller's read and its save is still refused by
  the store's real compare-and-swap (`stale pilot state revision`, a typed conflict), never
  silently overwritten; no automatic retry was added.

Unchanged: current-admission verification before every positive public entry including
idempotent replay (it runs before these transitions), resource/daily/delivery-rate limits,
non-accepted and crash-inconclusive closure without admission, and the outside-window
obligation.

Tests (`tests/test_production_evidence.py`, using a real `PilotStore` subclass,
`InterleavedStore`, that only pauses the second caller immediately before the compared
transition's load, identified by call frame rather than a read count, and never alters
returned states or bytes): `test_concurrent_identical_completions_credit_and_charge_exactly_once`
(one attempt, one charge, no extra history line, `report()` returns; delivery-rate limit 1),
`test_concurrent_conflicting_completion_never_appends_or_replaces` (accepted-then-
inconclusive and inconclusive-then-accepted),
`test_concurrent_begins_charge_once_and_never_reopen_or_duplicate` (identical, conflicting,
already-completed),
`test_concurrent_crash_recoveries_close_one_inconclusive_attempt` and
`test_trusted_local_completion_race_and_store_compare_and_swap_are_preserved`.

Rollback: reverting R3 restores the double-credit race. It deletes nothing; a state
already carrying duplicate identities stays as retained evidence and must be quarantined,
not repaired in place.

## Root execution and independent disposition, 2026-09-21

The Builder's unrun statements above describe its restricted edit-only session.
Root subsequently executed the qualified isolated Python environment: 73 focused
tests pass in 5.005 seconds, including production evidence, runtime, orchestration,
closeout and the CI contract. Repository-configured Ruff (`src tests`) and Pyright
(configured `src` scope) pass. An exploratory expansion of Pyright to test fixtures
reported 92 typing diagnostics; that extra scope is not the configured gate and
is not claimed passing. No ignore or gate weakening was introduced.

Independent Curator `/root/readiness_judge` froze the candidate, replayed both
original counterexample scripts unchanged, and reproduced all 73 focused tests.
The 13 original scenarios and 24 additional cases comprising 113 checks close
the three remands: missing admission prerequisites cannot earn credit, mutable
closeouts cannot bypass structural validation, and racing completions cannot
double-credit a result. Additional checks cover conflicting signed payloads,
one durable transition, all three mode-specific admission omissions, mutation
during current-status resolution, revoked replay and no-refund recovery.
Eight critical source/qualification files remain identical after the separate
H1 clock-fixture correction was propagated to this branch.

Scoped disposition: ADOPT for verification-only reversible delivery, subject to
full CI. Review SHA-256:
`5be57327f86ba7b51b5ece39c96a6c891e80acdc7f1a9946141c73a7255a06e6`;
receipt: `26467a2d0f24d2fff9693fceac58f2babf23eca10a5530638011e399b506ddf6`.
The prior CI integration ADOPT and dependency qualification remain separate
receipts. Original failures and the deliberately stopped first full run are
retained; the second full local run and remote matrix are pending at this entry.

These checks use explicitly synthetic signing principals/providers. Real external
custody, issuer mappings, current-status services, host leases, pilot targets and
admitted pilot outcomes remain required. Signature validity authenticates the
configured attestor's claim; it does not independently prove the claim is true.
Disable production-mode composition on rollback and retain evidence; never
substitute trusted-local mode as a production qualification fallback.
