# Hive Mind OS — Detailed Implementation Action Plan

- **Status:** Proposed implementation program
- **Target product branch:** `main`
- **Purpose:** Convert the full third-party analysis into a detailed, durable implementation plan that lower-capability models can execute without silently broadening scope, authority, or claims.
- **Preservation note:** This document retains the complete action plan. Chat-specific citation markers have been converted to stable repository file references so the document remains usable in GitHub.

## Program objective

Transform Hive Mind OS from a **verification-first prototype** into a **durable, secure, outcome-driven operating system** that can:

1. Discover and prioritize real product problems.
2. Plan and execute bounded engineering work.
3. Operate all eight roles as real runtime participants.
4. Challenge and remand weak decisions without creating procedural paralysis.
5. Recover from model, worker, process, and host failures.
6. Execute untrusted repository code within a hard security boundary.
7. Measure whether delivered work created customer value.
8. Improve through governed champion/challenger experiments.
9. Earn progressively broader autonomy through evidence.

The plan preserves the project’s core rules:

- Evidence before authority.
- Missing evidence is a blocked state.
- No role may approve its own work.
- No mission or policy self-mutation.
- No live champion mutation.
- No unsupported execution, independence, production, or superiority claims.
- Every substantive run ends with a checkpoint and append-only ledger delta.

Those operating rules are consistent with the HIVE OS Classic Simulator instructions and should be made mandatory for every implementation session.

---

# Current baseline that this plan assumes

The active `main` branch presently has a credible local verification product, but repository missions only execute Explorer, Builder, and Curator. The other five roles remain planned or structural. See `src/hive_mind_os/roles.py`.

The current repository mission is still centered on reproducing one failing test, generating a candidate, and independently re-running sealed checks. See `src/hive_mind_os/mission.py`.

The current process sandbox provides useful command controls, timeouts, environment filtering, output caps, and path checks, but explicitly does not provide hard network isolation. See `src/hive_mind_os/sandbox.py`.

Durable mission support currently requires the scripted repository backend rather than the real model backend. See `src/hive_mind_os/mission.py` and `src/hive_mind_os/workers.py`.

The experiment system has a well-structured registry and promotion model, but the primary fixture evaluation surface is deliberately unavailable, and the current point-in-time surface does not yet constitute a meaningful prompt-dependent challenger evaluation. See `src/hive_mind_os/experiment_runner.py` and `src/hive_mind_os/prompt_registry.py`.

The reviewed owner authority record also keeps real-model spending, external signing, external evidence retention, a production pilot, and authenticated independent human review behind human gates. Lower models must not fabricate those inputs or mark them complete. See `docs/architecture/ADR-043-VERIFICATION-FIRST-OPEN-SOURCE-POSTURE.md`, `docs/architecture/HUMAN_AUTHORITY_GATES.md`, and `docs/plan/BLOCKERS.md`.

---

# Program-wide execution rules

These rules apply to every phase and every implementing model.

## 1. Use one active product branch

`main` should be the only active product line.

`release/version_1.1` should be retained as an architecture and evidence reference, not merged wholesale. The release branch contains substantial role, memory, telemetry, federation, Obsidian, and governance material, but much of it explicitly has no runtime authority or consumer.

A feature may be brought forward from that branch only through a new focused change that identifies:

- The current problem it solves.
- The runtime consumer.
- The user-facing effect.
- The exact files being imported or reimplemented.
- The tests proving behavior.
- Migration and rollback.
- Any inherited security or maintenance liability.

## 2. Major phases may contain multiple PRs

A major phase is not intended to be one enormous PR.

Each phase may use several implementation branches, but the phase is not complete until its end-to-end acceptance scenario passes. A collection of individually green components does not establish phase completion unless they are integrated.

Recommended structure:

```text
main
 └── program/phase-<number>-<name>
      ├── feat/<workstream-a>
      ├── feat/<workstream-b>
      ├── test/<phase-adversarial-suite>
      └── docs/<phase-operator-guide>
```

The phase integration branch should remain temporary. After the phase acceptance suite passes, merge it through the normal protected path and delete only the integration branch, not historical tags or evidence.

## 3. Tests precede implementation

For every behavior change:

1. Write or update the executable acceptance test.
2. Demonstrate that it fails for the intended reason.
3. Implement the smallest complete behavior.
4. Run focused tests.
5. Run the complete repository gate.
6. Run linting, type checks, security checks, packaging checks, and platform-specific checks.
7. Inspect the final diff for weakened assertions or broadened authority.

Do not create documentation-only substitutes for missing runtime behavior.

## 4. Every new subsystem requires a production consumer

Do not add a new:

- Registry.
- Schema family.
- Agent package.
- Memory layer.
- Projection.
- Adapter.
- Evidence format.
- Governance compiler.
- Telemetry layer.

unless the same phase wires it into an active runtime path and includes behavioral tests.

A subsystem that is intentionally reference-only must live under a clearly labeled reference or archive namespace and must not appear in the active capability matrix.

## 5. Use explicit maturity labels

Every capability must have exactly one status:

- `planned`
- `structural`
- `executable_fixture`
- `executable_local`
- `executed_real_provider`
- `independently_reproduced`
- `pilot_proven`
- `production_proven`

Do not use a generic `implemented` status that hides the difference between a schema, a fixture, and an externally verified capability.

## 6. Preserve authority boundaries

No implementing model may:

- Broaden autonomy to unblock itself.
- Remove a failing test to complete a phase.
- Change an acceptance specification after candidate access.
- Make Curator consume Builder rationale.
- Treat same-session role labels as authenticated independence.
- Create a fake signing authority.
- Add an API key or authorize spend.
- Create a production pilot without owner approval.
- Promote a challenger based only on its own evaluation.
- Merge or deploy merely because local tests passed.

## 7. Every phase produces a portable handoff

At the end of every implementation session, write a checkpoint with:

```yaml
phase:
workstream:
base_sha:
head_sha:
status: PROPOSED | EXECUTED | BLOCKED | FAILED
objective:
acceptance_tests:
tests_actually_run:
tests_not_run:
files_changed:
behavior_added:
authority_added:
authority_not_added:
receipts:
known_failures:
unresolved_dissent:
human_gates:
next_exact_action:
```

Never claim a command or test was run unless its actual output was observed.

---

# Phase overview

| Phase | Major outcome |
|---|---|
| **Phase 1 — Establish the truthful product and verification boundary** | One canonical product branch, immutable candidate verification, honest CLI, generated capability truth. |
| **Phase 2 — Build the general autonomous mission loop** | Orchestrator, Explorer, Architect, Builder, and Curator can solve multiple repository task classes through an iterative bounded loop. |
| **Phase 3 — Make real execution durable, isolated, and trustworthy** | Model missions use durable workers, hard isolation, resource-aware policy, authenticated evidence, cancellation, and operational telemetry. |
| **Phase 4 — Operationalize all eight roles and their interaction model** | All eight roles have real inputs, outputs, tools, remands, metrics, and authority boundaries. |
| **Phase 5 — Add product intelligence, real-world QA, and outcome learning** | The system learns whether it solved the right problem and measures real customer and engineering outcomes. |
| **Phase 6 — Controlled delivery, pilot operation, and governed self-improvement** | Draft delivery, canary operation, rollback, external evidence, and valid champion/challenger promotion. |

The phases are intentionally large. Within each phase, the work is organized into implementation workstreams rather than dozens of narrowly named subphases.

---

# Phase 1 — Establish the truthful product and verification boundary

## Outcome

At the end of Phase 1:

- `main` is the only active product branch.
- The public capability matrix is generated from executable code and tests.
- `hive-mind verify` verifies an immutable commit rather than a mutable working directory.
- No dirty, untracked, or concurrently modified file can influence a verdict.
- All published bundles are atomically created and self-verifiable.
- CLI names clearly distinguish simulation, verification, execution, service operation, and evaluation.
- A clean-machine user can understand exactly what the tool does and does not do.

This phase addresses the highest-risk defect from the audit before broader autonomy is added.

---

## Workstream: Canonical product line and active-capability registry

### Implementation instructions

1. Declare `main` as the canonical active branch in:
   - `README.md`
   - `CONTRIBUTING.md`
   - `AGENTS.md`
   - The active plan index.
   - The release documentation.

2. Tag the current `release/version_1.1` state as an immutable reference point.

3. Add a document describing the branch disposition:
   - Why it is retained.
   - Which assets are architecture references.
   - Which assets are prohibited from wholesale merge.
   - How individual features may be reintroduced.
   - Which plans are superseded.

4. Add an executable capability registry, for example:

```python
@dataclass(frozen=True)
class CapabilityRegistration:
    capability_id: str
    maturity: str
    entry_point: str | None
    runtime_consumer: str | None
    test_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    required_authority: str
```

5. Register active capabilities from the runtime rather than manually duplicating them in documentation.

6. Generate:
   - README capability table.
   - CLI `capabilities` output.
   - Machine-readable capability manifest.
   - Documentation page.

7. Add a CI test that fails when:
   - Documentation claims a capability absent from the registry.
   - A registry entry names a nonexistent runtime consumer.
   - A capability is marked executable without an associated behavioral test.
   - A planned capability appears in the supported CLI.

### Likely code areas

- `src/hive_mind_os/roles.py`
- `src/hive_mind_os/cli.py`
- New `src/hive_mind_os/capabilities.py`
- `README.md`
- `docs/`
- Tests for documentation/runtime parity

### Required result

A newcomer must be able to run:

```bash
hive-mind capabilities --json
```

and receive the same capability truth presented in the README.

---

## Workstream: Repair standalone immutable verification

The current verifier must stop using the caller’s live repository worktree as the execution target. The implementation currently derives changed paths from committed Git state but executes the acceptance command with the live repository as its working directory. See `src/hive_mind_os/verify.py`.

### New verification sequence

Implement the following exact order:

1. **Validate inputs without reading candidate content**
   - Validate output path.
   - Validate acceptance specification schema.
   - Validate allowed command structure.
   - Validate declared paths.
   - Validate requested candidate reference format.

2. **Seal the verification contract**
   - Acceptance specification digest.
   - Candidate reference supplied by the user.
   - Environment contract.
   - Sandbox profile.
   - Tool version.
   - Verification policy version.

3. **Resolve immutable Git objects**
   - Candidate commit SHA.
   - Candidate tree SHA.
   - Parent commit SHA.
   - Parent tree SHA.
   - Repository identity.

4. **Materialize a fresh base workspace**
   - No hard links.
   - Detached checkout.
   - Disabled hooks.
   - Isolated Git configuration.
   - No inherited credentials.
   - No user working-tree content.

5. **Materialize a fresh candidate workspace**
   - Exact candidate commit.
   - Same isolation rules as the base workspace.
   - Separate directory from base and original source.

6. **Fail closed on unsupported repository features**
   Until explicitly supported, reject:
   - Active Git submodules.
   - Git LFS pointers requiring smudge.
   - External clean/smudge filters.
   - Sparse-checkout states that change materialized content.
   - Worktrees whose exact candidate cannot be reconstructed.
   - Unsafe symlink or reparse-point layouts.
   - Repository-local hooks or configuration that could affect execution.

7. **Compute the candidate change from immutable objects**
   - Compare candidate to its declared base.
   - Record additions, modifications, deletions, renames, and mode changes.
   - Require the complete changed-path set to equal the accepted declared scope.
   - Do not ignore changed tests, fixtures, build files, or configuration.

8. **Execute acceptance checks only in the candidate materialization**
   - Never execute in the caller’s source worktree.
   - Use a scrubbed, allowlisted environment.
   - Use the selected sandbox tier.
   - Record actual executable identity.
   - Record requested and executed arguments.
   - Record output truncation.
   - Record exit code, duration, resources, and enforcement limits.

9. **Compare base and candidate tests**
   - Preserve the existing AST checks.
   - Add skip/decorator/import/fixture/configuration analysis.
   - Detect file deletion and non-Python test weakening.
   - Treat unsupported semantic analysis as `not-evaluated`, not `pass`.

10. **Run repository regression checks**
    Add one of these supported models:
    - A regression command declared in the verification contract.
    - A repository profile discovered and approved before sealing.
    - An explicit `no-regression-command` state that prevents broad claims.

11. **Build output in a temporary staging directory**
    Write:
    - Verification report.
    - Ledger.
    - Acceptance specification.
    - Base and candidate object identities.
    - Changed-path manifest.
    - Receipts.
    - Environment and enforcement manifest.
    - Tool versions.
    - Integrity manifest.

12. **Self-verify the complete bundle**
    Reopen and validate every digest and binding.

13. **Publish atomically**
    Rename the complete staging directory to the requested output path only after validation succeeds.

14. **Publish nothing on failed validation**
    Failure evidence should go to a separate explicitly named failure root and must not resemble a successful verification bundle.

### Required adversarial tests

At minimum:

- Dirty tracked file changes behavior.
- Untracked helper module changes behavior.
- Concurrent source mutation during verification.
- Candidate commit differs from working tree.
- Symlink replacement.
- Windows junction or reparse point.
- Git hook attempts execution.
- Repository configuration injects a filter.
- Environment variable changes test behavior.
- Acceptance command output is truncated.
- Acceptance process times out.
- Output publication interrupted before atomic rename.
- Declared path omits a modified fixture.
- Candidate modifies a test skip condition.
- Candidate deletes a test.
- Candidate changes a non-Python test.
- Candidate uses unsupported submodules.
- Candidate uses Git LFS pointer content.

### Definition of done

- The original source worktree may be deleted after candidate resolution and verification still completes.
- Modifying the original worktree after sealing cannot change the verdict.
- Candidate tree digest is present in the report.
- The complete bundle independently reconstructs what was verified.
- Verification tests pass on Windows and Linux.
- macOS should be included where CI budget permits.

---

## Workstream: Make the CLI truthful and consistent

### Target command model

```text
hive-mind simulate     Structural eight-role simulation
hive-mind verify       Verify an existing immutable candidate
hive-mind run          Execute one governed mission
hive-mind serve        Run durable workers
hive-mind status       Show mission and worker state
hive-mind doctor       Validate environment and configuration
hive-mind eval         Run evaluation programs
hive-mind capabilities Show active capability truth
```

### Instructions

1. Preserve old commands as deprecated aliases for one compatibility window.
2. Print an explicit warning when an alias is used.
3. Reject incompatible options before creating any state.
4. Add `--explain` to policy-sensitive commands.
5. Add preflight output showing:
   - Repository.
   - Candidate.
   - Intended role sequence.
   - Sandbox tier.
   - Network policy.
   - Model provider.
   - Estimated maximum model calls.
   - Maximum tool calls.
   - Spend ceiling when applicable.
   - Intended side effects.
6. Add `hive-mind doctor` checks for:
   - Git.
   - Python.
   - Platform support.
   - Repository health.
   - Sandbox availability.
   - Model configuration.
   - Credential environment names, without exposing values.
   - Evidence-store writeability.
   - Long-path support behavior.
   - External delivery readiness.
7. Provide human-readable output by default and machine-readable JSON through `--json`.

---

## Phase 1 exit gate

Do not begin Phase 2 until all are true:

- Immutable candidate verification passes adversarial tests.
- Original-worktree contamination is impossible in the supported path.
- Capability documentation is generated.
- `main` is the sole active product line.
- The release branch is frozen as reference.
- CLI terminology is consistent.
- A clean-machine user can run the demo and verify example.
- Complete CI passes on supported platforms.
- No current command overstates active role count or maturity.

---

# Phase 2 — Build the general autonomous mission loop

## Outcome

At the end of Phase 2, Hive Mind OS can perform bounded repository work beyond its existing hard-coded fixture model.

The system should be able to handle:

- A failing-test bug.
- A bug hidden behind green tests.
- Documentation/code drift.
- A small feature.
- A bounded refactor.
- A dependency or configuration repair.
- A compatibility change.
- A security hardening task.

The core operational lifecycle in this phase is:

```text
Orchestrator
    ↓
Explorer
    ↓
Architect when required
    ↓
Builder iterative loop
    ↓
Curator
    ↘ remand to Builder, Architect, Explorer, or Orchestrator
```

Integrator, Steward, and Optimizer become fully operational in Phase 4, but their contracts should be anticipated here.

---

## Workstream: Replace the fixed loop with a typed mission state machine

### Canonical mission states

Use a deterministic state reducer. Recommended states:

```text
INTAKE
PLANNING
DISCOVERING
DESIGNING
BUILDING
VERIFYING
INTEGRATING
OPERATING
EVALUATING

SUCCEEDED
BLOCKED
FAILED
CANCELLED
QUARANTINED
```

### Required state objects

```python
@dataclass(frozen=True)
class MissionState:
    mission_id: str
    revision: int
    objective_ref: str
    status: MissionStatus
    risk_lane: str
    work_items: tuple[WorkItemState, ...]
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    dissent_refs: tuple[str, ...]
    budgets: BudgetState
    grants: tuple[str, ...]
    active_leases: tuple[str, ...]
    current_role: str | None
    terminal_reason: str | None
```

Each state transition must be:

- Deterministic.
- Append-only.
- Revision-bound.
- Validated against an explicit transition table.
- Rejected when based on stale state.
- Independent from model prose.

### Required event types

- `mission.intake`
- `mission.planned`
- `work.created`
- `role.started`
- `role.action.proposed`
- `policy.decided`
- `tool.executed`
- `role.completed`
- `role.remanded`
- `claim.disputed`
- `court.decided`
- `budget.consumed`
- `mission.blocked`
- `mission.failed`
- `mission.cancelled`
- `mission.succeeded`

The model may propose a transition. The deterministic reducer owns whether the transition is legal.

---

## Workstream: Operational Orchestrator

The Orchestrator must become a real runtime role rather than a ledger label.

### Inputs

- Objective.
- Acceptance criteria.
- Constraints.
- Repository identity.
- Available evidence.
- Risk tier.
- Autonomy ceiling.
- Budget ceilings.
- Current blockers.
- Prior remands.
- Current mission state.

### Outputs

- Risk lane.
- Applicable roles.
- Work-item DAG.
- Dependencies.
- Evidence requirements.
- Budget allocations.
- Stop conditions.
- Rollback reserve.
- Verification reserve.
- Human gates.
- Initial handoff.

### Implementation behavior

1. Validate intake.
2. Determine whether the objective is:
   - Supported.
   - Unsupported.
   - Ambiguous.
   - Unsafe.
   - Out of authority.
3. Select a governance lane.
4. Create the smallest role sequence that can satisfy the burden.
5. Allocate explicit budgets.
6. Define phase-local stop conditions.
7. Refuse execution when acceptance criteria are not testable.
8. Replan after remand without changing the original objective or sealed acceptance contract.
9. Cancel or block when repeated remands show no progress.
10. Never implement code, approve the candidate, or evaluate its own plan as independent.

### Tests

- Missing acceptance criteria.
- Contradictory constraints.
- Exhausted budget.
- Unsupported repository.
- High-risk task selects Architect and Steward.
- Low-risk documentation task does not force every role.
- Curator remand creates revised work item without mutating prior history.
- Repeated progress fingerprint stops the loop.

---

## Workstream: Give Explorer an iterative read-only discovery loop

The current Explorer must stop guessing a single test command before repository access.

### Explorer tools

Implement typed read-only tools:

- `list_tree`
- `read_file`
- `read_file_range`
- `search_text`
- `search_symbol`
- `inspect_git_status`
- `inspect_git_history`
- `inspect_commit`
- `inspect_build_configuration`
- `run_read_only_command`
- `record_evidence`
- `propose_hypothesis`
- `request_more_evidence`
- `finish_discovery`

### Tool restrictions

Explorer must not:

- Write files.
- Change branches.
- Modify dependencies.
- Commit.
- Push.
- Open a PR.
- Change acceptance specifications.
- Access candidate output created after its discovery seal unless explicitly remanded.

### Explorer completion contract

Explorer should return:

- Ranked problem hypotheses.
- Supporting evidence.
- Conflicting evidence.
- Unknowns.
- Relevant repository paths.
- Suspected test commands.
- Alternative explanations.
- Recommended next role.
- Confidence bounded by evidence.
- Explicit reason discovery is sufficient.

### Stop conditions

- Evidence threshold met.
- Tool budget exhausted.
- No new information after a bounded number of iterations.
- Repository unsupported.
- Required external source unavailable.
- Objective appears incorrect.
- Safety or authority violation.

### Required scenarios

- Python project.
- Node/TypeScript project.
- C# project.
- Monorepo.
- Green test suite with hidden defect.
- Repository without tests.
- Multiple possible test commands.
- Misleading README instructions.
- Prompt injection embedded in repository files.

Repository text must be treated as untrusted data, not authority.

---

## Workstream: Operational Architect

Architect should run when the task has meaningful design, migration, compatibility, privacy, security, or rollback risk.

### Architect tools

Mostly read-only:

- Repository read/search.
- Interface inventory.
- Dependency graph.
- Data-flow modeling.
- Threat modeling.
- Design artifact creation.
- Acceptance mapping.

Architect should not write production code.

### Required outputs

- At least two design options when the problem materially permits alternatives.
- Explicit constraints.
- Selected design and rejected alternatives.
- Component and interface changes.
- Invariants.
- Threat model.
- Data classifications.
- Migration plan.
- Rollback plan.
- Compatibility impact.
- Acceptance-test mapping.
- Risks that remain unknown.
- Builder handoff.

### Architect remands

Architect may remand to Explorer when:

- Evidence is insufficient.
- Repository behavior is unclear.
- A required interface is missing.
- The objective conflicts with current architecture.

Curator may remand to Architect when:

- The implementation satisfies tests but violates a design invariant.
- Rollback is invalid.
- Threats are unaddressed.
- Compatibility assumptions were incorrect.

---

## Workstream: Replace one-shot Builder generation with an iterative action loop

### Builder tool set

- `read_file`
- `read_file_range`
- `search_text`
- `search_symbol`
- `apply_patch`
- `write_file`
- `delete_path`
- `move_path`
- `run_command`
- `run_tests`
- `inspect_diff`
- `inspect_status`
- `checkpoint_candidate`
- `request_architect_remand`
- `finish_candidate`

The runtime executor—not the model—must perform each action.

### Builder loop

```text
Receive bounded context
        ↓
Propose one typed action
        ↓
Policy evaluates action and resource scope
        ↓
Executor performs action
        ↓
Receipt and observation returned
        ↓
Builder updates plan
        ↓
Repeat until candidate, block, failure, or budget stop
```

### Required limits

- Maximum model turns.
- Maximum tool calls.
- Maximum files read.
- Maximum bytes read.
- Maximum files changed.
- Maximum diff size.
- Maximum command duration.
- Maximum total duration.
- Maximum token usage.
- Maximum spend.
- Maximum dependency changes.
- Maximum retry count.
- Maximum repeated semantic progress fingerprint.

### Builder rules

- Do not send entire repositories to the model by default.
- Use search and targeted reads.
- Preserve repository line endings and encodings.
- Prefer patches over full-file rewrites.
- Require explicit authorization for dependency changes.
- Reject changes outside allowed paths.
- Run tests after relevant changes.
- Inspect final diff.
- Never change sealed acceptance tests.
- Never classify its own candidate as verified.
- Preserve failed attempts as evidence.

### Required tests

- Malformed action JSON.
- Unknown tool.
- Unsupported path.
- Duplicate write.
- Patch conflict.
- Test failure followed by correction.
- Budget exhaustion.
- Model refusal.
- Model timeout.
- Provider retry.
- Builder requests Architect remand.
- Builder attempts to edit sealed test.
- Builder attempts to broaden allowed paths.
- Builder modifies unrelated file.
- Builder produces no meaningful change.

---

## Workstream: Deepen Curator without contaminating independence

Keep the existing pre-seal and fresh-workspace design.

Add:

- Candidate tree binding.
- Repository regression profile.
- Language-neutral changed-test inspection.
- Skip/decorator/configuration checks.
- Mutation testing where supported.
- Static analysis.
- Security checks.
- API compatibility checks.
- Generated counterexamples.
- Rollback execution in a disposable workspace.
- Artifact reconstruction.
- Environment parity checks.
- Explicit `not-evaluated` findings.

Curator must receive:

- Original objective.
- Sealed acceptance specifications.
- Base commit.
- Candidate commit.
- Architecture invariants.
- Allowed paths.
- Required evidence.

Curator must not receive:

- Builder hidden reasoning.
- Builder confidence.
- Builder recommendation.
- Unsealed late tests.
- A mutable candidate workspace.

### Curator verdicts

Use:

- `ADOPT`
- `REJECT`
- `REMAND_BUILDER`
- `REMAND_ARCHITECT`
- `REMAND_EXPLORER`
- `DEFER`
- `QUARANTINE`

A single generic failure is insufficient for a multi-role operating system.

---

## Phase 2 integrated acceptance scenario

The phase is not complete until one integrated scenario demonstrates:

1. Orchestrator accepts an objective.
2. Explorer inspects an unfamiliar repository.
3. Explorer identifies the correct evidence and test profile.
4. Architect produces a design because the task affects an interface.
5. Builder performs multiple model/tool turns.
6. Builder’s first attempt fails a test.
7. Builder observes the failure and corrects the candidate.
8. Curator materializes a fresh candidate.
9. Curator rejects or remands one intentionally defective candidate.
10. Builder or Architect corrects the problem.
11. Curator adopts the final candidate.
12. The output bundle proves every action and transition.
13. No remote delivery occurs.
14. The mission completes within declared budgets.

Run equivalent scenarios for several task classes, not only off-by-one fixture repair.

---

# Phase 3 — Make real execution durable, isolated, and trustworthy

## Outcome

At the end of Phase 3:

- Model-backed missions run through the durable scheduler and worker system.
- Every model turn and tool action is resumable.
- Worker loss does not duplicate adopted side effects.
- Lease loss cancels continuing work.
- Repository commands run in a hard isolation backend.
- Policy decisions include resource scope and obligations.
- Worker and receipt identities are cryptographically verifiable.
- Operational traces and metrics expose failures and costs.
- External provider, storage, signing, and pilot requirements remain blocked until humans supply authority.

---

## Workstream: Durable model-backed missions

The current restriction tying durable state to the scripted backend must be removed.

### Persisted mission information

Persist:

- Immutable objective and acceptance-contract references.
- Mission revision.
- Work-item graph.
- Role status.
- Role input and output artifact references.
- Model provider and model identifier.
- Model request digest.
- Model response digest.
- Private model state required for resume.
- Tool intents.
- Policy decisions.
- Tool receipts.
- Budget state.
- Lease state.
- Current candidate.
- Current base and tree digests.
- Current blocker.
- Remand history.
- Cancellation state.
- Terminal result.

### Public/private state separation

Use two data classes:

1. **Public operational state**
   - Digests.
   - Model metadata.
   - Actions.
   - Receipts.
   - Status.
   - Budgets.
   - Evidence references.

2. **Private resumable state**
   - Prompt content.
   - Model responses.
   - Sensitive repository excerpts.
   - Customer data.
   - Secret references.

Private state must be encrypted at rest or stored in a replaceable secure store. Public receipts should never silently contain prompt bodies or sensitive source content.

### Durable-step model

Every model call and tool action follows:

```text
record intent
    ↓
commit intent
    ↓
perform effect
    ↓
write immutable effect receipt
    ↓
adopt effect into mission state
    ↓
advance state revision
```

After a crash:

1. Read last state revision.
2. Locate any effect receipt not yet adopted.
3. Validate receipt binding.
4. Adopt it without rerunning the effect.
5. Rerun only when no valid receipt exists and the action is safe to repeat.

### Required crash tests

Terminate the worker:

- Before model request.
- After model response but before state update.
- Before tool execution.
- After tool execution but before receipt.
- After receipt but before adoption.
- After file write.
- After commit.
- After Curator seal.
- During Curator execution.
- During artifact publication.
- During remote push in a later delivery fixture.
- During queue heartbeat.
- During cancellation.

Run the crash matrix against both successful and failed missions.

---

## Workstream: Scheduler and worker hardening

### Required scheduler features

Add:

- Mission priority.
- Dependencies.
- Tenant or project identity.
- Resource class.
- Queue deadline.
- Cancellation.
- Pause.
- Resume.
- Replay generation.
- Intentional rerun of completed identical payloads.
- Poison-job quarantine.
- Operator notes.
- Dead-letter reason classes.
- Worker capability matching.
- Maximum concurrent work per repository.
- Maximum concurrent work per tenant.
- Fair scheduling.
- Queue-health metrics.

### Lease requirements

- A worker must check its lease before every side effect.
- A background heartbeat is not enough.
- Lease loss must set the mission cancellation token.
- Running child processes must be terminated.
- Provider requests should be cancelled where supported.
- External actions that cannot be cancelled must be classified before execution.
- A stale worker must not publish artifacts, push branches, open PRs, or mark success.

### Process model

Prefer separate worker processes over multiple mission threads in one interpreter.

This makes:

- Cancellation clearer.
- Resource accounting more reliable.
- Crashes more isolated.
- Worker identity more meaningful.
- Model/provider errors less likely to corrupt unrelated work.

---

## Workstream: Hard execution isolation

Create a replaceable backend interface:

```python
class ExecutionBackend(Protocol):
    def prepare(self, specification: IsolationSpecification) -> ExecutionHandle: ...
    def execute(self, handle: ExecutionHandle, intent: ToolIntent) -> ToolReceipt: ...
    def cancel(self, handle: ExecutionHandle) -> CancellationReceipt: ...
    def collect(self, handle: ExecutionHandle) -> ExecutionArtifacts: ...
    def destroy(self, handle: ExecutionHandle) -> DestructionReceipt: ...
```

### Isolation tiers

| Tier | Purpose |
|---|---|
| `process` | Trusted fixture and development fallback. |
| `container` | Default for ordinary real repositories. |
| `microvm` | High-risk or hostile-code tasks. |
| `remote_trusted_runner` | Organization-managed execution. |

### Minimum container requirements

- Fresh image or trusted image digest.
- Read-only base source.
- Writable copy-on-write workspace.
- Default-deny network.
- Explicit domain allowlist.
- No host environment inheritance.
- No Docker socket.
- No host SSH agent.
- No raw cloud credentials.
- Restricted device access.
- CPU limit.
- Memory limit.
- Process limit.
- File-size limit.
- Storage limit.
- Wall-time limit.
- Process-tree termination.
- Non-root user.
- Seccomp/AppArmor or platform equivalent where available.
- Protected receipt output outside candidate control.
- Complete teardown.

### Secret delivery

Use scoped secret leases:

- Secret value never enters the mission ledger.
- Secret is injected only into the required process.
- Secret has one purpose.
- Secret expires.
- Secret can be revoked.
- Receipt records only the secret reference and scope.
- Model context receives no secret value.
- Logs are scanned for accidental exposure before publication.

### Required adversarial suite

- Read host home directory.
- Read environment.
- Read Git credential helper.
- Connect to arbitrary internet host.
- Connect to metadata service.
- Fork bomb.
- Memory exhaustion.
- Disk exhaustion.
- Long-running child after parent exit.
- Escape through symlink.
- Escape through mounted path.
- Write to receipt store.
- Modify sandbox policy.
- Exfiltrate injected secret.
- Execute substituted binary.
- Use package manager to access network without grant.

---

## Workstream: Resource-aware policy engine

The policy request should include more than role and action.

### Policy request

```python
@dataclass(frozen=True)
class PolicyRequest:
    mission_id: str
    state_revision: int
    role: str
    action: str
    risk_tier: str
    autonomy_level: str
    repository: str | None
    resource_scope: tuple[str, ...]
    data_classification: str
    network_destinations: tuple[str, ...]
    credential_refs: tuple[str, ...]
    estimated_cost: float
    rollback_available: bool
    idempotency_class: str
    external_visibility: str
    lease_ref: str
    grant_refs: tuple[str, ...]
```

### Policy decision

```python
@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_codes: tuple[str, ...]
    obligations: tuple[PolicyObligation, ...]
    expires_at: str | None
    decision_digest: str
```

### Possible obligations

- Execute only in container tier.
- Disable network.
- Allow only approved domains.
- Redact outputs.
- Require Curator.
- Require Architect.
- Require human approval.
- Require signed worker.
- Cap cost.
- Cap duration.
- Require rollback.
- Require a second provider.
- Prevent external delivery.
- Delete private workspace after completion.

Risk tier must materially affect decisions. Merely validating that the enum exists is insufficient.

---

## Workstream: Authenticated identity and evidence custody

### Worker identity

Each worker should have:

- Stable identity.
- Key pair or workload identity.
- Signed execution receipts.
- Key rotation.
- Revocation.
- Environment and binary provenance.
- Supported capability declaration.

### Evidence custody

Add a replaceable external evidence store supporting:

- Write-once or object-lock retention.
- Content addressing.
- Retention policy.
- Independent read-back.
- Recovery after local loss.
- Export.
- Signature verification.
- Mutation and deletion detection.

The local filesystem and SQLite ledger may remain a development profile, but production claims must be blocked when external custody is absent.

### Attestation bundle

A high-trust mission bundle should bind:

- Source repository and base commit.
- Candidate commit and tree.
- Acceptance specifications.
- Policy bundle.
- Worker identity.
- Model/provider identity.
- Isolation image.
- Tool versions.
- Tool intents and receipts.
- Curator result.
- CI results.
- Delivery target when applicable.
- Final artifact digests.
- Rollback artifact.
- Outcome observations when later available.

---

## Workstream: Operational telemetry

Add traces and metrics for:

- Mission duration.
- Queue duration.
- Role duration.
- Model latency.
- Model tokens.
- Model cost.
- Tool duration.
- Tool failures.
- Policy denials.
- Remands.
- Curator rejection.
- Sandbox violations.
- Worker restarts.
- Lease loss.
- Recovery.
- Duplicate-effect prevention.
- Artifact publication.
- Evidence-store failure.
- Cancellation.
- Delivery state.

Trace IDs must correlate:

```text
mission → work item → role turn → model call → action intent
        → policy decision → tool execution → receipt → artifact
```

Prompt and response content should be opt-in and redacted. Metadata and digests should be the default.

---

## Human gates in Phase 3

Implementation may proceed with fake providers, local test identities, and local object-store emulators.

The following cannot be marked complete without human input:

| Gate | Human input required |
|---|---|
| Real model E2E | API key, approved provider, spend ceiling. |
| External signing | Non-agent-controlled signing identity. |
| External retention | Storage account, retention policy, recovery authority. |
| Real repository delivery | Repository authorization and credential scope. |
| Independent verification | Separate reviewer, organization, or authenticated execution identity. |

If a lower model reaches one of these gates, it must write a blocked checkpoint and stop that workstream.

---

## Phase 3 exit gate

- Model-backed missions use durable state.
- Workers recover after injected crashes.
- No adopted effect is duplicated.
- Lease loss stops active execution.
- Arbitrary repository commands use hard isolation.
- Network is denied by default.
- Secrets are scoped and absent from model context.
- Policy evaluates resource scope and risk.
- Receipts are signed in the supported high-trust profile.
- External evidence can be recovered after local state deletion.
- Operational traces identify every mission and action.
- Real-provider closure remains explicitly blocked until authorized if no human input exists.

---

# Phase 4 — Operationalize all eight roles and their interaction model

## Outcome

All eight roles become executable runtime roles with:

- Typed inputs.
- Typed outputs.
- Runtime consumers.
- Authority boundaries.
- Tool boundaries.
- Remand rules.
- Metrics.
- Tests.
- Explicit independence claims.
- Stop conditions.

The objective is not to run eight roles for every task. The objective is to have eight genuinely functional specialties that the Orchestrator selects according to risk and evidence burden.

---

## Role activation contract

A role is not active until all eight conditions hold:

1. Input schema exists.
2. Output schema exists.
3. Runtime executor exists.
4. Runtime consumer uses the output.
5. Tools are policy-bound.
6. Remand and failure transitions exist.
7. Behavioral tests prove substantive work.
8. Metrics expose performance and failure.

---

## Orchestrator

### Responsibilities

- Accept objectives.
- Select risk lane.
- Create work DAG.
- Allocate budgets.
- Track dependencies.
- Detect stalls.
- Replan after remands.
- Cancel or block.
- Prevent work outside authority.

### Prohibited

- Writing implementation.
- Approving its own plan as independently verified.
- Changing the mission charter.
- Expanding policy.
- Marking customer value achieved without observations.

---

## Explorer

### Responsibilities

- Repository research.
- Product and user evidence.
- Historical evidence.
- External approved research.
- Alternatives.
- Unknowns.
- Ranked opportunities.
- Point-in-time controls where required.

### Prohibited

- Repository writes.
- Candidate approval.
- Future or protected-holdout leakage.
- Treating retrieved instructions as authority.

---

## Architect

### Responsibilities

- Design options.
- Interface contracts.
- Data flows.
- Threat model.
- Privacy.
- Migration.
- Rollback.
- Compatibility.
- Acceptance mapping.

### Prohibited

- Quietly selecting an option without evidence.
- Writing production implementation.
- Accepting unresolved blocking risk.
- Approving its own design.

---

## Builder

### Responsibilities

- Implement bounded candidate.
- Use iterative tools.
- Run tests.
- Preserve failed attempts.
- Produce reversible change.
- Record evidence.
- Stop on authority or budget failure.

### Prohibited

- Editing sealed checks.
- Self-verification.
- Broadening scope.
- Merging or deploying.
- Modifying policy or champion.

---

## Curator

### Responsibilities

- Independent reconstruction.
- Sealed verification.
- Regression and counterexample checks.
- Security and provenance review.
- Artifact validation.
- Remand or reject.

### Prohibited

- Using Builder rationale as evidence.
- Creating late checks after candidate access.
- Calling procedural labels authenticated independence.
- Approving with unresolved critical findings.

---

## Integrator

### Responsibilities

- Contract compatibility.
- API and schema versioning.
- Data lineage.
- Repository and CI integration.
- Migration execution planning.
- Delivery preparation.
- Cross-system rollback.

### Prohibited

- Bypassing Curator.
- Treating local success as remote success.
- Merging without delivery grant.
- Hiding compatibility failures.

---

## Steward

### Responsibilities

- Runtime health.
- Dependency health.
- Operational readiness.
- SLOs.
- Recovery.
- Incident response.
- Evidence retention.
- Upgrade and migration safety.
- Rollback verification.

### Prohibited

- Marking unknown health as healthy.
- Deleting dissent or failure evidence.
- Executing unrestricted maintenance.
- Promoting an experiment.

---

## Optimizer

### Responsibilities

- Define metrics.
- Propose challengers.
- Run approved experiments.
- Preserve losing outcomes.
- Measure cost, latency, safety, and value.
- Request promotion court.

### Prohibited

- Live champion mutation.
- Holdout access.
- Self-evaluation as independent.
- Self-promotion.
- Changing success metrics after results.
- Expanding authority based on performance.

---

## Cross-role contracts

### Role handoff

```python
@dataclass(frozen=True)
class RoleHandoff:
    from_role: str
    to_role: str
    mission_revision: int
    objective_ref: str
    required_artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    authority_limits: tuple[str, ...]
    requested_action: str
    handoff_digest: str
```

### Remand

```python
@dataclass(frozen=True)
class Remand:
    issued_by: str
    destination_role: str
    defect_class: str
    finding_refs: tuple[str, ...]
    unchanged_contract_refs: tuple[str, ...]
    required_correction: str
    retry_budget: BudgetState
```

### Dissent

```python
@dataclass(frozen=True)
class Dissent:
    claim_ref: str
    role: str
    objection: str
    evidence_refs: tuple[str, ...]
    blocking: bool
    resolution_burden: str
```

---

## Remand matrix

| Issuing role | Destination | Typical reason |
|---|---|---|
| Explorer | Orchestrator | Objective is unsupported, ambiguous, or lower value than another problem. |
| Architect | Explorer | Missing evidence or unclear system behavior. |
| Builder | Architect | Design is not implementable within constraints. |
| Curator | Builder | Implementation defect. |
| Curator | Architect | Design invariant, threat, or rollback defect. |
| Curator | Explorer | Missing or contradictory evidence. |
| Integrator | Builder | Contract or packaging defect. |
| Integrator | Architect | Migration or compatibility design defect. |
| Steward | Integrator | Deployment or operational integration defect. |
| Steward | Orchestrator | Mission must stop, roll back, or be rescheduled. |
| Optimizer | Orchestrator | New challenger objective or process improvement proposal. |

All remands must preserve the original evidence and candidate history.

---

## Risk-adaptive governance lanes

| Lane | Work type | Required roles |
|---|---|---|
| `L0 Observe` | Read-only analysis | Explorer or selected specialist. |
| `L1 Local reversible` | Docs, fixtures, small isolated changes | Explorer, Builder, Curator. |
| `L2 Repository` | Standard code change | Orchestrator, Explorer, optional Architect, Builder, Curator. |
| `L3 High-impact` | Security, migrations, public contracts, sensitive data | Full design and verification chain including Architect, Integrator, Steward. |
| `L4 External delivery` | Push, PR, deployment | Integrator and Steward plus external grant. |
| `L5 Governed full` | Secrets, spending, production policy, irreversible action | Human authority, strong isolation, external custody, kill switch. |

A typo should not require a full courtroom. A security migration should not use the typo lane.

---

## Courtroom as a cross-cutting service

Do not make every work item pass through a theatrical court.

Invoke the court when:

- Material claims conflict.
- A source has uncertain provenance.
- A design tradeoff materially affects risk.
- Curator and Builder disagree.
- A risk acceptance decision is needed.
- A challenger promotion is proposed.
- A superiority claim is contemplated.

The court must preserve:

- Claim.
- Advocate evidence.
- Cross-examiner evidence.
- Expert findings.
- Burden.
- Dissent.
- Verdict.
- Appeal route.

A majority vote is not sufficient. Evidence burden controls the verdict.

---

## Phase 4 integrated role test

Create a controlled mission where:

1. Orchestrator plans a medium-risk interface change.
2. Explorer finds two possible root causes.
3. Architect chooses between two designs.
4. Builder implements the selected design.
5. Curator discovers a rollback flaw and remands to Architect.
6. Architect revises the rollback plan.
7. Builder updates the candidate.
8. Curator adopts.
9. Integrator discovers a compatibility issue and remands to Builder.
10. Builder corrects packaging.
11. Integrator prepares a local delivery artifact.
12. Steward simulates recovery and reports operational readiness.
13. Optimizer records baseline metrics and proposes—but does not promote—a challenger.
14. Orchestrator completes the mission.
15. Every role’s output is consumed by a later role.

The phase fails if any role only emits ceremonial output that no runtime consumer uses.

---

# Phase 5 — Product intelligence, real-world QA, and outcome learning

## Outcome

The system stops optimizing only for passing tests and starts measuring whether it solved a valuable problem.

At the end of this phase:

- Product and customer signals can become governed objectives.
- Every objective has an outcome contract.
- The system can distinguish customer value, product value, engineering quality, agent performance, and process overhead.
- Real-world evaluation covers multiple repositories, languages, and task families.
- Shadow mode compares system recommendations with human outcomes.
- False adoption and false rejection rates are measured.
- No superiority claim is permitted without a qualifying comparator court.

---

## Workstream: Product-signal intake

Create a provider-neutral signal model.

```python
@dataclass(frozen=True)
class ProductSignal:
    signal_id: str
    source_type: str
    source_locator: str
    observed_at: str
    tenant: str
    product_area: str
    user_segment: str | None
    content_ref: str
    evidence_digest: str
    privacy_classification: str
    reliability: str
    duplicate_group: str | None
```

### Initial sources

- GitHub issues.
- Pull-request review feedback.
- Support cases.
- User feedback forms.
- Product analytics.
- Error and incident telemetry.
- Feature-request records.
- Engineering-maintenance signals.
- Cost and performance regressions.

Do not connect all sources at once. Implement at least two real source adapters and keep the rest as planned capabilities.

### Signal processing

- Deduplicate related signals.
- Preserve source identity.
- Classify privacy and access.
- Extract claims.
- Identify contradictions.
- Rank by frequency, severity, affected users, strategic fit, confidence, and cost.
- Never allow ranking to silently expand execution authority.

---

## Workstream: Outcome contract

Every mission intended to create product value should have:

```python
@dataclass(frozen=True)
class OutcomeContract:
    objective_id: str
    problem_hypothesis: str
    affected_segment: str
    baseline_metric_refs: tuple[str, ...]
    target_metrics: tuple[MetricTarget, ...]
    guardrails: tuple[MetricTarget, ...]
    observation_window: str
    expected_behavior_change: str
    engineering_acceptance_refs: tuple[str, ...]
    rollback_trigger_refs: tuple[str, ...]
```

### Distinguish five outcome layers

| Layer | Question |
|---|---|
| Customer | Did the user’s problem improve? |
| Product | Did behavior, adoption, retention, or task completion improve? |
| Engineering | Is the change correct, secure, maintainable, and reversible? |
| Agent | Did the roles solve the task efficiently and reliably? |
| Process | Did governance add more value than cost? |

A mission may pass engineering checks and still fail customer or product outcomes.

---

## Workstream: Outcome ledger

Add append-only observations after delivery:

- Recommendation.
- Expected outcome.
- Actual outcome.
- Confidence.
- Measurement method.
- Observation window.
- Known confounders.
- User feedback.
- Rollback or follow-up.
- Lessons.
- Whether the original hypothesis held.

Do not overwrite the original prediction with the observed result.

---

## Workstream: Real-world evaluation corpus

### Minimum initial corpus

Use an initial target such as:

- At least five repositories.
- At least three languages or build systems.
- At least six task families.
- At least three repeated runs per system configuration.
- At least one Windows-dependent task.
- At least one security task.
- At least one recovery task.
- At least one green-tests hidden bug.
- At least one feature task.
- At least one compatibility or migration task.

These are program targets, not claims about current evidence.

### Task families

- Bug repair.
- Hidden edge case.
- Feature implementation.
- Refactor.
- Documentation/code alignment.
- Dependency update.
- API migration.
- Security hardening.
- Performance regression.
- Packaging failure.
- Cross-platform defect.
- Recovery from interruption.

### Evaluation separation

Maintain:

1. Development cases visible to implementers.
2. Hidden held-out cases inaccessible to Builder and Optimizer.
3. Safety cases.
4. Recovery cases.
5. Customer-outcome cases.
6. Comparator cases.

Protected holdout details must not enter normal mission context.

---

## Workstream: Comparator program

Do not compare only against an intentionally weak in-repository baseline.

Use multiple comparators representing materially different approaches:

- A simple deterministic baseline.
- A single-agent coding baseline.
- A contemporary agent framework.
- A human-assisted workflow where measurable.

Equalize:

- Task access.
- Repository state.
- Tool authority.
- Model class.
- Budget.
- Time.
- Network.
- Retry rules.
- Acceptance tests.
- Evaluation environment.

Retain:

- Raw results.
- Failed attempts.
- Losing results.
- Cost and latency.
- Safety violations.
- Confidence intervals.
- Environment manifest.

No marketing superiority claim may be made before independent review.

---

## Workstream: Expand QA beyond unit tests

### Property and fuzz testing

Apply to:

- Canonical JSON.
- Digests.
- Portable paths.
- State transitions.
- Policy decisions.
- Receipt bindings.
- Scheduler idempotency.
- Mission replay.
- Model output parsing.
- Provider responses.

### Mutation testing

Prioritize:

- `verify.py`
- `curator.py`
- `policy.py`
- `mission_store.py`
- `scheduler.py`
- `workers.py`
- Receipt validation.
- State reducer.

A green test suite that survives mutation of critical branches is not strong enough.

### Concurrency testing

- Multiple schedulers.
- Multiple workers.
- Same repository.
- Same mission payload.
- Lease expiration.
- Cancellation races.
- Evidence-store contention.
- Duplicate external action attempts.

### Usability testing

Test with a user unfamiliar with the repository:

- Install.
- Run doctor.
- Run demo.
- Write acceptance spec.
- Verify candidate.
- Interpret rejection.
- Recover a failed mission.
- Find receipts.
- Understand what was not enforced.

Record confusion and task-completion time as product data.

---

## Workstream: Shadow mode

Before autonomous delivery:

1. Run the system in read-only recommendation mode.
2. Compare its problem selection with human selection.
3. Compare its design with the actual implemented design.
4. Compare its proposed candidate with human changes.
5. Compare Curator findings with human code review.
6. Record where it:
   - Found a missed problem.
   - Proposed an invalid change.
   - Over-governed a trivial task.
   - Missed customer context.
   - Saved time.
   - Created additional work.
7. Do not use shadow results to silently grant more authority.
8. Use them as evidence for explicit autonomy promotion.

---

## Phase 5 exit gate

- Real product signals can create governed objectives.
- Every pilot objective has an outcome contract.
- Multiple real repository task families are evaluated.
- False adoption and rejection are measured.
- Costs and latency are recorded.
- Shadow-mode results exist.
- At least one external or human calibration pass occurs.
- Protected holdouts remain sealed.
- No current system is called superior without a qualifying court.
- The system can identify when technically correct work produced no customer value.

---

# Phase 6 — Controlled delivery, pilot operation, and governed self-improvement

## Outcome

At the end of Phase 6:

- Hive Mind OS can prepare and, when explicitly authorized, deliver changes through a governed external path.
- Production or pilot authority is graduated rather than assumed.
- Rollback and incident handling are operational.
- Champion/challenger experiments use real prompt-dependent evaluations.
- Promotion is independently judged.
- Stable or production positioning is supported by external evidence rather than repository-local labels.

---

## Workstream: Controlled GitHub delivery

The repository already contains substantial GitHub delivery machinery, but it should be connected to the durable real-model mission rather than treated as a separate capability.

### Delivery sequence

1. Curator adopts exact candidate tree.
2. Integrator verifies:
   - Candidate tree.
   - Base branch.
   - Expected repository.
   - Contract compatibility.
   - Required CI checks.
   - Branch-protection requirements.
3. Policy evaluates the exact external action.
4. Human or external grant is obtained when required.
5. Worker verifies lease immediately before push.
6. Push a mission-specific branch.
7. Verify remote head equals adopted candidate head.
8. Open draft PR.
9. Observe CI.
10. Bind CI result to exact remote head.
11. Curator may review new external evidence.
12. Steward records delivery health.
13. Merge remains a separate, higher-authority action.
14. Deployment remains separate from merge.

### Initial authority ladder

| Level | External behavior |
|---|---|
| Observe | Read repository and PR metadata. |
| Advise | Produce proposed patch and PR text. |
| Sandbox | Create local bundle only. |
| Repository | Create local commit or controlled branch. |
| Delivery-1 | Push branch and open draft PR. |
| Delivery-2 | Mark PR ready after checks. |
| Delivery-3 | Merge with explicit grant. |
| Production | Deploy through approved environment promotion. |

Do not jump directly from local candidate generation to autonomous merge.

---

## Workstream: Pilot operation

Select a pilot only after the owner provides:

- Approved repository.
- Data classification.
- Model provider.
- Spend ceiling.
- Delivery authority.
- Rollback authority.
- Pilot users.
- Incident contact.
- Success metrics.

### Recommended pilot order

1. Read-only code review.
2. Documentation or test-only changes.
3. Low-risk local code changes.
4. Draft PR creation.
5. Non-production merge with approval.
6. Shadow deployment.
7. Canary deployment.
8. Broader production only after repeated evidence.

### Pilot requirements

- Every mission can be cancelled.
- Every change can be rolled back.
- No secrets reach the model.
- No uncontrolled network.
- User-visible outcome is measured.
- Failures are retained.
- Human overrides are recorded.
- Incident freeze immediately blocks new delivery.
- A pilot failure does not automatically become a system-wide stop, but it must affect the applicable competency scope.

---

## Workstream: Steward production operations

Implement:

- Mission SLOs.
- Worker SLOs.
- Evidence-store SLOs.
- Queue latency SLOs.
- Recovery SLOs.
- Delivery failure SLOs.
- Cost budgets.
- Error budgets.
- Alerting.
- Incident severity.
- Rollback runbooks.
- Provider outage runbooks.
- Evidence corruption runbooks.
- Credential compromise runbooks.
- Sandbox failure runbooks.
- Model regression runbooks.
- Global kill switch.
- Per-tenant freeze.
- Per-repository freeze.
- Per-provider freeze.

A production-ready system must prove that it can stop safely, not merely that it can keep running.

---

## Workstream: Real champion/challenger evaluation

### Challenger lifecycle

1. Optimizer proposes a challenger artifact.
2. Challenger is immutable and versioned.
3. Parent champion remains active and unchanged.
4. Evaluation contract is sealed.
5. Development evaluations run.
6. Protected held-out evaluations run through a separate custodian.
7. Safety and policy tests run.
8. Cost and latency are compared.
9. Results are independently judged.
10. Verdict is one of:
    - `KEEP`
    - `RETEST`
    - `DISCARD`
    - `QUARANTINE`
    - `STOP`
11. Promotion requires a separate recorded action.
12. Rollback pointer is retained.

### Required causal validity

The evaluation must actually use the prompt, skill, workflow, model-routing policy, or code artifact under test.

A challenger evaluation is invalid when:

- Both lanes execute identical scripted behavior.
- The evaluator ignores the challenger content.
- Builder sees protected holdouts.
- Optimizer changes metrics after results.
- Challenger evaluates itself.
- Losing runs are discarded.
- Different budgets are used.
- Champion is modified during evaluation.
- Promotion occurs before independent judgment.

### Promotion thresholds

Define these before evaluation:

- Primary effect threshold.
- Noise floor.
- Minimum repetitions.
- Safety guardrails.
- Regression guardrails.
- Cost guardrails.
- Latency guardrails.
- Maximum failure rate.
- Required task-family coverage.
- Required independent reproduction.

Do not promote based on one favorable result.

---

## Workstream: External review and release posture

Before a stable or production-positioned release:

- Independent reviewer reproduces installation.
- Independent reviewer reproduces verification.
- Independent reviewer inspects sandbox claims.
- Independent reviewer validates evidence signatures.
- Independent reviewer reproduces at least one real mission.
- Known blockers are published.
- Security policy exists.
- Supported platforms are explicit.
- Upgrade and migration policy exists.
- Backward compatibility is documented.
- Deprecation policy exists.
- Incident contact exists.
- Release artifacts have SBOM and provenance.
- Release notes distinguish current capability from target architecture.

---

## Phase 6 exit gate

Hive Mind OS may only be called a production-capable autonomous product-development system when:

- Immutable verification is independently reproduced.
- Real model missions are durable.
- Hard isolation passes adversarial testing.
- All active roles have substantive runtime behavior.
- Customer outcomes are measured.
- Delivery uses explicit external authority.
- Rollback is operational.
- External evidence custody is active.
- Signed identities are active.
- A controlled pilot has completed.
- Champion/challenger promotion has been independently reproduced.
- No critical blocker remains.
- Production claims are adjudicated separately from repository-local green tests.

---

# Human authority gates

These must remain visible throughout the plan.

| Gate | Lower model behavior |
|---|---|
| API key and model spending | Implement configuration and fake-provider tests. Stop before real spend unless owner authorizes it. |
| External signing identity | Implement interface and local test signer. Do not claim authenticated identity until a human-controlled key exists. |
| External evidence retention | Implement adapter and emulator. Do not claim durable external custody until an account and recovery test exist. |
| GitHub delivery authority | Prepare draft-only path. Do not push, merge, or deploy without exact repository authority. |
| Production pilot | Prepare pilot plan and runbooks. Do not recruit users or deploy without owner approval. |
| Independent reviewer | Preserve the requirement. Same-session role simulation is not independent human review. |
| Comparator licensing | Preserve pinned source and license evidence. Do not execute or copy unauthorized comparator material. |
| Customer data access | Implement data-classification and adapter boundaries. Do not ingest sensitive customer data without approval. |

---

# Program-level definition of done

The complete program is successful when an independent user can:

1. Install Hive Mind OS on a clean supported system.
2. Run `doctor` and understand all supported and unsupported capabilities.
3. Verify an immutable agent-authored commit without live-worktree contamination.
4. Run a real model-backed mission against an unfamiliar repository.
5. Observe Explorer gather evidence before choosing a test strategy.
6. Observe Builder use a bounded iterative tool loop.
7. Observe Curator independently reconstruct and remand a defective candidate.
8. Kill the worker and resume without duplicated adopted effects.
9. Confirm repository code cannot access unauthorized host files or networks.
10. See all eight roles perform substantive work when applicable.
11. Trace every role, action, policy decision, receipt, and artifact.
12. Measure whether the change improved an actual user or product outcome.
13. Produce a draft delivery through explicit authority.
14. Roll back a failed pilot safely.
15. Run a real champion/challenger experiment whose result depends on the challenger.
16. Reproduce the promotion decision independently.
17. See known limitations and blockers without inflated claims.

---

# Lower-model implementation prompt template

Use the following for each major phase or workstream:

```text
You are implementing one bounded workstream of the Hive Mind OS action plan.

ACTIVE PHASE:
<phase name>

WORKSTREAM:
<workstream name>

OBJECTIVE:
<exact user-visible or runtime behavior>

SOURCE OF TRUTH:
- latest origin/main
- AGENTS.md
- README.md
- docs/plan/BLOCKERS.md
- the controlling action-plan phase
- applicable ADRs and schemas
- existing behavioral tests
- HIVE OS truthfulness and role-pass instructions

NON-NEGOTIABLE RULES:
1. Do not work on a later phase.
2. Do not merge release/version_1.1 wholesale.
3. Do not add an inactive subsystem.
4. Do not weaken tests, policy, evidence, or claims.
5. Do not mutate mission or policy authority.
6. Do not represent same-session role simulation as independent verification.
7. Do not claim commands or tests ran unless you observed their output.
8. Preserve failed attempts, dissent, and unresolved blockers.
9. Use typed contracts at trust boundaries.
10. Keep all side effects behind policy, lease, receipts, and rollback.
11. Stop at human authority gates rather than fabricating inputs.

EXECUTION ORDER:
1. Confirm clean latest main and record the exact base SHA.
2. Read the relevant existing implementation and tests completely.
3. Reproduce the current behavior.
4. Write the acceptance tests first.
5. Confirm the new test fails for the intended reason.
6. Implement the smallest complete production behavior.
7. Run focused tests.
8. Run the complete repository test gate.
9. Run lint, type, security, packaging, and supported platform checks.
10. Inspect the final diff for scope, weakened assertions, broadened authority, secret exposure, and inactive code.
11. Produce a PR-ready change summary.
12. Produce a RUN CHECKPOINT and LEDGER DELTA.

REQUIRED OUTPUT:
- Current-state findings
- Exact files changed
- Behavior implemented
- Tests added
- Commands actually run and outputs
- Tests not run
- Security and authority impact
- Migration and rollback
- Known limitations
- Unresolved dissent
- Human gates
- Exact next eligible action

COMPLETION RULE:
The workstream is complete only when its executable acceptance criteria pass. Documentation, schemas, or generated role text alone do not establish completion.
```

---

# Recommended exact starting point

Begin with **Phase 1, immutable standalone verification**.

The first implementation objective should be:

> Change `hive-mind verify` so it seals the acceptance contract, resolves an immutable candidate commit, materializes fresh isolated base and candidate workspaces, runs all checks only against the candidate materialization, binds the verdict to the commit and tree, and atomically publishes a self-verifying receipt bundle. Add adversarial tests proving dirty, untracked, and concurrently modified source-worktree bytes cannot influence the result.

Nothing in later phases should be activated until that verification boundary is trustworthy.
