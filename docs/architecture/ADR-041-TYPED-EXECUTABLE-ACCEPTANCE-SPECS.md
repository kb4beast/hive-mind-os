# ADR-041: Typed Executable Acceptance Specifications

- **Status:** Adapted; independently reviewed local implementation
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening, remaining high-priority item 1
- **Prior decisions:** ADR-007, ADR-010, ADR-012, ADR-014, ADR-040
- **Capability maturity:** local, reversible, and fail-closed for repository delivery

## Context

ADR-040 made a Curator seal reject missing criterion coverage. It did not make a command
semantically relevant: a model could attach any successful command to the text of a
criterion, and the execution receipt was not evaluated against the sealed command.

The resulting boundary was inadequate for an affirmative delivery claim. A local digest
alone does not establish external receipt authorship, but it must at least bind the
declared executable predicate to the observed local receipt.

## Court record

- **Claim:** A repository delivery may assert a criterion only after the predeclared
  requested argv, its resolved executable record, and the expected outcome for that
  criterion have been independently reproduced and receipt-bound.
- **Advocate:** Orchestrator/Builder implementation. A small, one-criterion-to-one-
  command contract makes command relevance mechanically inspectable, preserves the
  original prose for human review, and prevents a Curator model from selecting the
  evidence standard after work starts.
- **Cross-examiner:** Independent Architect/Cross-Examiner. It reproduced three
  failures in the initial candidate: a forged success receipt with another argv could
  adopt; scripted compatibility mapped unrelated prose to the same command; and
  permuted specification input changed queue identity. It required receipt-level argv
  and specification binding, no legacy auto-upgrade, and canonical ordering.
- **Expert testimony:** The typed schema, canonical JSON/SHA-256 digest, command-intent
  digest, and content-addressed sandbox receipt provide deterministic local evidence
  that a declared process predicate was requested and observed. This is not testimony
  that the human prose was formalized correctly.
- **Curator:** Independent Curator review issued `adapt` after focused acceptance,
  queue, durability, worker, configuration-tamper, and adversarial receipt-binding
  tests. It retained dissent that local receipt/configuration custody is not external
  authentication.
- **Judge disposition:** `adapt` for this narrow, local, reversible operating-kernel
  tranche, after the independent Architect/Cross-Examiner review and Curator
  reproduction. The Judge independently reran `tests/test_acceptance.py` and
  `tests/test_cli_enqueue.py` (9 passed) and confirmed the larger rerun was not claimed
  after exceeding its execution budget. This is not a production or authenticated-
  security promotion.
- **Dissent:** A command can be precisely bound while still being a poor formalization
  of the intended customer outcome. The kernel cannot infer semantic adequacy from
  shell syntax. Hostile-host receipt forgery and external configuration custody remain
  separate P1 work.

## Decision

1. Each repository delivery requires at least one `acceptance-specification` contract.
   A specification contains a stable identifier, the human criterion, an exact argv,
   and the expected `succeeded` or `failed` outcome. Prose-only criteria are rejected
   before any Builder workspace is materialized.
2. Specifications are normalized by stable identifier and canonical digest. The mission,
   durable configuration, scheduler payload, and deterministic queue identity use this
   normalized set. A supplied prose criterion may be displayed, but it must match the
   same complete set and cannot choose a separate order.
3. Curator seals one `AcceptanceCheck` for each specification. Its argv, expected
   outcome, criterion, identifier, and digest must exactly match. The repository
   regression command remains a separately rejecting check; it cannot satisfy a
   criterion.
4. The Curator model does not choose acceptance commands. It may assess completeness
   while blind to the candidate, but the control plane derives checks from the supplied
   specifications.
5. A Curator acceptance receipt must contain the exact requested argv, an executed argv
   whose tail exactly matches and whose executable resolves to the requested executable,
   the typed specification identifier/digest, matching result/outcome/exit status, and
   non-truncated output. Missing or mismatched binding, timeout, unknown result, or
   truncation rejects the delivery. The acceptance-specification data is included in the
   hashed command intent and copied into the receipt execution record.
6. Older queued or durable missions that contain criteria but lack typed specifications
   cannot be resumed as a successful delivery. They fail closed and must be re-enqueued
   with explicit specification files.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Curator invents `python -c pass` for a criterion | Only supplied typed specs can create criterion checks | Author can still formalize the wrong predicate |
| Receipt says success for another command | Match requested argv, resolved executed argv, spec id/digest, result, outcome, and exit code | Local host can forge all local state before external custody exists |
| Expected failure accepts a timeout | Timeouts and missing exit codes never match | Process tier remains a soft sandbox |
| Equivalent queued work has different identity | Canonical specification ordering in semantic payload | Repository identity/custody locking remains future work |
| Old prose-only job silently gains a default checker | Constructor and Curator fail closed | Operators must re-enqueue with explicit specs |

## Migration and rollback

`hive-mind deliver` and `hive-mind enqueue` accept repeatable `--acceptance-spec FILE`
arguments. Each file is one `acceptance-specification` JSON contract. Existing
scripted/model invocations with `--criterion` but no specification are intentionally
rejected; this is a security migration, not a compatibility default. Reverting the
implementation restores the older weaker local behavior but retains all receipt and
mission data; it must not erase failed legacy missions or sealed evidence.

## Verification

- `tests/test_acceptance.py`: untyped delivery, direct Curator bypass, substituted
  command, wrong receipt argv, timeout, and truncated output all reject.
- `tests/test_curator.py` and `tests/test_mission.py`: a typed scripted/model delivery
  passes, sabotage remains closed, and Curator reproduces receipt-bound specifications.
- `tests/test_cli_enqueue.py`: specification permutations share a semantic job while
  prose-only enqueues reject.
- `tests/test_mission_store.py` and `tests/test_workers.py`: typed specifications are
  preserved through durable config, resume, and worker execution.

## Open obligations

This ADR does not authenticate configuration or receipts outside the local trusted root,
lock repository sources, resume model-backed role state, isolate hostile code or
credentials with a hard boundary, or modify external branch protection/governance.
Those remain explicitly deferred and require their own authority, evidence, and ADRs.
