# ADR-041: Typed executable acceptance specifications

- **Status:** Adapted
- **Date:** 2026-08-03
- **Scope:** local, reversible repository delivery

## Decision

A repository delivery must receive one or more typed `acceptance-specification`
documents. Each document contains a stable identifier, a human criterion, an exact
argv, and an expected `succeeded` or `failed` outcome. A prose criterion may be
displayed, but it must exactly match the supplied specification set.

The control plane, not the Curator model, converts these specifications to sealed
acceptance checks. The seal records every specification's canonical SHA-256 digest.
The Curator's process receipt must bind the requested argv, resolved argv, specification
identifier and digest, exit status, process outcome, and non-truncated output. Any
mismatch, timeout, or missing binding rejects the delivery.

`hive-mind deliver` accepts repeatable `--acceptance-spec FILE` arguments. The files
are parsed and schema-validated before a mission starts. Durable mission configuration
retains their canonical form, so resumed work cannot silently substitute a criterion
command.

## Rationale

Prose alone cannot prove that a successful command is relevant to the promised result.
Binding the declared predicate before candidate access prevents a later model turn from
choosing an easier command and presenting it as acceptance evidence.

## Threats and limits

| Threat | Control | Residual |
|---|---|---|
| Curator substitutes `python -c pass` | Only supplied specifications create criterion checks | The author can still formalize the wrong predicate |
| Receipt claims another command ran | Requested and executed argv plus the spec id/digest are checked | A hostile local host can forge local state |
| Expected failure accepts a timeout | Timeout and missing exit code never match | The process tier is not hostile-code isolation |
| Resume changes acceptance | Canonical specification documents persist in mission configuration | External custody is deferred |

## Verification

`tests/test_acceptance.py` covers malformed inputs, prose-only delivery rejection,
exact sealed-command binding, receipt argv binding, and CLI input validation. Existing
mission, Curator, durable-resume, worker, and benchmark tests exercise propagation
through their respective paths.

## Rollback

Reverting this change restores the weaker prose-only local behavior. Existing receipts
and durable mission data remain intact and must not be rewritten or represented as
typed acceptance evidence.
