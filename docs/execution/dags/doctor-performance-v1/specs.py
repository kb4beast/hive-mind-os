"""Immutable node specifications for doctor-performance-v1."""

from __future__ import annotations


AUTOPILOT_TESTS_EXCEPT_HEALING = [
    ".autopilot/tests/test_attended_host.py",
    ".autopilot/tests/test_blocker_protocol.py",
    ".autopilot/tests/test_controller.py",
    ".autopilot/tests/test_dag_standard.py",
    ".autopilot/tests/test_dispatch_wave_selection.py",
    ".autopilot/tests/test_durable_completion.py",
    ".autopilot/tests/test_explorer_receipt_retirement.py",
    ".autopilot/tests/test_fixture_isolation.py",
    ".autopilot/tests/test_host_execution.py",
    ".autopilot/tests/test_orchestration.py",
    ".autopilot/tests/test_post_merge_repair.py",
    ".autopilot/tests/test_release_barrier.py",
    ".autopilot/tests/test_round_driver.py",
    ".autopilot/tests/test_sealed_recovery_bootstrap.py",
    ".autopilot/tests/test_sidecar_execution.py",
    ".autopilot/tests/test_singleton_release_target.py",
    ".autopilot/tests/test_stale_remote_claim.py",
    ".autopilot/tests/test_status_performance.py",
    ".autopilot/tests/test_workflow_policy.py",
]


SPECS = [
    {
        "id": "DP-CONTRACT-000",
        "title": "Seal the invocation-scoped fixture contract",
        "objective": (
            "Preserve the Judge's ADAPT disposition as a separate, additive, sealed "
            "predecessor contract without changing the doctor controller or production code."
        ),
        "rationale": (
            "The knowledge baseline is blocked by measured runtime, while changing the "
            "180-second doctor timeout would weaken the existing gate. The contract must "
            "therefore precede every implementation or benchmark claim."
        ),
        "dependencies": [],
        "primary_role": "architect",
        "consulted_roles": ["orchestrator", "optimizer", "curator", "steward"],
        "required_inputs": [
            "AGENTS.md",
            "docs/execution/DAG_AUTHORING_STANDARD.md",
            "git-object:6bc343f079be6f2d5fd6953d92099a8d5de872b1:evidence/knowledge-projection/baseline.json",
        ],
        "expected_outputs": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            "docs/execution/dags/doctor-performance-v1/README.md",
            "docs/execution/dags/doctor-performance-v1/specs.py",
            "docs/execution/dags/doctor-performance-v1/generate_plan.py",
            "docs/execution/dags/doctor-performance-v1/verify_plan.py",
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            "docs/execution/dags/doctor-performance-v1/manifest.json",
            "docs/execution/dags/doctor-performance-v1/.gitignore",
            "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
        ],
        "read_scope": [
            "AGENTS.md",
            "docs/execution/DAG_AUTHORING_STANDARD.md",
            ".autopilot/bin/controller.py",
            ".autopilot/tests/test_fixture_isolation.py",
            ".autopilot/tests/test_healing.py",
            "docs/execution/dags/knowledge-projection-v1/verify_plan.py",
            "docs/execution/dags/knowledge-projection-v1/manifest.json",
        ],
        "write_scope": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            "docs/execution/dags/doctor-performance-v1/README.md",
            "docs/execution/dags/doctor-performance-v1/specs.py",
            "docs/execution/dags/doctor-performance-v1/generate_plan.py",
            "docs/execution/dags/doctor-performance-v1/verify_plan.py",
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            "docs/execution/dags/doctor-performance-v1/manifest.json",
            "docs/execution/dags/doctor-performance-v1/.gitignore",
            "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
        ],
        "required_tests": [
            "python docs/execution/dags/doctor-performance-v1/verify_plan.py",
            "python docs/execution/dags/doctor-performance-v1/benchmark.py self-test",
            "python docs/execution/dags/knowledge-projection-v1/verify_plan.py",
        ],
        "acceptance_criteria": [
            "The exact six-node dependency graph and every Judge amendment are sealed.",
            "The doctor timeout remains 180 seconds and controller.py is forbidden to every implementation node.",
            "The knowledge DAG, its tournament bundle, production code, control plane, protected refs, and .autopilot/plan.json are unchanged.",
            "Only the ignored .autopilot/state/doctor-performance-v1.json may be materialized; it is never committed or treated as authority.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["contract:doctor-performance-v1"],
        "critical_path_importance": 100,
    },
    {
        "id": "DP-TESTS-010",
        "title": "Freeze the behavioral and isolation test contract",
        "objective": (
            "Add independent tests that freeze the complete unittest ID set and adversarially "
            "prove seed integrity, derivation isolation, confinement, and cleanup."
        ),
        "rationale": (
            "Tests must be authored independently before the Builder changes the fixture so "
            "the implementation cannot redefine its own success criteria."
        ),
        "dependencies": ["DP-CONTRACT-000"],
        "primary_role": "curator",
        "consulted_roles": ["explorer", "architect", "steward"],
        "required_inputs": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            ".autopilot/tests/test_fixture_isolation.py",
            ".autopilot/tests/test_healing.py",
        ],
        "expected_outputs": [
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
        ],
        "read_scope": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            ".autopilot/tests/test_fixture_isolation.py",
            ".autopilot/tests/test_healing.py",
            ".autopilot/bin/controller.py",
        ],
        "write_scope": [
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
        ],
        "required_tests": [
            "python -m unittest tests.test_autopilot_fixture_seed -v",
            "python -m unittest tests.test_doctor_performance_contract -v",
        ],
        "acceptance_criteria": [
            "The frozen and candidate suites discover exactly 381 executions on the cited host.",
            "The frozen and candidate suites have the identical complete unittest ID set digest sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4, with identical IDs, assertion bodies, subtests, behavior constants, skip decorators, and discovery order.",
            "On the cited host the frozen suite has 381 total executions: 380 pass, zero fail, zero error, and the same conditional skip test_orchestration.IntentOrchestrationTests.test_binding_state_symlink_escape_is_rejected only when directory symlink creation raises OSError.",
            "Adversarial cases cover source tree, commit, index mode, blob identity, source mutation fail-closed/rebuild, and exclusion of untracked, ignored, state, bytecode, credential-shaped, and outside-snapshot material.",
            "Tests prove ref, branch, receipt, index, worktree, concurrent-invocation, network, and cleanup isolation on success, test-body failure, and forced child-process termination.",
            "Tests reject alternates, shared object stores, hardlinks, symlinks, persistent caches, cached verdicts, and prior-result reuse.",
        ],
        "parallel_safe": True,
        "semantic_locks": ["test-contract:doctor-fixture-v1"],
        "critical_path_importance": 92,
    },
    {
        "id": "DP-BENCH-020",
        "title": "Capture the pinned baseline comparator",
        "objective": (
            "Run and retain reproducible baseline timing receipts for both pinned Python "
            "runtimes without changing the doctor command, timeout, discovery, or suite."
        ),
        "rationale": (
            "Benchmark evidence is an independent comparator and can be gathered in parallel "
            "with test authoring because both depend only on the sealed contract."
        ),
        "dependencies": ["DP-CONTRACT-000"],
        "primary_role": "optimizer",
        "consulted_roles": ["explorer", "curator", "steward"],
        "required_inputs": [
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            "git-object:6bc343f079be6f2d5fd6953d92099a8d5de872b1:evidence/knowledge-projection/baseline.json",
        ],
        "expected_outputs": [
            "evidence/performance/doctor-performance-v1/.gitkeep",
            "evidence/performance/doctor-performance-v1/baseline-python-3.14.json",
            "evidence/performance/doctor-performance-v1/baseline-python-3.12.json",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
        ],
        "read_scope": [
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            ".autopilot/bin/autopilot.py",
            ".autopilot/bin/controller.py",
            ".autopilot/tests/",
        ],
        "write_scope": [
            "evidence/performance/doctor-performance-v1/.gitkeep",
            "evidence/performance/doctor-performance-v1/baseline-python-3.14.json",
            "evidence/performance/doctor-performance-v1/baseline-python-3.12.json",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
        ],
        "required_tests": [
            "python docs/execution/dags/doctor-performance-v1/benchmark.py self-test"
        ],
        "acceptance_criteria": [
            "Each Python runtime has at least six fresh exact-doctor trials, alternating declared cold and warm modes with at least three cold trials.",
            "Receipts bind the commit, tree, index, source digests, runtime, platform, command, timeout, trial order, result digests, and nearest-rank p95 calculation.",
            "No trial uses the network, persistent test-result state, shared object storage, or a changed doctor timeout/discovery command.",
            "Baseline failure or slowness is retained as comparator evidence and is not represented as qualification success.",
        ],
        "parallel_safe": True,
        "semantic_locks": ["benchmark:doctor-performance-v1"],
        "critical_path_importance": 90,
    },
    {
        "id": "DP-FIXTURE-030",
        "title": "Implement invocation-scoped content-addressed fixtures",
        "objective": (
            "Build one pinned tracked seed and derive a fresh isolated writable repository "
            "and object database for every HealingFixture test invocation."
        ),
        "rationale": (
            "Implementation follows independent tests and a retained baseline, and its scope "
            "is limited to fixture support plus HealingFixture lifecycle wiring."
        ),
        "dependencies": ["DP-TESTS-010", "DP-BENCH-020"],
        "primary_role": "builder",
        "consulted_roles": ["architect", "curator", "steward"],
        "required_inputs": [
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
        ],
        "expected_outputs": [
            ".autopilot/tests/fixture_support.py",
            ".autopilot/tests/test_healing.py",
        ],
        "read_scope": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
            ".autopilot/tests/test_fixture_isolation.py",
            ".autopilot/tests/test_healing.py",
        ],
        "write_scope": [
            ".autopilot/tests/fixture_support.py",
            ".autopilot/tests/test_healing.py",
        ],
        "required_tests": [
            "python -m unittest discover -s .autopilot/tests -p test_fixture_isolation.py -v",
            "python -m unittest discover -s .autopilot/tests -p test_healing.py -v",
        ],
        "acceptance_criteria": [
            "The seed is content-addressed from a pinned tracked .autopilot snapshot and is revalidated for digest and repository identity before every derivation.",
            "Each test receives a fresh writable repository, object database, index, worktree, refs, branches, receipts, and state with no mutable sharing between invocations.",
            "The seed and derivations exclude untracked, ignored, .autopilot/state, bytecode, credential-shaped, and outside-snapshot content and perform no network operation.",
            "No alternates, --shared clone, hardlinks, symlinks, persistent cache, cached verdict, or prior result is used.",
            "Within test_healing.py only fixture imports and HealingFixture setUp/tearDown change; every test method, assertion, subtest, behavior constant, ID, order, and skip decorator remains byte-equivalent to the frozen contract.",
            "Cleanup succeeds after normal completion, test-body failure, and forced child-process termination; source mutation fails closed and a separately validated seed rebuild is explicit.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["fixture:healing-invocation-v1"],
        "critical_path_importance": 88,
        "forbidden_overrides": AUTOPILOT_TESTS_EXCEPT_HEALING,
    },
    {
        "id": "DP-QUALIFY-040",
        "title": "Independently qualify behavior and performance",
        "objective": (
            "Reproduce the frozen behavior vector, full repository gates, and candidate doctor "
            "latency on both runtimes as qualification evidence only."
        ),
        "rationale": (
            "A Curator identity different from the test author and Builder must reproduce all "
            "claims before any promotion decision."
        ),
        "dependencies": ["DP-FIXTURE-030"],
        "primary_role": "curator",
        "consulted_roles": ["integrator", "optimizer", "steward"],
        "required_inputs": [
            ".autopilot/tests/fixture_support.py",
            ".autopilot/tests/test_healing.py",
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
        ],
        "expected_outputs": [
            "evidence/performance/doctor-performance-v1/candidate-python-3.14.json",
            "evidence/performance/doctor-performance-v1/candidate-python-3.12.json",
            "evidence/performance/doctor-performance-v1/qualification.json",
        ],
        "read_scope": [
            ".autopilot/tests/",
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
            "docs/execution/dags/doctor-performance-v1/benchmark.py",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
        ],
        "write_scope": [
            "evidence/performance/doctor-performance-v1/candidate-python-3.14.json",
            "evidence/performance/doctor-performance-v1/candidate-python-3.12.json",
            "evidence/performance/doctor-performance-v1/qualification.json",
        ],
        "required_tests": [
            "python -m unittest discover -s .autopilot/tests -v",
            "python -m unittest discover -s tests -v",
        ],
        "acceptance_criteria": [
            "The candidate preserves the complete unittest ID set digest sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4 with unchanged discovery order, IDs, methods, assertions, subtests, behavior constants, and skip decorators.",
            "On the cited host qualification reproduces 381 total executions: 380 pass, zero fail, zero error, and the same conditional skip test_orchestration.IntentOrchestrationTests.test_binding_state_symlink_escape_is_rejected only when directory symlink creation raises OSError.",
            "Both exact doctor commands retain the controller's 180-second timeout, complete every trial below 180 seconds, and achieve nearest-rank p95 at or below 135 seconds.",
            "Each runtime has at least six fresh alternating cold/warm trials with at least three cold trials and complete digest-bound environment receipts.",
            "The two independent contract tests, focused fixture-isolation and healing suites, full .autopilot suite, full repository suite, confinement checks, and byte seals all pass.",
            "Qualification grants no production authority and makes no promotion or superiority decision.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["qualification:doctor-performance-v1"],
        "critical_path_importance": 82,
    },
    {
        "id": "DP-JUDGE-050",
        "title": "Judge exact candidate promotion and baseline retry",
        "objective": (
            "Issue ADOPT, ADAPT, DEFER, REJECT, or QUARANTINE on one immutable candidate "
            "and authorize a BASELINE-000 retry only after every sealed gate passes."
        ),
        "rationale": (
            "The Judge must be distinct from Architect, Optimizer, test Curator, Builder, "
            "qualification Curator, Integrator, and the blocked knowledge-baseline worker."
        ),
        "dependencies": ["DP-QUALIFY-040"],
        "primary_role": "integrator",
        "consulted_roles": [
            "orchestrator", "explorer", "architect", "builder", "curator", "steward", "optimizer"
        ],
        "required_inputs": [
            "evidence/performance/doctor-performance-v1/qualification.json",
            "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
        ],
        "expected_outputs": [
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json"
        ],
        "read_scope": [
            "docs/architecture/ADR-063-INVOCATION-SCOPED-TEST-FIXTURES.md",
            "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
            "evidence/performance/doctor-performance-v1/",
            "tests/test_autopilot_fixture_seed.py",
            "tests/test_doctor_performance_contract.py",
        ],
        "write_scope": [
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json"
        ],
        "required_tests": [
            "python docs/execution/dags/doctor-performance-v1/verify_plan.py"
        ],
        "acceptance_criteria": [
            "The court binds one immutable candidate commit and tree, all receipts, dissent, adverse evidence, identities, dispositions, rollback, and appeal conditions.",
            "Only an ADOPT verdict with zero unresolved material findings authorizes retrying knowledge-projection BASELINE-000; every other verdict keeps it blocked.",
            "The retry gate requires verifier/lint, byte seals, exact scope confinement, frozen vector and assertions, focused and full CI, both-runtime performance, and independent Curator receipts.",
            "Production/controller Git caching remains deferred and controller.py remains unchanged.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["court:doctor-performance-promotion"],
        "critical_path_importance": 75,
    },
]
