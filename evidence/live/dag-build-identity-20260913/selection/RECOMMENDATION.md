# Next bounded delivery: enforce caller identity expectations in DAG build

Reviewer: `/root/delivery_curator`. Immutable subject: `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`, tree `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0`. Static read-only review; no product imports, tests, dispatchers, activation or source edits. Continuity PR177 and its qualification remain separate.

**Recommended gap: `PUBLIC-RUNTIME-500-EXPECTED-IDENTITY-BUILD-001`, version 1.** Make `hive-mind dag build` enforce the caller's supplied expected request and subject IDs before writing an output. This is a real dropped-validation-input defect, not a missing-ledger inference.

## Concrete defect and correction

`src/hive_mind_os/dag_cli.py` accepts `--expected-request-id` and `--expected-subject-id` through the common plan parser. `_PlanArguments` retains both. Validate, rounds and graph forward them; the build call at line **139** drops both. `SubjectExecutionService.build_file` at `src/hive_mind_os/subject_execution.py:124` has no parameters for them, and its validation call at line **134** omits them. The existing canonical loader at `src/hive_mind_os/dag_standard.py:146` already rejects mismatching request and subject IDs when supplied.

Static counterexample: a caller supplies a valid plan digest and canonical plan for request A/subject A, but also supplies expected request B or subject B to `dag build`. The parser accepts the expectations; neither reaches validation, so those mismatches cannot prevent output creation or replacement. The exact plan digest still protects plan bytes. This is not an authentication bypass or authority expansion claim; it is failure to enforce two explicitly offered caller constraints at a local write boundary. No executable reproduction was run in this audit.

Correction: add optional `expected_request_id` and `expected_subject_id` keyword parameters, defaulting to `None`, to `build_file`; forward both to `validate_files`, and forward the parsed CLI values into `build_file`. Reuse the existing canonical validator rather than duplicate comparison logic. Keep output validation and publication after successful identity checks. Preserve existing callers that omit either expectation.

Proposed scope: the two source files above, `tests/test_public_dag_cli.py`, `tests/test_subject_execution.py`, and a small contract clarification in `docs/execution/PUBLIC_DAG_RUNTIME.md`. No plan/schema, authority, activation, historical evidence or dispatcher changes are needed. This touches the public build boundary of BUILD-SYSTEM-200/PUBLIC-RUNTIME-500; it does not close either whole node.

Intended acceptance for the subsequent builder/qualification:

- Independently mismatched request and subject expectations fail at the public CLI with exit 2/typed blocked output, and at the service through the existing contract error; valid plan digest alone must not suppress them.
- Rejection leaves a nonexistent output absent and leaves an existing output byte-identical even with `--replace`; it creates no leftover temporary files or runtime state.
- Matching expectations succeed with exactly canonical output and correct returned identities. Omitted expectations remain compatible; either expectation can be provided independently.
- Include malformed supplied digests and preserve the existing no-overwrite, concurrent-output ownership, absolute-path, plan-substitution and inert-default-execution assertions.
- Run the focused public CLI/service/compiler tests in the isolated follow-up worktree, then normal independent/full gates for delivery. These are intended checks, not tests run by this audit.

Rollback is an ordinary revert of the separate candidate. Output artifacts created by a successful inert build are local files; the correction grants no execution, remote, credential or promotion capability.

## Alternatives compared

| Candidate | Evidence and tradeoff | Recommendation |
|---|---|---|
| Enforce build identity expectations | Static parser-to-service trace proves both accepted flags are dropped; existing validator already implements checks; current build tests supply neither flag. Small, testable fail-closed repair before output mutation. | Select first. |
| Finish generic user guide | AC-PUBLIC-GUIDE / AC-HANDOFF-GUIDE have a real gap: planned generic guide entry paths are absent, and `USER_GUIDE/00_START_HERE.md` still describes a `REPO_ROOT` bootstrap bundle and historic dispatcher. Current public runtime documentation is scattered and omits the newer operator-local execution branch. | Valuable separate documentation delivery after the boundary fix; do not rename files solely to satisfy obsolete paths. |
| Reconstruct accepted V4/current-run ledger | Exact current owner plan/generation remains unavailable. Historical fixture tests and PR177 checks cannot create missing accepted receipts for another generation. | Requires scope-to-generation reconciliation; a new status wrapper would not close it. |
| Supply frozen host/external root/activation | V4 manifest is inert; external-root custody, independent signatures, nonce reservation and live authority are external obligations. | Software cannot self-grant these. Keep typed blockers; no fake activation. |

## Twenty-node reconciliation

`V4-ACCEPTANCE-MAPPING-V1.json` is the versioned mapping, containing every V4 acceptance criterion, predecessor planned path, actual artifact, missing literal path, test method/line and extracted assertion call, plus raw Git SHA-256/byte count/object ID for **96 artifacts**. It records static coverage only; test names/counts are not passing receipts.

| Node | Actual implementation/acceptance evidence at the pin | Remaining distinction |
|---|---|---|
| BASELINE-000 | V4 plan/source-provenance tests check canonical plan, exact source bytes, subject/base/request and topology. | No accepted baseline receipt for the new owner scope. |
| DOCTOR-PREFLIGHT-005 | `activation_bundle.py`, collector and activation/collector tests check exact bytes, malformed inputs, identities, nonce/expiry and inert preparation. | Fixture trust tests do not supply an independent frozen host or deployed signer. |
| FOUNDATION-010 | `brain_kernel/store.py`, store and durability suites contain replay, transaction, idempotence and crash checks. | Exact current-generation provider qualification receipt remains external/missing. |
| PLAN-CORE-100 | `plan_lineage.py`/`plan_generation.py`; lineage/generation tests cover nested identity, stale substitution, carry-forward and complete inert material. | Receipt carry-forward is contract-specific, never from repeated node IDs. |
| RUNTIME-CONTRACTS-150 | Portable/runtime schemas and tests check closed types, decision memory, V3 durability and ownership. | Historical fixed-count ownership conditions are not a new-plan verdict. |
| BUILD-SYSTEM-200 | Compiler/workflow/planner code and tests cover lint, exact standard/topology, original prompt and inert generation. | Selected downstream public-build expectation gap remains. |
| ADAPTER-INDEX-210 | Subject/resource/registry/index modules and tests check selection, exact snapshots, invalidation and unsafe inputs. | Not evidence of every external adapter's deployment or authority. |
| WAVE-HOST-300 | Wave/host/integration modules and tests check sealing, bounded lifecycle, restart, conflict and one CAS. | Real host effects and global custody remain injected obligations. |
| TASK-REUSE-310 | `task_reuse.py` tests distinguish validated integrated reuse, active/failed/repair and changed-fingerprint invalidation. | Current accepted dependencies still needed. |
| RUNTIME-TOKEN-320 | Role/token tests cover all eight dispositions, bounded context and measured/estimated/unavailable counts. | No current-run or universal efficiency conclusion. |
| GENERIC-EXECUTOR-400 | `dag_executor.py` tests cover fake-host concurrent rounds, exact bindings, recovery, cancellation and authenticated reconciliation contracts. | Does not itself provide a live activated journal. |
| CONTROL-TOKEN-410 | Context/cache/compaction/calibration tests check exact reuse keys, failure evidence and controlled positive/negative measurements. | Fixture savings are not superiority. |
| PUBLIC-RUNTIME-500 | `dag_cli.py`, service/preparation and their tests cover absolute inspection, canonical output, inert preparation and default execution refusal. | Build drops offered identity expectations; generic user guide incomplete. |
| GENERIC-FIXTURES-600 | Three tests cover the named language/nonrepository inventory, public contracts and inert capability declarations. | Language-shaped files plus fake hosts are not native toolchain or real delivery qualification. |
| FAILURE-QUALIFICATION-610 | `test_generic_dag_failure_matrix.py` and renamed `GENERIC_DAG_FAILURE_MATRIX.md` cover concurrency, drift, hidden dependencies, mutation, host loss and integration conflict. | Bounded doubles do not prove physical custody, cross-machine failures or production effects. |
| TOKEN-BENCHMARK-620 | Token benchmark module/tests, retained JSON and renamed `TOKEN_BENCHMARK.md` cover equal controls, losing lanes and bounded token-unit savings. | Explicitly synthetic lexical-token units, not provider billing or outcome superiority. |
| QUALIFICATION-PREP-625 | Collector implementation/tests enforce exact clean candidate and bounded outside-candidate evidence preparation. | Actual current freeze and prior-node receipt envelope missing. |
| CANDIDATE-CI-627 | CI workflow/contract tests and historical raw records exist. | Needs exact current-generation frozen doctor+CI evidence; unrelated green PR is not interchangeable. |
| GENERIC-QUALIFICATION-630 | Retained V4 court and plan tests identify scope and dissent. | No accepted current-generation independent node verdict established; waiver is not a successful historical receipt. |
| HANDOFF-700 | Public runtime and PowerShell surfaces offer inert preparation; tests enforce that boundary. | Generic guide gap, current delivery grant and qualified evidence lineage remain. |

### Planned names versus actual artifacts

`tests/test_cli_dag.py` maps to the present `tests/test_public_dag_cli.py`; `docs/execution/DAG_CLI.md` maps to `PUBLIC_DAG_RUNTIME.md`. Planned failure/token documentation names map to `GENERIC_DAG_FAILURE_MATRIX.md` and `TOKEN_BENCHMARK.md`. These are static content mappings, not accepted node-requalification receipts.

`USER_GUIDE/README.md` and `USER_GUIDE/07_GENERIC_DAG_EXECUTION.md` remain absent. The V4 README/public-runtime note partly cover generic operation, but the current start guide points to the historical bootstrap workflow. Additionally the public CLI now has explicit operator-local execute/resume options, while the older note broadly describes execution as externally blocked. A guide repair should explain actual profile limits and retain default external activation rules, not turn either profile into invented authority.

Absent V3-named baseline/preflight/foundation/freeze/CI/court/handoff JSON files are not proof of absent code: these are intended evidence artifacts and may properly live outside the repository. Their acceptance must bind exact current subject/request/generation and receipts. This report does not mark any of the 20 nodes complete, restart the failed 13-node tournaments, or claim all nodes are completed.
