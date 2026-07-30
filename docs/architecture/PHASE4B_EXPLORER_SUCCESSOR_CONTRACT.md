# Phase 4B Explorer successor contract

## Required invariants

- Preserve every Phase 2 canonical/generated Explorer byte, the complete generated
  manifest, Generation Zero behavior, and all Phase 3/4A contracts.
- Use new successor and definition identities; never supersede, overwrite, or
  activate the Phase 2 candidate.
- Compile ordered content-addressed layers for base, prompt, playbook, skills,
  context, output, admission, and lifecycle.
- Recompute every referenced digest from current packaged sources, compare the
  protected canonical/generated resources byte-for-byte, and fail closed on
  omission, duplication, reorder, substitution, version drift, or pin mismatch.
- Use a strict bounded contract with `additionalProperties: false` throughout.
- Preserve requested capabilities only as inherited metadata. Effective
  capabilities and tool references are empty.
- Store references and digests only: no prompt, context, repository, finding, user,
  tenant, secret, or private content body.
- Compilation performs no store write, engine/provider/tool call, registration,
  public export, runtime selection, or activation.
- Returned documents are defensive copies; mutable or reflective caller changes
  cannot alter later compilations or canonical bytes.
- Installed JSON resources remain exactly 133.

## Acceptance tests

The compiler proves semantic composition plus packaged Phase 2 byte bindings.
Source-tree and clean installed-wheel gates prove packaging preservation. Test
deterministic compilation, exact Phase 2 byte preservation, unique successor
identity, fixed layer order, base/projection/prompt/skill/schema/policy/output/
admission/lifecycle drift, missing/duplicate/extra layers, unknown fields, mutable
aliases, capability confusion, private-content absence, public/API/CLI/runtime
reachability, installed-wheel compilation, resource count, and rollback.

## Deferred

Runtime binding, new prompt prose, live repository/history/web/provider/tool access,
protected-content retrieval, semantic search, multi-turn autonomy, new memory
writers, public projection, hard token/cost/time leases, circuit breakers,
behavioral usefulness, customer value, learning, champion selection, activation,
promotion, and superiority.
