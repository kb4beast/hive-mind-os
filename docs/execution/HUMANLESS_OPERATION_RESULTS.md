# Humanless operation results (HUMANLESS-430)

## Purpose

This node qualifies humanless operation against the four acceptance criteria:
(1) every role-resolvable question is answered by role consultation or retained
deterministic evidence; (2) software defects create repair work rather than
human questions; (3) only genuine authority classes produce a human escalation
packet; and (4) the mission resumes after interruption without any human
restating context. Qualification is executable, not narrative: five situation
classes are re-run through already-merged kernel surfaces
(`hive_mind_os.brain_kernel.consultation`, `.reconciler`, `.workers`,
`hive_mind_os.scheduler`) plus the `tests/hive_cortex/acceptance_harness.py`
run validator, and the resulting rows are digest-bound into a retained
evidence packet.

## Scenario table

| Situation class | Kernel mechanism | Decision / repairs | Human questions asked |
|---|---|---|---|
| ambiguity | `ConsultationLoop.append` → `evaluate_consultation` (`AMBIGUOUS_DESIGN`) | `RESOLVED`, answer carried by a role | 0 |
| missing tests | `evaluate_consultation` (`MISSING_EVIDENCE`) over the `no-test-csharp` fixture | `REMAND` (repair work) | 0 |
| design tradeoff | `evaluate_consultation` (`AMBIGUOUS_DESIGN`) with divergent role proposals | `REPLAN`, dissent retained | 0 |
| CI repair | `DesiredStateReconciler.reconcile` over a retryable provider failure | `retry:WORK-ci` (attempt 1 of 3) | 0 |
| recoverable interruption | `DesiredStateReconciler.reconcile` over an expired lease, missing workspace, interrupted verification | `release-stale-lease:LEASE-resume`, `rebuild-workspace:WS-resume`, `remand:WORK-resume` | 0 |

`RepairKind` has exactly six members — `release-stale-lease`, `retry`,
`remand`, `rebuild-workspace`, `rollback`, `quarantine` — and no member names a
human, a question, or an escalation. Exhausted retry budgets and repeated
no-progress quarantine **inside** the system; they do not open a human channel.

## Genuine-authority classes

Two distinct vocabularies are checked by two distinct layers. The kernel
adjudicator validates `AUTHORITY_CLASSES`; the acceptance-run validator
validates `GENUINE_HUMAN_AUTHORITY`. They are not aliases and are deliberately
not mapped in code.

| Kernel `AUTHORITY_CLASSES` (consultation.py) | Harness `GENUINE_HUMAN_AUTHORITY` (acceptance_harness.py) |
|---|---|
| `credential_or_secret` | `credential` |
| `legal_or_regulatory` | `legal` |
| `financial_spend` | `financial` |
| `production_access` | `production-access` |
| `protected_branch_merge` | `protected-branch` |
| `owner_value_choice` | `owner-value` |
| `personal_consent` | `consent` |
| `external_contractual_commitment` | `external-contract` |

All eight kernel classes escalate to `TRUE_AUTHORITY_REQUIRED` when evidence is
present. An unknown class is rejected at `ConsultationRequest` construction; an
authority claim without retained evidence yields `BLOCKED_EVIDENCE`, not
escalation; an assessment claiming `authority_required` on a request with no
authority class also yields `BLOCKED_EVIDENCE`. `ConsultationResult` rejects any
attempt to keep `human_escalation` while relabelling the decision, or to drop
the authority class from an escalation.

## Evidence index

| File | Producer |
|---|---|
| `evidence/autonomy/humanless/humanless-qualification.json` | `python -m tests.hive_cortex.test_humanless_operation --write-evidence` |
| `evidence/autonomy/humanless/receipts/focused-tests.txt` | verbatim capture of the three focused commands below |
| `evidence/autonomy/humanless/receipts/commands.json` | command / exit-code / branch / base-commit records |

Packet `scenario_digest`:
`sha256:be7ce31e6bbaa820eb5ded19b1e3140c05c4394cc4b8684fefb59b31aa85e46b`
(over the five scenario rows; every row carries `"human_escalation": false`).

## How to re-verify

Run from the repository root:

```
A: python -m unittest tests.hive_cortex.test_humanless_operation -v
B: python -m unittest tests.hive_cortex.test_humanless_operation.GenuineAuthorityClassificationSuiteTests -v
C: python -m unittest tests.hive_cortex.test_humanless_operation.SoftwareDefectNotHumanSuiteTests -v
```

Prefix each with `PYTHONPATH=src` unless `hive_mind_os` is already importable
from this working tree.

Then regenerate the packet and confirm the file is byte-identical:

```
python -m tests.hive_cortex.test_humanless_operation --write-evidence
git diff --exit-code -- evidence/autonomy/humanless/humanless-qualification.json
```

`test_retained_evidence_packet_matches_recomputation` performs the same check
in-process: it loads the retained JSON, compares it to a fresh
`build_qualification_packet()`, and re-derives `scenario_digest` from the
loaded scenarios. The retained packet is therefore never hand-authored — it is
the recorded output of the code path it documents.
