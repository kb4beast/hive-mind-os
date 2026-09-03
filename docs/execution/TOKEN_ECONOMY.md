# Runtime Token Economy

Status: V3 candidate contract for `RUNTIME-TOKEN-320`.

The original role runtime made one provider call for every canonical role and
sent every earlier role body to every later role. Its legacy backend also used
an 8,000-character oldest-first truncation fallback. Static sidecar savings in
the controller were estimates. This change reduces avoidable model and context
cost while preserving all eight lifecycle accounts.

## Role accountability

Every task resolves all roles, in canonical order, to one evidence-bound
`RoleDispositionRecord`: `model_execute`, `deterministic_check`,
`not_applicable`, `deferred`, or `blocked`. No role disappears. A documentation
task has eight records but only Builder and Curator require model calls. Curator
is never not applicable. External effects retain Integrator and Steward
accountability, and recovery claims retain Steward accountability. A deferred
record requires a named trigger. A blocked record requires a reason and stops
the mission without emitting a passing result.

Non-model dispositions still create digest-verifiable `RoleResult` objects with
the normal required outputs. The disposition digest is included in
`base_artifact_refs`. This proves why a call was avoided and prevents a cheaper
path from hiding lifecycle work.

## Dependency-routed context

The declared role graph is a chain from Orchestrator through Optimizer. For a
consumer, a direct dependency is `FULL`, a transitive ancestor is `DIGEST`, and
an unrelated supplied role is `OMITTED`. Every supplied prior role is named
exactly once. Full-body deliveries therefore fall from the former quadratic 28
per eight-role mission to seven; prior result digests remain in the invocation
binding and omitted context is explicit.

`ContextCompiler` remains the only ranking, hot/warm/cold tier, provenance,
evaluator-isolation, and hard-token-budget system. A cold expansion uses
`ContextCompiler.retrieve_cold`, which creates and stores a new immutable
manifest revision. No second context store or unrecorded expansion path is
introduced. The backend character limit remains a compatibility fallback for
legacy envelope-less callers; it is not a new selection authority.

## Honest accounting

`TokenMeasurement` records input, output, and cache values independently as
`measured`, `estimated`, or `unavailable`. Provider counts are measured. Only a
known request body may use the existing `bytes-div-4` input estimate. A maximum
output limit is not observed usage, so a missing completion count remains
unavailable. Unavailable values are `null`, never zero. `TokenRecord` additionally
records role, work item, outcome, retry, call and fallback counts, context
manifest, omission count, purpose, and optional observed avoided/coordination
costs. `TokenLedger` appends these records through the existing hash-chained
evidence ledger and rejects duplicate accounting within one writer.

Calibration groups successful, usable observations by purpose and emits stable
integer medians. Fewer than five observations are `insufficient` and claim zero
observed savings rather than extrapolating. Five to nine are `provisional`; ten
or more are `calibrated`. Savings are derived only when an avoided-input
measurement exists. The canonical calibration document is product evidence;
adopting it in the sealed controller is a separate independently reviewed
controller change.

## V1 claim dispositions

| Source row | Disposition | Executable evidence |
|---|---|---|
| `V1-RUNTIME-TOKEN-320-OBJ` | Adapt | Applicability policy, routed prior context, and token records are explicit contracts. |
| `V1-RUNTIME-TOKEN-320-AC-01` | Adapt | Every role yields one of five typed, evidence-bound dispositions. |
| `V1-RUNTIME-TOKEN-320-AC-02` | Adapt without lifecycle weakening | Small tasks use fewer calls while retaining eight results. |
| `V1-RUNTIME-TOKEN-320-AC-03` | Adapt | Direct, transitive, and unrelated prior roles receive FULL, DIGEST, and OMITTED tiers. |
| `V1-RUNTIME-TOKEN-320-AC-04` | Reuse existing compiler | `ContextCompiler` and immutable manifest revisioning remain canonical. |
| `V1-RUNTIME-TOKEN-320-AC-05` | Adopt honest-accounting invariant | Measured, estimated, and unavailable values remain distinct; unavailable is never zero. |

Rollback removes the applicability/routing and accounting candidate while
retaining measurement receipts and unavailable observations for later review.
