# RUNBOOK DELIVERY-420 — Controlled GitHub delivery adapters on the canonical effect path

## 1. Contract summary

**Objective.** Connect controlled non-protected push, draft-PR, and comment
adapters to the canonical kernel effect path (`EffectIntent` ->
`EffectGateway`/`DurableEffectOutbox` -> `EffectReceipt`) **without adding any
merge authority**. The existing `AutonomousBrain` delivery boundary becomes an
adapter behind the kernel, not a separate brain.

**Acceptance criteria (compressed).**
1. Remote actions require immutable explicit grants (a frozen, digest-sealed
   grant object; no grant, no remote action).
2. Only the run branch can be pushed, never force (protected branches
   `main`/`master`/`staging` and out-of-prefix branches are denied before any
   remote call; the adapter exposes no force option at all).
3. Draft PR / comments are idempotent and receipt-backed (kernel idempotency
   key dedupe + remote lookup-before-create + comment marker dedupe; every
   delivery yields an `EffectReceipt` recorded by the outbox).
4. No merge API is reachable from routine missions (the new package defines no
   merge/close/approve/protection-write method; tests assert this).

**Scope.**

| Kind | Paths |
|---|---|
| write_scope | `src/hive_mind_os/cortex/github/**` (new package — its OWN `__init__.py` is inside this glob and MUST be created), `tests/test_hive_cortex_delivery.py`, `docs/execution/CONTROLLED_DELIVERY.md` |
| read_scope | `src/hive_mind_os/autonomous_os.py`, `src/hive_mind_os/github_adapter.py`, `src/hive_mind_os/brain_kernel/effects.py` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**Hard rules (state and obey).**
- Create/modify ONLY the exact write_scope paths above. Explicitly forbidden:
  any `__init__.py` OUTSIDE `src/hive_mind_os/cortex/github/` (in particular
  `src/hive_mind_os/cortex/__init__.py` and `src/hive_mind_os/__init__.py`),
  `conftest.py`, `pyproject.toml`, sibling nodes' files, `.autopilot/**`, and
  everything in forbidden_scope.
- New modules are imported by FULL module path
  (`hive_mind_os.cortex.github.delivery_adapter` etc.); no package re-export
  edits anywhere outside the new package. Keep the new package's own
  `__init__.py` docstring-only (no re-exports), matching
  `src/hive_mind_os/cortex/__init__.py` style.
- Work only on branch `autopilot/delivery-420`. Never touch the release
  branch, never rebase/squash/amend the node branch, never force-push.
- Run ONLY the focused required_tests command (section 5). Never run
  `python -m unittest discover` — the authenticated validation broker exclusively owns
  the repository-wide gate.
- Semantic lock: `github-delivery-adapter`. Round R2B (runs after DURABLE-410 has
integrated, so crash recovery exists before any external effect); siblings released in the
  same wave: `DURABLE-410`, `HUMANLESS-430`, `CHEAT-440`, `LEARN-500` — never
  read or wait on their files; a real dependency on a sibling means
  `autopilot fail` with a blocker.
- Stopping condition: open a draft PR (target `main`) with a validated node
  receipt; do not merge, do not start downstream nodes.

## 2. Existing-code map (real symbols; do not re-derive)

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/contracts.py` | `EffectIntent` | frozen dataclass, positional fields: `mission_id, work_id, attempt_id, actor_id, role, action, risk_tier, target_adapter, target, parameters_digest, idempotency_key, authority_envelope_digest, expected_preconditions, rollback_description, policy_decision_ref, intent_digest` | canonical intent; `target` is normalized via `normalize_portable_path` |
| `src/hive_mind_os/brain_kernel/contracts.py` | `EffectReceipt` | frozen dataclass: `intent_digest, started_at, ended_at, adapter_identity, adapter_version, observed_precondition_digest, status, stdout_digest, stderr_digest, produced_identifiers, postcondition_digest, retry_of, rollback_receipt` | receipt shape; status in `{"SUCCEEDED","FAILED","ABSTAINED"}` |
| `src/hive_mind_os/brain_kernel/effects.py` | `EffectGateway.__init__(self, store: KernelStore \| None = None) -> None` | adapter registry; with a store it delegates to `DurableEffectOutbox` | the canonical entry point |
| `src/hive_mind_os/brain_kernel/effects.py` | `EffectGateway.register_adapter(self, name: str, adapter: Callable[[EffectIntent], None], *, version: str = "1") -> None` | rejects duplicate/empty names | where the three delivery adapters register |
| `src/hive_mind_os/brain_kernel/effects.py` | `EffectGateway.execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult` | validates token, dedupes by `intent.idempotency_key` | call path under test |
| `src/hive_mind_os/brain_kernel/effects.py` | `build_effect_receipt(intent, *, adapter_identity, adapter_version, started_at, ended_at, status="SUCCEEDED", produced_identifiers=(), observed_precondition_digest=None, postcondition_digest=None, retry_of=None, rollback_receipt=None) -> EffectReceipt` | receipt builder without secrets | used by outbox from adapter return value |
| `src/hive_mind_os/brain_kernel/effect_outbox.py` | `DurableEffectOutbox.execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult` | durable delivery; adapter may return a `Mapping` with keys `produced_identifiers` (list/tuple of `str`) and `postcondition_digest` (`str`) which are folded into the receipt (lines 128–150) | defines the adapter return contract |
| `src/hive_mind_os/brain_kernel/effect_outbox.py` | `EffectReconciliationRequired(RuntimeError)` | raised on ambiguous outcomes; any adapter exception under the durable path becomes this | fail-closed behaviour to test |
| `src/hive_mind_os/brain_kernel/authority.py` | `CapabilityToken` | frozen dataclass `envelope_digest, action, target, token_digest` | required by `execute` |
| `src/hive_mind_os/brain_kernel/authority.py` | `AuthorityRegistry.authorize(self, digest: str, action: str, target: str, *, now: str) -> CapabilityToken` | action must be in envelope `allowed_actions`; write-scope check only for `action == "write"` | mint tokens in tests |
| `src/hive_mind_os/brain_kernel/authority.py` | `AuthorityDenied(PermissionError)` | capability failure type | expected on unregistered adapter / bad token |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest(value: Any) -> str` | returns `"sha256:" + hexdigest` of canonical JSON | parameter/grant/postcondition digests |
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore(Path)` / `.close()` / `.effect_entry(*, intent_digest)` | SQLite kernel store | durable tests |
| `src/hive_mind_os/github_adapter.py` | `GitHubTransport` (Protocol) | `request(self, method: str, url: str, headers: Mapping[str, str], body: bytes \| None, timeout_s: float) -> GitHubResponse` | fakeable HTTP seam — REUSE, do not redefine |
| `src/hive_mind_os/github_adapter.py` | `GitHubResponse` | frozen dataclass `status: int, body: bytes, headers: Mapping[str, str]` | transport response |
| `src/hive_mind_os/github_adapter.py` | `UrllibGitHubTransport.__init__(self, context: ssl.SSLContext \| None = None)` | production transport | default transport binding |
| `src/hive_mind_os/autonomous_os.py` | `PROTECTED_BRANCHES = ("main", "master", "staging")` | module constant (line 32) | mirror in the new package (do NOT import `autonomous_os` — it is heavy and the constant must live with the denial logic) |
| `src/hive_mind_os/autonomous_os.py` | `GitHubRestCommentGateway.open_draft_pull_request(self, owner, repository, branch, base, title, body) -> Mapping[str, Any]` | lookup-before-create draft PR, `draft: True`, `maintainer_can_modify: False` | the remote-idempotency pattern to reproduce |
| `src/hive_mind_os/autonomous_os.py` | `AutonomousBrain.push_own_branch(self, run_id: str, *, remote: str = "origin") -> str` | denies `PROTECTED_BRANCHES`, never force, returns head SHA | the push semantics the adapter enforces at the kernel boundary |

Model the tests on `tests/test_hive_cortex_effects.py` (its `_envelope()` /
`_intent()` helpers and `AuthorityRegistry` setup are the house pattern).

## 3. Design — new files

### 3.1 `src/hive_mind_os/cortex/github/__init__.py`
Docstring only:
```python
"""Controlled GitHub delivery adapters bound to the kernel effect path."""
```

### 3.2 `src/hive_mind_os/cortex/github/grants.py`
```python
from __future__ import annotations
import re
from dataclasses import dataclass
from hive_mind_os.brain_kernel.canonical import canonical_digest

_SIMPLE_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
# Mirrors hive_mind_os.autonomous_os.PROTECTED_BRANCHES; kept local so branch
# denial has no import dependency on the legacy brain.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "staging"})
VALID_DELIVERY_ACTIONS: frozenset[str] = frozenset(
    {"push", "open_draft_pr", "post_comment"}
)  # merge is not a valid action name; it can never be granted


class DeliveryGrantError(PermissionError):
    """A remote delivery action is not covered by an immutable grant."""


@dataclass(frozen=True, slots=True)
class DeliveryGrant:
    grant_id: str
    owner: str
    repository: str
    base_branch: str
    branch_prefix: str            # e.g. "autopilot/" — only branches under it may push
    allowed_actions: tuple[str, ...]
    issued_at: str
    grant_digest: str             # canonical_digest of every other field

    def __post_init__(self) -> None: ...
    @classmethod
    def issue(cls, *, grant_id: str, owner: str, repository: str,
              base_branch: str, branch_prefix: str,
              allowed_actions: tuple[str, ...], issued_at: str) -> "DeliveryGrant": ...
    def require(self, action: str) -> None: ...
    def require_push_branch(self, branch: str) -> None: ...
```
Behaviour:
- `issue` validates `owner`/`repository`/`base_branch` against `_SIMPLE_NAME`,
  requires non-empty `branch_prefix` ending with `/`, requires
  `allowed_actions` to be a non-empty subset of `VALID_DELIVERY_ACTIONS`
  (raise `DeliveryGrantError` otherwise — this is how "merge" is structurally
  ungrantable), then computes `grant_digest = canonical_digest({...all fields
  except grant_digest...})`.
- `__post_init__` recomputes that digest and raises `DeliveryGrantError` on
  mismatch: the dataclass is frozen AND tamper-evident — this is the
  "immutable explicit grant".
- `require(action)` raises `DeliveryGrantError` unless
  `action in self.allowed_actions`.
- `require_push_branch(branch)` raises `DeliveryGrantError` when `branch` is
  empty, in `PROTECTED_BRANCHES`, equal to `self.base_branch`, or does not
  start with `self.branch_prefix`.

### 3.3 `src/hive_mind_os/cortex/github/rest_gateway.py`
Narrow REST surface reusing the existing transport seam. Import
`from hive_mind_os.github_adapter import GitHubResponse, GitHubTransport, UrllibGitHubTransport`.
```python
class DeliveryRestError(RuntimeError):
    """The GitHub REST call failed or returned an invalid document."""


class ControlledRestGateway:
    """Draft-PR and comment REST calls only; no merge, close, review,
    or protection method exists on this class."""

    def __init__(self, owner: str, repository: str, *,
                 transport: GitHubTransport | None = None,
                 token_env: str = "GITHUB_TOKEN",
                 api_base: str = "https://api.github.com",
                 timeout_s: float = 30.0) -> None: ...
    def _request_json(self, method: str, path: str, *,
                      body: Mapping[str, Any] | None = None,
                      accepted: tuple[int, ...] = (200,)) -> dict | list: ...
    def find_open_draft_pr(self, branch: str, base: str) -> Mapping[str, Any] | None: ...
    def create_draft_pr(self, branch: str, base: str, title: str, body: str) -> Mapping[str, Any]: ...
    def list_comments(self, pull_number: int) -> tuple[Mapping[str, Any], ...]: ...
    def post_comment(self, pull_number: int, body: str) -> Mapping[str, Any]: ...
```
Behaviour (copy the proven request mechanics, not the classes):
- `__init__` validates names with `_SIMPLE_NAME`, requires
  `api_base.startswith("https://")` and `timeout_s > 0`; default transport is
  `UrllibGitHubTransport()`.
- `_request_json` reads the token from `os.environ[token_env]` at call time
  (raise `DeliveryRestError` when missing), sends headers exactly as
  `GitHubClient._request_json` does (`Accept: application/vnd.github+json`,
  `Authorization: Bearer <token>`, `User-Agent: "hive-mind-os-delivery-420"`,
  `X-GitHub-Api-Version: "2022-11-28"`), never includes the token in error
  text, and raises `DeliveryRestError` on unexpected status or non-JSON body.
- `find_open_draft_pr` GETs
  `/repos/{owner}/{repo}/pulls?state=open&head={owner}:{branch}&base={base}`
  and returns the first candidate with `draft is True`, else `None`.
- `create_draft_pr` POSTs `/repos/{owner}/{repo}/pulls` with
  `{"title","body","head","base","draft": True, "maintainer_can_modify": False}`,
  `accepted=(201,)`, and raises `DeliveryRestError` if the response is not a
  mapping with `draft is True` (mirror `GitHubRestCommentGateway`,
  `autonomous_os.py` lines 217–246).
- `list_comments` GETs `/repos/{owner}/{repo}/issues/{n}/comments?per_page=100`.
- `post_comment` POSTs `/repos/{owner}/{repo}/issues/{n}/comments` with
  `{"body": body}`, `accepted=(201,)`.

### 3.4 `src/hive_mind_os/cortex/github/delivery_adapter.py`
```python
from typing import Any, Mapping, Protocol
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway
from hive_mind_os.cortex.github.grants import DeliveryGrant, DeliveryGrantError
from hive_mind_os.cortex.github.rest_gateway import ControlledRestGateway

COMMENT_MARKER_PREFIX = "<!-- hive-effect:"


class PushExecutor(Protocol):
    """Pushes exactly one non-force branch ref and returns the full head SHA."""
    def push(self, branch: str) -> str: ...


class DeliveryParametersUnbound(RuntimeError):
    """No registered parameters match the intent parameters_digest."""


class ControlledGitHubDelivery:
    PUSH_ADAPTER = "github-push"
    DRAFT_PR_ADAPTER = "github-draft-pr"
    COMMENT_ADAPTER = "github-comment"
    adapter_version = "1"

    def __init__(self, grant: DeliveryGrant, *, rest: ControlledRestGateway,
                 push_executor: PushExecutor) -> None: ...
    def bind_parameters(self, parameters: Mapping[str, Any]) -> str: ...
    def register_with(self, gateway: EffectGateway) -> None: ...
    def push_adapter(self, intent: EffectIntent) -> dict[str, Any]: ...
    def draft_pr_adapter(self, intent: EffectIntent) -> dict[str, Any]: ...
    def comment_adapter(self, intent: EffectIntent) -> dict[str, Any]: ...
```
Behaviour:
- `bind_parameters` stores `dict(parameters)` in an internal
  `dict[str, dict]` keyed by `canonical_digest(parameters)` and returns that
  digest (same registration pattern as
  `cortex/repository/builder_adapter.py::IsolatedBuilderAdapter.register_action`).
  `EffectIntent` carries only `parameters_digest`, never raw parameters, so
  callers build the intent with the returned digest.
- `_parameters(intent)` looks up `intent.parameters_digest`; missing entry
  raises `DeliveryParametersUnbound` (fail closed, no remote call).
- `_require_target(intent)` asserts
  `intent.target == f"github/{grant.owner}/{grant.repository}"` (already
  portable-path-normalized by the contract), else `DeliveryGrantError`.
- `register_with(gateway)` calls `gateway.register_adapter(name, fn,
  version=self.adapter_version)` for the three names. Only these three
  callables exist; there is no merge adapter to register.
- `push_adapter`: `grant.require("push")`; parameters must contain `branch:
  str`; `grant.require_push_branch(branch)`; ALL denials happen before
  `push_executor.push` is invoked. Then `head = push_executor.push(branch)`;
  validate `re.fullmatch(r"[0-9a-f]{40}", head)` else raise
  `DeliveryRestError`. Return
  `{"produced_identifiers": (f"branch:{branch}", f"sha:{head}"),
    "postcondition_digest": canonical_digest({"pushed": branch, "head": head})}`
  — exactly the mapping shape `DurableEffectOutbox.execute` folds into
  `build_effect_receipt` (effect_outbox.py lines 133–150).
- `draft_pr_adapter`: `grant.require("open_draft_pr")`; parameters need
  `branch`, `title`, `body` (non-empty strings); base is ALWAYS
  `grant.base_branch` (callers cannot pick another base). Remote idempotency:
  `existing = rest.find_open_draft_pr(branch, grant.base_branch)`; when found
  reuse it, else `rest.create_draft_pr(...)`. Validate `number` is a positive
  `int` and `html_url` is a `str`. Return
  `{"produced_identifiers": (f"pr:{number}", url),
    "postcondition_digest": canonical_digest({"pr": number, "draft": True})}`.
- `comment_adapter`: `grant.require("post_comment")`; parameters need
  `pull_number: int > 0`, `body: str` non-empty. Marker dedupe: `marker =
  f"{COMMENT_MARKER_PREFIX}{intent.idempotency_key} -->"`; scan
  `rest.list_comments(pull_number)` — if any existing comment `body` contains
  `marker`, return that comment's identifiers WITHOUT posting; otherwise
  `rest.post_comment(pull_number, body + "\n\n" + marker)`. Return
  `{"produced_identifiers": (f"comment:{comment_id}",),
    "postcondition_digest": canonical_digest({"comment": comment_id,
    "pull": pull_number})}`.

Layering note: kernel-level duplicate suppression (same `idempotency_key` →
prior receipt, no adapter call) is provided by
`EffectGateway`/`DurableEffectOutbox` and is NOT reimplemented; the marker and
lookup-before-create handle the cross-process case where a duplicate arrives
under a fresh intent.

### 3.5 `docs/execution/CONTROLLED_DELIVERY.md`
Short operator doc (60–120 lines): what the boundary is (three adapters, one
grant), the grant issuance example, how intents are built (digest binding via
`bind_parameters`), the denial matrix (protected branch, missing grant action,
unbound parameters, tampered grant), the idempotency layers, and an explicit
"No merge authority" section stating that `VALID_DELIVERY_ACTIONS` excludes
merge and no REST method for merge exists in the package.

## 4. Implementation order (small commits on `autopilot/delivery-420`)

1. `feat(cortex): add immutable github delivery grants` — `__init__.py` +
   `grants.py` + grant tests (`DeliveryGrantTests`).
2. `feat(cortex): add narrow github rest gateway` — `rest_gateway.py` + fake
   transport tests.
3. `feat(cortex): bind controlled delivery to the effect path` —
   `delivery_adapter.py` + adapter/denial/duplicate tests.
4. `docs(execution): document controlled delivery boundary` —
   `CONTROLLED_DELIVERY.md`.
5. Focused test run + receipts; push branch; open draft PR to `main`.

## 5. Test plan — `tests/test_hive_cortex_delivery.py`

Follow the fixture style of `tests/test_hive_cortex_effects.py`: build a
`ConstraintEnvelope` with `allowed_actions=("push", "open_draft_pr",
"post_comment")`, register it in an `AuthorityRegistry`, and mint tokens with
`registry.authorize(DIGEST, action, target, now=TIME)` (non-`"write"` actions
skip the path-scope check — see `authority.py::AuthorityRegistry.authorize`).
Build `EffectIntent` positionally like `_intent()` in that file, with
`target_adapter` set to the adapter name and `target =
"github/octo/repo"` — but note `_intent()` hardcodes `action="write"`:
each test intent must instead set its `action` field to the delivery
action being exercised (`push` / `open_draft_pr` / `post_comment`),
matching the action passed to `registry.authorize` for that test's
token, or `effects.validate_capability_token` raises
`AuthorityDenied("capability token does not bind this intent")`. Use a `FakeTransport` implementing
`GitHubTransport.request(...) -> GitHubResponse` that records every call and
serves scripted JSON bodies; use a `FakePushExecutor` recording pushed
branches and returning `"a" * 40`... use a valid 40-hex constant like
`"0" * 40` is fine (`"0"*40` matches `[0-9a-f]{40}`). No network, no token:
set `os.environ` for the token env inside tests via
`unittest.mock.patch.dict`.

| required_tests name | Test class | Methods (minimum) |
|---|---|---|
| `delivery-adapter-tests` | `DeliveryAdapterTests` | `test_push_executes_through_gateway_and_records_receipt` (durable `KernelStore` + `EffectGateway(store=...)`; assert `effect_entry` state `receipt_recorded` and `produced_identifiers` bound into the stored receipt JSON); `test_draft_pr_creates_when_absent_and_reports_identifiers`; `test_comment_posts_with_marker`; `test_unbound_parameters_fail_closed_without_remote_call` (in-memory gateway, expect `DeliveryParametersUnbound`, transport recorded zero calls); `test_grant_tamper_is_rejected` (constructing `DeliveryGrant` with a wrong `grant_digest` raises `DeliveryGrantError`) |
| `protected-branch-denial-tests` | `ProtectedBranchDenialTests` | `test_push_to_each_protected_branch_is_denied` (loop `main`/`master`/`staging`, in-memory `EffectGateway`, expect `DeliveryGrantError`, `FakePushExecutor` never called); `test_push_outside_grant_prefix_is_denied`; `test_push_to_base_branch_is_denied`; `test_action_not_granted_is_denied` (grant without `"push"`); `test_merge_is_not_a_grantable_action` (`DeliveryGrant.issue(allowed_actions=("merge",))` raises); `test_no_merge_surface_exists` (assert no public attribute of `ControlledGitHubDelivery` or `ControlledRestGateway` contains `"merge"`); `test_durable_path_denial_is_fail_closed` (durable gateway: denial surfaces as `EffectReconciliationRequired` and no receipt is recorded) |
| `duplicate-pr-comment-tests` | `DuplicatePrCommentTests` | `test_same_intent_twice_returns_prior_receipt_without_second_remote_call` (durable store; two `execute` calls, one transport POST); `test_existing_open_draft_pr_is_reused_not_recreated` (scripted GET returns a draft candidate; assert no POST to `/pulls`); `test_comment_with_existing_marker_is_not_reposted` (scripted `list_comments` contains the marker body; assert no comment POST); `test_fresh_intent_new_key_posts_again` (different `idempotency_key`/digests → second POST happens) |

Edge cases: non-mapping adapter return is impossible (always dict); invalid
head SHA from push executor raises; PR response missing `number` raises
`DeliveryRestError`; token env unset raises `DeliveryRestError` before any
transport call.

Exact focused commands (the ONLY test commands this node may run):
```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_delivery -v
```
Optionally a single class while iterating:
```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_delivery.ProtectedBranchDenialTests -v
```

## 6. Acceptance self-check -> completion receipt evidence

| Acceptance criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Remote actions require immutable explicit grants | `DeliveryGrant` frozen + digest-sealed; every adapter method starts with `grant.require(...)`; `test_grant_tamper_is_rejected`, `test_action_not_granted_is_denied` | focused test output naming both tests; `grants.py` path in changed-path inventory |
| Only the run branch can be pushed, never force | `require_push_branch` denies protected/base/out-of-prefix branches before `push_executor.push`; `PushExecutor` has no force parameter anywhere | `test_push_to_each_protected_branch_is_denied`, `test_push_outside_grant_prefix_is_denied` outcomes; grep receipt showing no `--force`/`force` push option in package |
| Draft PR/comments are idempotent and receipt-backed | kernel key dedupe + `find_open_draft_pr` + comment marker; durable receipts asserted via `KernelStore.effect_entry` | `DuplicatePrCommentTests` output; stored receipt digest quoted in node receipt |
| No merge API reachable from routine missions | `VALID_DELIVERY_ACTIONS` excludes merge; `test_merge_is_not_a_grantable_action`, `test_no_merge_surface_exists` | test output; `CONTROLLED_DELIVERY.md` "No merge authority" section |

Also record: base/final commit SHAs, changed-path list (must equal write_scope
files), the exact focused command with its output, and the rollback reference
(`git revert` of the node commits).

## 7. Out-of-scope traps (do NOT do these)

- Do NOT modify `src/hive_mind_os/github_adapter.py`, `git_adapter.py`, or
  `autonomous_os.py` — they are read-only reference surfaces for this node.
- Do NOT edit `src/hive_mind_os/cortex/__init__.py` or any other existing
  `__init__.py`; only the NEW `src/hive_mind_os/cortex/github/__init__.py`
  is yours, and it stays docstring-only.
- Do NOT touch `brain_kernel/effects.py`, `effect_outbox.py`, `contracts.py`,
  `authority.py`, or `store.py` — bind to them as-is; if they seem
  insufficient, that is an escalation condition, not a license to edit.
- Do NOT implement merge, PR close/reopen, review submission, branch
  protection writes, ruleset writes, label/assignee mutation, or force push —
  even behind a flag.
- Do NOT import `hive_mind_os.autonomous_os` from the new package (heavy
  legacy module; mirror `PROTECTED_BRANCHES` locally instead).
- Do NOT store tokens, raw request bodies containing credentials, or comment
  text in receipts; receipts carry digests and identifiers only.
- Do NOT run `python -m unittest discover`, pytest, or any repo-wide test
  pass; do not run sibling nodes' tests.
- Do NOT touch `.autopilot/**`, `conftest.py`, `pyproject.toml`,
  `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, or
  `docs/architecture/HARDENED_VISION_CONTRACT.md`.
- Do NOT rebase, squash, amend, or force-push `autopilot/delivery-420`; do
  not merge the draft PR; do not push any branch other than
  `autopilot/delivery-420`.
