# Controlled GitHub delivery (DELIVERY-420)

`src/hive_mind_os/cortex/github/` is the **entire** remote authority surface a
routine mission can reach. It is three adapters behind one immutable grant,
bound to the canonical kernel effect path
(`EffectIntent` -> `EffectGateway` / `DurableEffectOutbox` -> `EffectReceipt`).
It adds no merge authority of any kind.

| Module | Responsibility |
|---|---|
| `grants.py` | `DeliveryGrant` — frozen, digest-sealed authorization; `PROTECTED_BRANCHES`; `VALID_DELIVERY_ACTIONS` |
| `rest_gateway.py` | `ControlledRestGateway` — four REST calls only (find draft PR, create draft PR, list comments, post comment) |
| `delivery_adapter.py` | `ControlledGitHubDelivery` — the three kernel adapters `github-push`, `github-draft-pr`, `github-comment` |

Modules are imported by full path, e.g.
`from hive_mind_os.cortex.github.delivery_adapter import ControlledGitHubDelivery`.
The package `__init__.py` is docstring-only and re-exports nothing.

## 1. Issue a grant

No grant, no remote action. A grant names one repository, one base branch, one
run-branch prefix, and an explicit action list.

```python
from hive_mind_os.cortex.github.grants import DeliveryGrant

grant = DeliveryGrant.issue(
    grant_id="GRANT-delivery-420",
    owner="octo",
    repository="repo",
    base_branch="main",
    branch_prefix="autopilot/",
    allowed_actions=("push", "open_draft_pr", "post_comment"),
    issued_at="2030-01-01T00:00:00Z",
)
```

`issue` seals every other field into `grant_digest`. `DeliveryGrant` is a
frozen dataclass whose `__post_init__` recomputes that digest and raises
`DeliveryGrantError` on any mismatch, so a mutated copy cannot be
reconstructed and passed off as authorized.

## 2. Wire the adapters onto the kernel

```python
from hive_mind_os.brain_kernel.effects import EffectGateway
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.cortex.github.delivery_adapter import ControlledGitHubDelivery
from hive_mind_os.cortex.github.rest_gateway import ControlledRestGateway

rest = ControlledRestGateway("octo", "repo", token_env="GITHUB_TOKEN")
delivery = ControlledGitHubDelivery(grant, rest=rest, push_executor=executor)

gateway = EffectGateway(store=KernelStore(store_path))
delivery.register_with(gateway)   # registers exactly three adapter names
```

`push_executor` satisfies the `PushExecutor` protocol: `push(branch) -> str`
returning the full 40-hex head SHA. The protocol has **no force parameter and
no ref-spec parameter anywhere**, so a force push cannot be expressed.

## 3. Build an intent

`EffectIntent` carries only `parameters_digest`, never raw parameters. Bind the
parameters first and use the returned digest:

```python
parameters_digest = delivery.bind_parameters({"branch": "autopilot/delivery-420"})
intent = EffectIntent(
    ...,
    action="push",
    target_adapter=ControlledGitHubDelivery.PUSH_ADAPTER,
    target="github/octo/repo",
    parameters_digest=parameters_digest,
    ...,
)
gateway.execute(intent, capability_token)
```

The capability token must bind the same `action` and `target` as the intent
(`effects.validate_capability_token`), and `target` must equal
`github/<owner>/<repository>` from the grant.

Adapter return values are the mapping shape `DurableEffectOutbox.execute`
folds into `build_effect_receipt`:
`{"produced_identifiers": (...), "postcondition_digest": "sha256:..."}`.
Receipts therefore carry identifiers and digests only — never tokens, request
bodies, or comment text.

## 4. Denial matrix

| Condition | Raised | Remote call reached? |
|---|---|---|
| Action absent from `grant.allowed_actions` | `DeliveryGrantError` | no |
| Intent `target` is not the granted repository | `DeliveryGrantError` | no |
| `parameters_digest` was never bound | `DeliveryParametersUnbound` | no |
| Push branch in `PROTECTED_BRANCHES` (`main`, `master`, `staging`) | `DeliveryGrantError` | no |
| Push branch equals `grant.base_branch` | `DeliveryGrantError` | no |
| Push branch outside `grant.branch_prefix` | `DeliveryGrantError` | no |
| Grant fields tampered with (digest mismatch) | `DeliveryGrantError` | no — construction fails |
| Missing token environment variable | `DeliveryRestError` | no — checked before transport |
| Push executor returns a non-40-hex SHA | `DeliveryRestError` | push already happened; outcome fails closed |
| Invalid / non-draft / malformed REST response | `DeliveryRestError` | yes, then fails closed |

Under a durable gateway every one of these becomes
`EffectReconciliationRequired` and the outbox entry moves to
`reconciliation_required` with **no receipt recorded**. Nothing is silently
retried.

## 5. Idempotency layers

Three independent layers, deliberately not collapsed into one:

1. **Kernel key dedupe** — `EffectGateway` / `DurableEffectOutbox` key on
   `intent.idempotency_key` and `intent.intent_digest`. A repeated intent
   returns the prior `EffectReceipt` and never calls the adapter again. This is
   *not* reimplemented in this package.
2. **Lookup before create** — `find_open_draft_pr(branch, base)` returns an
   existing open draft PR, and the adapter reuses it instead of POSTing.
3. **Comment marker** — each comment is suffixed with
   `<!-- hive-effect:<idempotency_key> -->`. Before posting, the adapter scans
   existing comments for that marker and adopts the existing comment if found.

Layers 2 and 3 cover the cross-process case where a duplicate arrives under a
fresh intent (for example after a host replacement), which layer 1 cannot see.

## 6. No merge authority

This is a structural property, not a policy setting:

- `VALID_DELIVERY_ACTIONS` is `{"push", "open_draft_pr", "post_comment"}`.
  `DeliveryGrant.issue` rejects any other action name, so `"merge"` is not
  merely denied — it is **ungrantable**. A grant carrying it cannot be built.
- `ControlledRestGateway` defines no merge, close, reopen, review-submission,
  label/assignee, branch-protection-write, or ruleset-write method. The only
  paths it ever forms are `/pulls`, `/pulls?state=open&...`, and
  `/issues/{n}/comments`.
- `ControlledGitHubDelivery` exposes exactly three adapter callables and
  registers exactly three adapter names. There is no fourth to register.
- `PushExecutor` cannot express a force push or a protected ref.

`tests/test_hive_cortex_delivery.py::ProtectedBranchDenialTests` asserts all of
this: `test_merge_is_not_a_grantable_action` and `test_no_merge_surface_exists`
(which also scans the package source for `--force`, `force_push`, `/merge`,
`merge_method`, and `/merges`).

## 7. Verification

```
python -m unittest tests.test_hive_cortex_delivery -v
```

Every test is in-process. The HTTP seam is a scripted `FakeTransport` that
raises on any unscripted request, and the push seam is a `FakePushExecutor`
that only records branch names. No socket is opened, no credential is read
from the real environment, no git command runs, and no GitHub API is
contacted.
