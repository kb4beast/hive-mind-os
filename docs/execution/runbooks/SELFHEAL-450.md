# SELFHEAL-450 — Self-healing runtime composed over mission reconciliation

## 1. Contract summary

**Objective.** Integrate provider failover, bounded retry, remand, rollback,
workspace rebuild, stale-lease repair, and quarantine into mission
reconciliation. The design **composes** the existing
`DesiredStateReconciler`; it never forks, subclasses, or re-implements it.

**Compressed acceptance criteria.**

| # | Criterion |
|---|---|
| AC1 | Every recoverable failure maps to a deterministic repair or bounded role remand. |
| AC2 | Provider failover preserves contract and receipt identity. |
| AC3 | Rollback is automatic only inside existing authority. |
| AC4 | Repeated semantic no-progress quarantines. |

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (create ONLY these) | `src/hive_mind_os/brain_kernel/self_healing.py`, `tests/test_hive_cortex_self_healing.py`, `docs/execution/SELF_HEALING.md` |
| read_scope | `src/hive_mind_os/brain_kernel/**`, `src/hive_mind_os/model_provider.py` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**HARD RULES (violating any one is a scope violation → `autopilot fail`):**

- Create/modify ONLY the three write_scope paths. Explicitly forbidden: ANY
  `__init__.py` (including `src/hive_mind_os/brain_kernel/__init__.py`),
  `conftest.py`, `pyproject.toml`, `.autopilot/**`, everything in
  forbidden_scope, and every sibling node's files (CHALLENGER-510 and
  POISON-540 run in this same round R3 — never touch their paths).
- The new module is imported by FULL module path:
  `from hive_mind_os.brain_kernel.self_healing import ...`. No package
  re-export edits. Existing tests already import this way
  (see `tests/test_hive_cortex_reconciler.py` line 7).
- Never touch the release branch (`release/hive-mind-os-singleton-20260812-r5`).
  Work only on node branch `autopilot/selfheal-450`. Never rebase/squash/amend.
- Run ONLY the focused test command in section 5. NEVER run
  `python -m unittest discover` — the authenticated validation broker exclusively owns
  the repository-wide gate.
- Semantic lock held: `self-healing-runtime`. Stopping condition: open a draft
  PR targeting `main` with a validated node receipt; do not merge, do not
  start downstream nodes.

**Round context.** Round R3, wave `SELFHEAL-450 CHALLENGER-510 POISON-540`
(3 parallel sessions). If you discover a real dependency on a sibling,
`autopilot fail` with a blocker — never poll or wait for a sibling.

## 2. Existing-code map (real signatures — do not invent others)

All paths relative to repo root. These are the ONLY external symbols the new
module needs.

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/reconciler.py` | `RepairKind` | `class RepairKind(StrEnum)` with members `RELEASE_STALE_LEASE, RETRY, REMAND, REBUILD_WORKSPACE, ROLLBACK, QUARANTINE` | Finite repair vocabulary. |
| `reconciler.py` | `ReconciliationPolicy` | `@dataclass(frozen=True, slots=True)` fields `max_retries: int = 3`, `no_progress_limit: int = 3`, `max_repairs_per_pass: int = 8` | Bounds for automatic recovery. |
| `reconciler.py` | `ObservedState` | `@classmethod from_document(cls, document: Mapping[str, Any]) -> "ObservedState"`; fields incl. `mission_id`, `mission_status`, `no_progress_count: int`, `progress_signature: str \| None`, `authority_scope: tuple[str, ...]`; property `digest -> str` | Canonical reconciler input. |
| `reconciler.py` | `RepairAction` | frozen dataclass: `kind: RepairKind, target_id: str, reason: str, attempt: int = 0, max_attempts: int = 1, authority_scope: tuple[str, ...] = ()`; property `action_id -> str` (`f"{kind.value}:{target_id}"`); `to_document() -> dict[str, Any]` | One bounded proposal (not an executed effect). |
| `reconciler.py` | `ReconciliationResult` | fields `observed: ObservedState, desired: DesiredState, now: float`; properties `actions`, `quarantined`; `apply(self, handlers: Mapping[str \| RepairKind, Callable[[RepairAction], Any]]) -> tuple[str, ...]` | One pass result; missing handlers are safe no-ops. |
| `reconciler.py` | `DesiredStateReconciler` | `__init__(self, policy: ReconciliationPolicy \| None = None)`; `reconcile(self, observed: ObservedState \| Mapping[str, Any], *, now: float) -> ReconciliationResult` | Pure planner. COMPOSE it; never fork. |
| `reconciler.py` | `DesiredState` | fields incl. `mission_status: str, actions: tuple[RepairAction, ...], quarantined: bool, observed_digest: str, desired_digest: str`; `to_document() -> dict[str, Any]` | Reconciled projection. |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `def canonical_digest(value: Any) -> str` (returns `"sha256:<hex>"`) | All identity/receipt digests. |
| `src/hive_mind_os/brain_kernel/events.py` | `KernelEvent` | frozen dataclass: `event_id: str, mission_id: str, event_type: str, actor_id: str, occurred_at: str, payload: Mapping[str, Any], work_id: str \| None = None, attempt_id: str \| None = None, actor_role: str \| None = None, event_version: int = 1, previous_digest: str \| None = None` | Durable event fact. |
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore.append` | `def append(self, event: KernelEvent, *, expected_sequence: int \| None = None, recorded_at: str = "1970-01-01T00:00:00Z", idempotency_key: str \| None = None) -> int` | Optional durable healing-pass event. |
| `store.py` | `KernelStore.events` | `def events(self) -> list[dict[str, Any]]` (rows include `"digest"`) | Chain the `previous_digest` link. |
| `src/hive_mind_os/model_provider.py` | `ModelRequest` | frozen dataclass: `system: str, user: str, corrective_message: str \| None = None` | Provider-neutral request; its canonical digest IS contract identity. |
| `model_provider.py` | `ModelResponse` | frozen dataclass: `content: str, raw_body: bytes, prompt_tokens: int \| None, completion_tokens: int \| None, transport_retry_index: int = 0` | Provider result. |
| `model_provider.py` | `ModelTransportError` | `class ModelTransportError(ModelProviderError)` | Transport failure → failover to next provider. |
| `model_provider.py` | `MissingModelCredential` | `class MissingModelCredential(ModelProviderError)` | Absent credential → failover to next provider. |
| `model_provider.py` | `ModelResponseError` | `class ModelResponseError(ModelProviderError)`, `__init__(self, message: str, raw_body: bytes)` | Semantic failure → NOT a failover trigger (counts toward no-progress). |
| `model_provider.py` | `ModelProvider` (Protocol) | requires `config: ProviderConfig`, `kind: ProviderKind`, `complete(self, request: ModelRequest) -> ModelResponse`, property `credential_reference -> str` | Duck-type chain members against this. |
| `src/hive_mind_os/scheduler.py` (context only) | `Scheduler` / `KernelWorker.reconcile` (`workers.py`) | `def reconcile(self, observed: Mapping[str, Any], *, now: float \| None = None, policy: Any \| None = None) -> Any` | Existing adapter pattern to imitate: derive plans, never auto-execute. |

## 3. Design — `src/hive_mind_os/brain_kernel/self_healing.py`

One new module, stdlib-only, no I/O except optional `KernelStore` appends.
Module docstring must state: "Composes the desired-state reconciler; applying
a repair is always an explicit, authority-checked handler call."

Imports (exactly these external ones):

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from .canonical import canonical_digest
from .events import KernelEvent
from .reconciler import (
    DesiredStateReconciler, ObservedState, ReconciliationPolicy,
    ReconciliationResult, RepairAction, RepairKind,
)
from .store import KernelStore
from ..model_provider import (
    MissingModelCredential, ModelRequest, ModelResponse,
    ModelResponseError, ModelTransportError,
)
```

### 3.1 Errors

```python
class SelfHealingError(RuntimeError):
    """Base error for the self-healing runtime."""

class AuthorityViolationError(SelfHealingError):
    """A repair required authority outside the granted scope."""

class FailoverExhaustedError(SelfHealingError):
    """Every provider in the chain failed at the transport layer."""
    def __init__(self, message: str, attempts: tuple["FailoverAttempt", ...]) -> None: ...
        # sets self.attempts
```

### 3.2 Provider failover (AC2)

```python
class FailoverProvider(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...
    @property
    def credential_reference(self) -> str: ...

def request_identity(request: ModelRequest) -> str:
    """canonical_digest({"corrective_message": ..., "system": ..., "user": ...})."""

@dataclass(frozen=True, slots=True)
class FailoverAttempt:
    provider_index: int
    credential_reference: str
    outcome: str            # "success" | "transport-error" | "missing-credential"
    detail: str             # redacted error text or "" on success
    def to_document(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class FailoverReceipt:
    request_digest: str          # request_identity(request) — identical across providers
    response_digest: str         # canonical_digest({"content": response.content})
    attempts: tuple[FailoverAttempt, ...]
    served_by: int               # index of the provider that succeeded
    def to_document(self) -> dict[str, Any]: ...
    @property
    def digest(self) -> str:     # canonical_digest(self.to_document())

class ProviderFailoverChain:
    def __init__(self, providers: Sequence[FailoverProvider]) -> None:
        # raise ValueError("failover chain requires at least one provider") if empty
    def complete(self, request: ModelRequest) -> tuple[ModelResponse, FailoverReceipt]:
```

`complete` control flow: compute `request_digest` ONCE before any attempt
(this is the preserved contract identity — the exact same `ModelRequest` is
handed to every provider unmodified). Iterate providers in order; catch ONLY
`ModelTransportError` and `MissingModelCredential` and record a
`FailoverAttempt`, then continue to the next provider. `ModelResponseError`
propagates unchanged — a semantic failure is not a transport problem and must
surface to the no-progress ledger, not silently switch providers. On success,
build the receipt with the pre-computed `request_digest`; on full exhaustion
raise `FailoverExhaustedError` carrying all attempts. Never log or embed
`raw_body` or credential values in receipts — only `credential_reference`.

### 3.3 Progress ledger — semantic no-progress (AC4)

```python
@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    signature: str | None
    no_progress_count: int

class ProgressLedger:
    """Pure signature comparator; the caller persists the returned counts."""
    def advance(self, previous: ProgressUpdate, current_signature: str | None) -> ProgressUpdate:
```

`advance`: if `current_signature` is not None and equals
`previous.signature`, return `ProgressUpdate(current_signature,
previous.no_progress_count + 1)`; otherwise return
`ProgressUpdate(current_signature, 0)`. The caller feeds the resulting
`no_progress_count` back into the next `ObservedState` document, where the
EXISTING reconciler rule (`reconciler.py` lines 453-461) emits
`RepairKind.QUARANTINE` once `no_progress_count >= policy.no_progress_limit`.
Do not duplicate that quarantine rule in this module.

### 3.4 Repair handler registry and authority guard (AC1, AC3)

```python
RepairHandler = Callable[[RepairAction], Any]

class RepairHandlerRegistry:
    def __init__(self) -> None: ...
    def register(self, kind: RepairKind, handler: RepairHandler) -> None:
        # re-registering a kind raises ValueError("handler already registered: ...")
    def handlers(self) -> dict[RepairKind, RepairHandler]:  # shallow copy
```

```python
@dataclass(frozen=True, slots=True)
class HealingOutcome:
    action_id: str
    kind: str                # RepairKind.value
    status: str              # "applied" | "skipped-no-handler" | "escalated-authority"
    reason: str
    def to_document(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class HealingReceipt:
    mission_id: str
    observed_digest: str
    desired_digest: str
    outcomes: tuple[HealingOutcome, ...]
    quarantined: bool
    escalations: tuple[str, ...]     # action_ids that need a human/role decision
    progress: ProgressUpdate
    def to_document(self) -> dict[str, Any]: ...
    @property
    def digest(self) -> str: ...
```

```python
class SelfHealingRuntime:
    def __init__(
        self,
        registry: RepairHandlerRegistry,
        *,
        policy: ReconciliationPolicy | None = None,
        reconciler: DesiredStateReconciler | None = None,
        store: KernelStore | None = None,
        actor_id: str = "self-healing-runtime",
    ) -> None:
        # self.reconciler = reconciler or DesiredStateReconciler(policy)
    def heal(
        self,
        observed: ObservedState | Mapping[str, Any],
        *,
        now: float,
        granted_authority: Sequence[str] = (),
    ) -> HealingReceipt:
```

`heal` control flow (this is the integration point that satisfies AC1):

1. `result = self.reconciler.reconcile(observed, now=now)` — composition, not
   a fork. All fault classification (stale lease, retryable provider failure,
   workspace rebuild, interrupted verification remand, integration rollback,
   orphaned-intent and budget-exhaustion quarantine) stays in the reconciler.
2. Build the effective handler map from `self.registry.handlers()`, then wrap
   it: for each `action` in `result.actions`, decide an outcome BEFORE
   dispatch:
   - no handler registered → `HealingOutcome(..., "skipped-no-handler",
     "no handler registered; proposal retained")`. Safe no-op (mirrors
     `ReconciliationResult.apply` semantics).
   - `action.kind is RepairKind.ROLLBACK` and
     `not set(action.authority_scope) <= set(granted_authority)` →
     `HealingOutcome(..., "escalated-authority", ...)`, add `action.action_id`
     to `escalations`, DO NOT call the handler (AC3: rollback is automatic
     only inside existing authority). Apply the same subset guard to every
     kind — but ROLLBACK must be covered by an explicit test.
   - otherwise call the handler once, in `result.actions` order (the
     reconciler already sorted deterministically by priority then action_id),
     and record `"applied"`. A handler exception is wrapped:
     `raise SelfHealingError(f"repair handler failed: {action.action_id}") from error`
     — never swallow it, never continue past a failed repair.
3. Compute `progress = ProgressLedger().advance(ProgressUpdate(
   result.observed.progress_signature, result.observed.no_progress_count),
   result.desired.desired_digest if result.actions else result.observed.progress_signature)`
   — a pass that proposes actions establishes a new signature (the desired
   digest); a pass with zero actions keeps the previous signature so repeated
   identical stalls accumulate.
4. Assemble `HealingReceipt` from `result.observed.digest`,
   `result.desired.desired_digest`, outcomes, `result.quarantined`,
   escalations, progress.
5. If `self.store is not None`, append one `KernelEvent(
   event_id=f"self-healing:{mission_id}:{receipt.digest}",
   mission_id=..., event_type="self_healing.pass", actor_id=self.actor_id,
   occurred_at="1970-01-01T00:00:00Z", payload=receipt.to_document(),
   actor_role="steward", previous_digest=<digest of last row from
   store.events(), or None>)`. Use `idempotency_key=receipt.digest` so a
   crashed-and-replayed pass is a read-only retry.
6. Return the receipt.

`__all__` lists every public name above.

### 3.5 Doc — `docs/execution/SELF_HEALING.md`

40-80 lines. Sections: purpose; fault matrix table (failure class → observed
signal → `RepairKind` → bound/budget → terminal outcome); failover identity
guarantee (request_digest invariance); authority rule for rollback;
no-progress → quarantine loop; how callers wire `RepairHandlerRegistry`;
pointer to `docs/execution/DESIRED_STATE_RECONCILIATION.md` for the base
reconciler semantics. No code duplication — reference signatures only.

## 4. Implementation order (small commits on `autopilot/selfheal-450`)

1. `feat(kernel): add self-healing errors, failover chain, and receipts` —
   module skeleton, errors, `request_identity`, `FailoverAttempt`,
   `FailoverReceipt`, `ProviderFailoverChain`.
2. `feat(kernel): add progress ledger and repair handler registry` —
   `ProgressUpdate`, `ProgressLedger`, `RepairHandlerRegistry`,
   `HealingOutcome`, `HealingReceipt`.
3. `feat(kernel): compose reconciler into self-healing runtime` —
   `SelfHealingRuntime.heal` with authority guard and optional store event.
4. `test(kernel): cover self-healing fault matrix, failover, rollback, quarantine`
   — full test file (section 5).
5. `docs(execution): document the self-healing runtime` — SELF_HEALING.md.
6. Run the focused command, fix, open draft PR to `main`, push receipt.

## 5. Test plan — `tests/test_hive_cortex_self_healing.py`

Conventions (copy from `tests/test_hive_cortex_reconciler.py`): stdlib
`unittest`, one class, full-module-path imports, no fixtures beyond inline
dicts and tiny fake providers. Fake providers are plain classes with
`complete(request)` and a `credential_reference` property — do NOT construct
real `ProviderConfig`/HTTP transports.

```python
class HiveCortexSelfHealingTests(unittest.TestCase): ...
```

**required_tests mapping (every plan name → concrete methods):**

| required_tests name | Test method(s) | What it proves |
|---|---|---|
| `self-healing-fault-matrix` | `test_self_healing_fault_matrix_tests` | One observed document containing simultaneously: an expired lease, a retryable provider failure under budget, a missing workspace under budget, an interrupted verification, and an intent on RUNNING work. `heal` with all six kinds registered applies every action deterministically; outcomes list matches reconciler priority order; every recoverable failure produced exactly one `applied` outcome (AC1). Also: unregistered kind → `skipped-no-handler`, receipt digest stable across two identical passes. |
| `provider-failover-tests` | `test_provider_failover_tests`, `test_provider_failover_exhaustion_tests`, `test_provider_semantic_error_does_not_failover_tests` | Chain of [always-`ModelTransportError` fake, always-`MissingModelCredential` fake, succeeding fake]: response served by index 2; `receipt.request_digest == request_identity(request)` and equals the digest a single-provider chain produces for the same `ModelRequest` (AC2 identity preservation); attempts record 2 failures + 1 success with no secret material. Exhaustion: all-failing chain raises `FailoverExhaustedError` with `len(attempts) == len(providers)`. Semantic: a fake raising `ModelResponseError("bad", b"{}")` propagates unchanged and the next provider is NOT tried. |
| `rollback-tests` | `test_rollback_inside_authority_tests`, `test_rollback_outside_authority_escalates_tests` | Work record with `"rollback_required": True` and `"authority_scope": ["src/a.py"]`. With `granted_authority=("src/a.py",)` the ROLLBACK handler runs (`applied`). With `granted_authority=()` the handler is NEVER called (assert via recording list), outcome is `escalated-authority`, action_id appears in `receipt.escalations` (AC3). |
| `quarantine-tests` | `test_no_progress_quarantine_tests`, `test_progress_ledger_reset_tests` | Feed `no_progress_count` at `policy.no_progress_limit` (default 3): `heal` receipt has `quarantined=True` and a QUARANTINE outcome targeting the mission (AC4, exercising the reconciler rule through composition). Ledger: `advance` on an equal signature increments; a changed signature resets to 0. |

Additional edge assertions folded into the above methods: empty provider
chain raises `ValueError`; handler exception surfaces as `SelfHealingError`;
and the durable pass append **fails closed** — see below.

**The durable pass event: assert fail-closed, not a successful append.**
Do NOT assert that `heal` with a `KernelStore(":memory:")` appends a
`self_healing.pass` event. That is unsatisfiable, and making it satisfiable
would break a seal.

`reduce_event` raises `ValueError(f"unknown kernel event type: {event_type}")`
for anything outside its dispatch chain (`projection.py:271-272`), and
`append`/`append_batch` rebuild inside the same transaction, converting that
into `KernelIntegrityError("event sequence cannot be reduced")` and rolling the
insert back (`store.py:320`, `store.py:628-630`). Measured:
`KernelStore(':memory:').append(KernelEvent(event_type='self_healing.pass', …))`
raises `KernelIntegrityError` with cause
`ValueError('unknown kernel event type: self_healing.pass')`, and
`store.events()` is still empty.

Teaching the reducer this type is **not** an option for any node: `projection.py`
is under the sealed `event-schema` lock (MISSION-400 §1 — "the reducer in
`projection.py` is CLOSED … do NOT edit `projection.py`"), and CHEAT-440's
anti-cheating evidence asserts precisely that the spine refuses invented event
types. Adding one to make this node's own test pass would be the cheat that
node exists to detect.

Assert instead: the append fails closed with `KernelIntegrityError`, the cause
message names the unknown type exactly, and no partial write survives. Build
`_append_pass` exactly as §3.4 specifies (epoch `occurred_at`, chained
`previous_digest`, `idempotency_key=receipt.digest`, `actor_role="steward"`) so
the durable path is correct the moment a node that owns `projection.py` is
authorized to admit the type; record that admission as an open obligation in
`SELF_HEALING.md` rather than performing it here.

**Exact focused commands (run from repo root; PowerShell and bash identical):**

```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_self_healing -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_reconciler -v   # composition regression guard (read-only neighbor check)
```

NEVER run `python -m unittest discover -s tests` — integrator-only.

## 6. Acceptance self-check → completion receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| AC1 every recoverable failure → deterministic repair or bounded remand | `heal` delegates classification to `DesiredStateReconciler.reconcile` (all six `RepairKind`s covered in the fault-matrix test with bounded `attempt/max_attempts`) | `test_self_healing_fault_matrix_tests` pass output; changed-path inventory = exactly the 3 write_scope paths |
| AC2 failover preserves contract and receipt identity | `request_digest` computed once from the immutable `ModelRequest`, asserted equal across 1-provider and 3-provider chains | `test_provider_failover_tests` output; quoted assertion lines in receipt |
| AC3 rollback automatic only inside existing authority | subset guard on `action.authority_scope` vs `granted_authority`; escalation path never invokes the handler | both rollback test outputs |
| AC4 repeated semantic no-progress quarantines | `ProgressLedger` count feeds the existing reconciler quarantine bound; receipt shows `quarantined=True` | `test_no_progress_quarantine_tests` output |
| Evidence requirements (node contract) | base/final commit SHAs, `git diff --name-only <base>..HEAD` bound to write_scope, both focused test command receipts, role identities (builder/steward), rollback reference = revert of the node commit | completion receipt fields |

## 7. Out-of-scope traps — do NOT do these

- Do NOT edit `reconciler.py`, `workers.py`, `model_provider.py`, `store.py`,
  `events.py`, or ANY existing file — read-only inputs. If a change there
  seems required, that is escalation condition "required changes exceed
  declared write scope": `autopilot fail`, do not improvise.
- Do NOT create or edit any `__init__.py`, `conftest.py`, `pyproject.toml`,
  `.autopilot/**`, `.github/**`, `evidence/**`, or
  `docs/architecture/HARDENED_VISION_CONTRACT.md`.
- Do NOT add new `RepairKind` members, subclass `DesiredStateReconciler`, or
  copy its rule loops into `self_healing.py` — compose `reconcile()` only.
- Do NOT auto-execute repairs inside `reconcile`/observation code paths;
  application happens only in `heal` via explicitly registered handlers.
- Do NOT perform real HTTP, subprocess, or filesystem side effects in the
  failover chain or tests; providers in tests are in-memory fakes.
- Do NOT put `raw_body`, API keys, or environment values into any receipt or
  event payload — only `credential_reference` strings.
- Do NOT widen authority to make rollback pass a test (node assumption: "no
  node may expand its own authority or weaken acceptance to pass").
- Do NOT run repo-wide test discovery, touch the release branch, rebase or
  amend `autopilot/selfheal-450`, or wait on CHALLENGER-510 / POISON-540.
- Do NOT re-read `.autopilot/plan.json` or `.autopilot/README.md`; the
  rendered prompt plus this runbook is the complete contract.
