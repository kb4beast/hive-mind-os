"""Immutable Appeals-Judge-authorized node specifications for git-commit-observation-v1."""

from __future__ import annotations


VECTOR_DIGEST = "sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4"
EVIDENCE_DIR = "evidence/performance/git-commit-observation-v1"


SPECS = [
    {
        "id": "GCO-SEAL-000",
        "title": "Seal the Git commit observation challenger court",
        "objective": (
            "As Clerk, seal the Appeals Judge's ADAPT disposition as an additive ten-node "
            "git-commit-observation-v1 DAG without changing runtime code, tests, existing "
            "DAGs, or the rejected fixture candidate."
        ),
        "rationale": (
            "The prior Judge authorized court opening only. A deterministic sealed contract "
            "must precede diagnostics, tests, architecture, implementation, or qualification."
        ),
        "dependencies": [],
        "primary_role": "orchestrator",
        "court_seat": "clerk",
        "consulted_roles": ["explorer", "architect", "curator", "steward", "optimizer"],
        "required_inputs": [
            "AGENTS.md",
            "docs/execution/DAG_AUTHORING_STANDARD.md",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
            "docs/execution/dags/knowledge-projection-v1/verify_plan.py",
            "docs/execution/dags/doctor-performance-v1/verify_plan.py",
        ],
        "expected_outputs": [
            "docs/execution/dags/git-commit-observation-v1/README.md",
            "docs/execution/dags/git-commit-observation-v1/.gitignore",
            "docs/execution/dags/git-commit-observation-v1/specs.py",
            "docs/execution/dags/git-commit-observation-v1/generate_plan.py",
            "docs/execution/dags/git-commit-observation-v1/verify_plan.py",
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            "docs/execution/dags/git-commit-observation-v1/manifest.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
        ],
        "read_scope": [
            "AGENTS.md",
            "docs/execution/DAG_AUTHORING_STANDARD.md",
            ".autopilot/plan.json",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "docs/execution/dags/knowledge-projection-v1/manifest.json",
            "docs/execution/dags/knowledge-projection-v1/verify_plan.py",
            "docs/execution/dags/doctor-performance-v1/manifest.json",
            "docs/execution/dags/doctor-performance-v1/verify_plan.py",
            "evidence/courts/CASE-BASELINE-000-DOCTOR-PERFORMANCE.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "write_scope": [
            "docs/execution/dags/git-commit-observation-v1/README.md",
            "docs/execution/dags/git-commit-observation-v1/.gitignore",
            "docs/execution/dags/git-commit-observation-v1/specs.py",
            "docs/execution/dags/git-commit-observation-v1/generate_plan.py",
            "docs/execution/dags/git-commit-observation-v1/verify_plan.py",
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            "docs/execution/dags/git-commit-observation-v1/manifest.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
        ],
        "required_tests": [
            "python docs/execution/dags/git-commit-observation-v1/verify_plan.py",
            "python docs/execution/dags/git-commit-observation-v1/benchmark.py self-test",
            "python docs/execution/dags/knowledge-projection-v1/verify_plan.py",
            "python docs/execution/dags/doctor-performance-v1/verify_plan.py",
        ],
        "acceptance_criteria": [
            "The exact ten-node graph, nine dispatch rounds, scopes, identities, gates, stopping conditions, rejected comparator, and Appeals Judge amendments are sealed.",
            "The plan expressly rejects generic caching, automatic promotion, superiority, and knowledge BASELINE-000 retry authority.",
            "All seven DAG files and the opening court are self-consistently sealed while .autopilot/plan.json and both existing sealed DAGs remain unchanged.",
            "Only the ignored .autopilot/state/git-commit-observation-v1.json is materialized; it is never committed or treated as authority.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["contract:git-commit-observation-v1"],
        "critical_path_importance": 100,
        "stopping_condition": (
            "Stop after the verifier, benchmark self-test, both predecessor DAG verifiers, "
            "strict lint, and nine-round compilation pass; commit exactly the eight declared outputs."
        ),
        "rollback": "Revert only GCO-SEAL-000's single retained unsquashed commit; do not amend predecessor seals or adverse evidence.",
    },
    {
        "id": "GCO-BASELINE-010",
        "title": "Capture current Git-read diagnostics",
        "objective": (
            "As Explorer with Optimizer testimony, measure and retain the current exact-doctor "
            "Git-read diagnostic comparator without modifying behavior or claiming causality."
        ),
        "rationale": "A retained current-state diagnostic is required before architecture or optimization claims.",
        "dependencies": ["GCO-SEAL-000"],
        "primary_role": "explorer",
        "consulted_roles": ["optimizer", "curator", "steward"],
        "required_inputs": [
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "expected_outputs": [f"{EVIDENCE_DIR}/baseline-diagnostic.json"],
        "read_scope": [
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            ".autopilot/bin/autopilot.py",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "write_scope": [f"{EVIDENCE_DIR}/baseline-diagnostic.json"],
        "required_tests": [
            f"python docs/execution/dags/git-commit-observation-v1/benchmark.py verify --receipt {EVIDENCE_DIR}/baseline-diagnostic.json --phase baseline-diagnostic"
        ],
        "acceptance_criteria": [
            "The receipt binds baseline commit/tree, index, runtime, exact doctor command, 180-second timeout, output digest, and one fresh diagnostic trial.",
            "The receipt preserves observed failure or slowness and makes no claim that Git reads are the dominant cause.",
            "The rejected fixture candidate 41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378 / b02326bf108de2fbaa2f174975f937979c02bf90 remains a separate pinned adverse comparator.",
        ],
        "parallel_safe": True,
        "semantic_locks": ["evidence:gco-baseline-diagnostic-v1"],
        "critical_path_importance": 95,
        "stopping_condition": "Stop when the one-trial diagnostic receipt verifies, is retained unchanged, and no path outside write_scope changed.",
        "rollback": "Revert only GCO-BASELINE-010's single retained unsquashed commit; preserve any externally cited receipt as superseded adverse evidence.",
    },
    {
        "id": "GCO-TEST-020",
        "title": "Freeze adversarial commit-observation behavior",
        "objective": (
            "As an independent Curator, author the complete adversarial contract before the "
            "Architect and Builder can define implementation success."
        ),
        "rationale": "Independent tests prevent the implementation from weakening or redefining the observation boundary.",
        "dependencies": ["GCO-SEAL-000"],
        "primary_role": "curator",
        "court_seat": "independent-test-curator",
        "consulted_roles": ["explorer", "architect", "steward"],
        "required_inputs": [
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            ".autopilot/bin/sealed_recovery.py",
            ".autopilot/bin/release_barrier.py",
        ],
        "expected_outputs": ["tests/test_doctor_git_fact_batching.py"],
        "read_scope": [
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            ".autopilot/bin/sealed_recovery.py",
            ".autopilot/bin/release_barrier.py",
            ".autopilot/tests/test_controller.py",
            ".autopilot/tests/test_durable_completion.py",
        ],
        "write_scope": ["tests/test_doctor_git_fact_batching.py"],
        "required_tests": ["python -m unittest tests.test_doctor_git_fact_batching -v"],
        "acceptance_criteria": [
            "Tests cover delimiter and duplicate injection, partial false-negatives, ref move/create/delete, fetch after missing objects, replace refs, and malformed batch missing/duplicate/extra/truncated/reordered/wrong-type/hash-mismatch responses.",
            "Tests cover shallow repositories, grafts, alternates, promisor repositories, ordinary repositories, worktrees, and object-format/repository-identity mismatch.",
            "Tests cover nested and concurrent use, success, exception, cancellation, timeout cleanup, mutation attempts, and prohibit cross-instance or cross-invocation reuse.",
            "Tests mutate authority, claims, releases, leases, snapshots, receipts, intents, refs, origin, and target during an observation and require fresh uncached effect-adjacent checks including force-with-lease/CAS.",
            "Tests prove sealed_recovery.py and release_barrier.py neither consume nor retain GitCommitObservation and freeze all existing .autopilot tests unchanged.",
        ],
        "parallel_safe": True,
        "semantic_locks": ["test-contract:git-commit-observation-v1"],
        "critical_path_importance": 94,
        "stopping_condition": "Stop when the independent adversarial module is red against the baseline for only the authorized missing behavior, is reviewable, and no existing test changed.",
        "rollback": "Revert only GCO-TEST-020's single retained unsquashed commit; never modify frozen .autopilot tests to make the contract pass.",
    },
    {
        "id": "GCO-ARCH-030",
        "title": "Specify one-shot raw commit observation",
        "objective": (
            "As Architect, specify the private immutable GitCommitObservation and its bounded "
            "one-shot raw Git reader, fail-closed validation, lifecycle, threat model, and rollback."
        ),
        "rationale": "Architecture follows sealed evidence and precedes implementation; no generic cache or ambient API substitution is authorized.",
        "dependencies": ["GCO-SEAL-000", "GCO-BASELINE-010"],
        "primary_role": "architect",
        "consulted_roles": ["explorer", "builder", "curator", "integrator", "steward", "optimizer"],
        "required_inputs": [
            f"{EVIDENCE_DIR}/baseline-diagnostic.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
        ],
        "expected_outputs": ["docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md"],
        "read_scope": [
            f"{EVIDENCE_DIR}/baseline-diagnostic.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "tests/test_doctor_git_fact_batching.py",
        ],
        "write_scope": ["docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md"],
        "required_tests": ["python -m unittest tests.test_doctor_git_fact_batching -v"],
        "acceptance_criteria": [
            "The ADR limits the reader to finite deduplicated validated full commit OIDs and binds repository root, absolute Git directory, common directory, object format, and permitted object store.",
            "The ADR rejects shallow, graft, promisor, replace, and alternate configurations unless independently proven safe; replacements are disabled for one git cat-file --batch process.",
            "It requires full OIDs linewise, exact count and order, exact '<oid> commit <decimal-size>' headers, exact bodies and terminators, OID recomputation from 'commit <size>\\0<body>', and exactly one tree plus zero or more parents before the blank line.",
            "Missing, malformed, duplicate, extra, truncated, reordered, wrong-type, and hash-mismatch output is fatal; facts are immutable, process state is fully cleaned, and observations are never retained or serialized.",
            "It explicitly excludes diff/ancestry batching, generic/ref/HEAD/negative caches, persistent state, shared daemons, network mutation authority, automatic promotion, superiority, and BASELINE-000 retry.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["architecture:git-commit-observation-v1"],
        "critical_path_importance": 90,
        "stopping_condition": "Stop when ADR-064 encodes every sealed invariant and threat, the independent test command passes or remains red only for missing implementation, and changed paths equal write_scope.",
        "rollback": "Revert only GCO-ARCH-030's single retained unsquashed commit; the opening court and diagnostic remain authoritative evidence.",
    },
    {
        "id": "GCO-BUILD-040",
        "title": "Build bounded raw commit observation",
        "objective": (
            "As Builder, implement the controller-private immutable GitCommitObservation and "
            "one-shot reader and use it only in exercised diagnostic and pure-validation paths."
        ),
        "rationale": "Implementation is authorized only after independent tests and the architecture decision are integrated.",
        "dependencies": ["GCO-TEST-020", "GCO-ARCH-030"],
        "primary_role": "builder",
        "consulted_roles": ["architect", "curator", "steward"],
        "required_inputs": [
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
            "tests/test_doctor_git_fact_batching.py",
            ".autopilot/bin/controller.py",
        ],
        "expected_outputs": [".autopilot/bin/controller.py"],
        "read_scope": [
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
            "tests/test_doctor_git_fact_batching.py",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
        ],
        "write_scope": [".autopilot/bin/controller.py"],
        "required_tests": ["python -m unittest tests.test_doctor_git_fact_batching -v"],
        "acceptance_criteria": [
            "The implementation exactly enforces the sealed repository identity, configuration rejection, one-process batch protocol, commit grammar, object hash, count/order, immutability, and cleanup contract.",
            "The candidate removes or bypasses unsafe generic _git caching and delimiter-derived graph conclusions only in exercised validation/effect-adjacent paths; it does not replace them with another generic cache.",
            "No ambient replacement of _git, git_object_exists, is_ancestor, _commit_tree, or _commit_parents occurs; no diff or ancestry batching is introduced.",
            "The observation is invocation-local, non-serializable, non-retained, diagnostic/pure-validation only, and grants no remote or effect authority.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["iface:controller-git-facts"],
        "critical_path_importance": 85,
        "stopping_condition": "Stop when the focused adversarial test passes, the observation remains private and invocation-local, no unauthorized surface changed, and changed paths equal write_scope.",
        "rollback": "Revert only GCO-BUILD-040's single retained unsquashed commit to restore controller.py; retain tests, ADR, diagnostics, and court records.",
    },
    {
        "id": "GCO-INTEGRATE-050",
        "title": "Integrate explicit pure receipt validation",
        "objective": (
            "As Integrator, allow durable_controller receipt validation to consume an explicit "
            "invocation-local observation parameter only, with no ambient or retained access."
        ),
        "rationale": "The durable consumer follows the bounded producer so interface and lifecycle are integrated serially.",
        "dependencies": ["GCO-BUILD-040"],
        "primary_role": "integrator",
        "consulted_roles": ["architect", "builder", "curator", "steward"],
        "required_inputs": [
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
            "tests/test_doctor_git_fact_batching.py",
        ],
        "expected_outputs": [".autopilot/bin/durable_controller.py"],
        "read_scope": [
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            ".autopilot/bin/sealed_recovery.py",
            ".autopilot/bin/release_barrier.py",
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
            "tests/test_doctor_git_fact_batching.py",
        ],
        "write_scope": [".autopilot/bin/durable_controller.py"],
        "required_tests": [
            "python -m unittest tests.test_doctor_git_fact_batching -v",
            "python -m unittest discover -s .autopilot/tests -p test_durable_completion.py -v",
        ],
        "acceptance_criteria": [
            "durable_controller consumes an explicit parameter or local variable only for pure receipt validation and never stores, serializes, reconstructs, or obtains it ambiently.",
            "Before every claim, completion, retirement, repair, fetch, push, update-ref, CAS, compensation, or publication decision, the observation is destroyed and repository/origin/target/reconcile/refs/objects/authority/releases/leases/claims/snapshots/receipts/intents/CAS are freshly read without cache.",
            "Effects retain existing CAS/force-with-lease semantics and are freshly verified after execution; the observation never supplies effect authority.",
            "sealed_recovery.py and release_barrier.py remain unchanged and cannot consume the observation.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["iface:durable-receipt-validation"],
        "critical_path_importance": 80,
        "stopping_condition": "Stop when focused observation and durable-completion tests pass, fresh effect boundaries are explicit, sealed recovery/release files are untouched, and changed paths equal write_scope.",
        "rollback": "Revert only GCO-INTEGRATE-050's single retained unsquashed commit to restore durable_controller.py without reverting GCO-BUILD-040.",
    },
    {
        "id": "GCO-SAFETY-060",
        "title": "Independently qualify observation safety",
        "objective": (
            "As Steward with an independent Curator, reproduce the fail-closed parser, "
            "repository isolation, cleanup, mutation, and fresh-effect boundary claims."
        ),
        "rationale": "Safety evidence must be independent from Builder and Integrator before any performance smoke trial.",
        "dependencies": ["GCO-INTEGRATE-050"],
        "primary_role": "steward",
        "court_seat": "independent-safety-curator",
        "consulted_roles": ["curator", "architect", "integrator", "optimizer"],
        "required_inputs": [
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            "tests/test_doctor_git_fact_batching.py",
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
        ],
        "expected_outputs": [f"{EVIDENCE_DIR}/safety-qualification.json"],
        "read_scope": [
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
            ".autopilot/bin/sealed_recovery.py",
            ".autopilot/bin/release_barrier.py",
            "tests/test_doctor_git_fact_batching.py",
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
        ],
        "write_scope": [f"{EVIDENCE_DIR}/safety-qualification.json"],
        "required_tests": [
            "python -m unittest tests.test_doctor_git_fact_batching -v",
            "python -m unittest discover -s .autopilot/tests -p test_durable_completion.py -v",
            "python -m unittest discover -s .autopilot/tests -p test_release_barrier.py -v",
            "python -m unittest discover -s .autopilot/tests -p test_sealed_recovery_bootstrap.py -v",
        ],
        "acceptance_criteria": [
            "The receipt binds candidate commit/tree, exact changed paths, test commands/results, parser/configuration adversaries, repository/worktree isolation, lifecycle cleanup, immutability, and mutation evidence.",
            "It independently proves no cross-instance/invocation reuse, persistent/shared state, generic/ref/HEAD/negative/ancestry cache, remote effect, or sealed-recovery/release consumption.",
            "It proves observation destruction and fresh uncached authority/ref/object/CAS reads before and after every effect-adjacent decision.",
            "Any unresolved material finding stops performance trials and is retained for GCO-JUDGE-090.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["evidence:gco-safety-v1"],
        "critical_path_importance": 75,
        "stopping_condition": "Stop when all focused safety tests pass and a digest-bound independent safety receipt records zero unresolved material findings; otherwise stop fail-closed with findings retained.",
        "rollback": "Revert only GCO-SAFETY-060's single retained unsquashed commit; do not rewrite Builder/Integrator commits or erase adverse findings.",
    },
    {
        "id": "GCO-SMOKE-070",
        "title": "Run one fresh smoke trial per runtime",
        "objective": (
            "As Optimizer, run exactly one fresh exact-doctor smoke trial on Python 3.14 and "
            "the bundled Python 3.12 before authorizing a six-trial matrix."
        ),
        "rationale": "A cheap two-runtime stop gate prevents repeating a decisively failing twelve-trial experiment.",
        "dependencies": ["GCO-SAFETY-060"],
        "primary_role": "optimizer",
        "consulted_roles": ["curator", "steward"],
        "required_inputs": [
            f"{EVIDENCE_DIR}/safety-qualification.json",
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
        ],
        "expected_outputs": [
            f"{EVIDENCE_DIR}/smoke-python-3.14.json",
            f"{EVIDENCE_DIR}/smoke-python-3.12.json",
        ],
        "read_scope": [
            f"{EVIDENCE_DIR}/safety-qualification.json",
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            ".autopilot/bin/autopilot.py",
            ".autopilot/bin/controller.py",
            ".autopilot/bin/durable_controller.py",
        ],
        "write_scope": [
            f"{EVIDENCE_DIR}/smoke-python-3.14.json",
            f"{EVIDENCE_DIR}/smoke-python-3.12.json",
        ],
        "required_tests": [
            f"python docs/execution/dags/git-commit-observation-v1/benchmark.py verify --receipt {EVIDENCE_DIR}/smoke-python-3.14.json --phase smoke",
            f"python docs/execution/dags/git-commit-observation-v1/benchmark.py verify --receipt {EVIDENCE_DIR}/smoke-python-3.12.json --phase smoke",
        ],
        "acceptance_criteria": [
            "Each pinned runtime has exactly one fresh exact-doctor trial with the unchanged command and internal 180-second timeout.",
            "If either smoke does not pass below 180 seconds, preserve both receipts, prohibit the six-trial matrix, and route a fail-closed non-run qualification to the Judge.",
            "Only two passing sub-180-second smokes authorize GCO-QUALIFY-080 to execute fresh cold-first alternating trials.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["benchmark:gco-smoke-v1"],
        "critical_path_importance": 70,
        "stopping_condition": "Stop after exactly one receipt per pinned runtime verifies; never begin six-trial qualification in this node.",
        "rollback": "Revert only GCO-SMOKE-070's single retained unsquashed commit; retain any externally cited smoke failure as adverse evidence.",
    },
    {
        "id": "GCO-QUALIFY-080",
        "title": "Conditionally qualify the immutable challenger",
        "objective": (
            "As an independent qualification Curator, enforce the smoke stop gate and, only "
            "after it passes, run the two-runtime six-trial performance and complete behavior gates."
        ),
        "rationale": "Qualification is evidence only and remains independent of Builder, Integrator, Optimizer, and Judge.",
        "dependencies": ["GCO-SMOKE-070"],
        "primary_role": "curator",
        "court_seat": "independent-qualification-curator",
        "consulted_roles": ["integrator", "steward", "optimizer"],
        "required_inputs": [
            f"{EVIDENCE_DIR}/smoke-python-3.14.json",
            f"{EVIDENCE_DIR}/smoke-python-3.12.json",
            f"{EVIDENCE_DIR}/safety-qualification.json",
            f"{EVIDENCE_DIR}/baseline-diagnostic.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "expected_outputs": [
            f"{EVIDENCE_DIR}/candidate-python-3.14.json",
            f"{EVIDENCE_DIR}/candidate-python-3.12.json",
            f"{EVIDENCE_DIR}/qualification.json",
        ],
        "read_scope": [
            f"{EVIDENCE_DIR}/baseline-diagnostic.json",
            f"{EVIDENCE_DIR}/safety-qualification.json",
            f"{EVIDENCE_DIR}/smoke-python-3.14.json",
            f"{EVIDENCE_DIR}/smoke-python-3.12.json",
            "evidence/performance/doctor-performance-v1/baseline-summary.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
            "docs/execution/dags/git-commit-observation-v1/benchmark.py",
            "tests/test_doctor_git_fact_batching.py",
            ".autopilot/tests/",
            "tests/",
        ],
        "write_scope": [
            f"{EVIDENCE_DIR}/candidate-python-3.14.json",
            f"{EVIDENCE_DIR}/candidate-python-3.12.json",
            f"{EVIDENCE_DIR}/qualification.json",
        ],
        "required_tests": [
            "python -m unittest tests.test_doctor_git_fact_batching -v",
            f"python docs/execution/dags/git-commit-observation-v1/benchmark.py verify-program --qualification {EVIDENCE_DIR}/qualification.json",
        ],
        "acceptance_criteria": [
            "A failed smoke produces explicit not-run candidate receipts and a fail-closed qualification record; it never executes the six-trial matrix or full suites.",
            "After two passing smokes, each runtime runs at least six fresh cold-first alternating exact-doctor trials; every trial passes below 180 seconds and nearest-rank p95 is at most 135 seconds.",
            f"After performance passes, focused adversarial tests, full .autopilot discovery, and full repository CI pass, with exactly 381 executions = 380 pass + the same conditional skip and complete ID digest {VECTOR_DIGEST}.",
            "Receipts bind the new immutable candidate commit/tree and compare it with the retained baseline and rejected fixture candidate 41950b74bdec2b6e1c48ee7f5ef3ce947d0c8378 / b02326bf108de2fbaa2f174975f937979c02bf90.",
            "Qualification grants no promotion, superiority, remote effect, generic caching, or BASELINE-000 retry authority.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["qualification:git-commit-observation-v1"],
        "critical_path_importance": 65,
        "stopping_condition": "Stop after a verifier-bound failed-smoke non-run record or a complete passing two-runtime qualification; preserve every losing receipt and do not judge the candidate.",
        "rollback": "Revert only GCO-QUALIFY-080's single retained unsquashed commit; retain cited losing measurements and never reuse them as fresh trials.",
    },
    {
        "id": "GCO-JUDGE-090",
        "title": "Judge the immutable observation challenger",
        "objective": (
            "As a Judge distinct from every prior identity, issue adopt, adapt, defer, reject, "
            "or quarantine for the one immutable candidate and preserve all dissent and evidence."
        ),
        "rationale": "Only an independent final court may convert qualification evidence into narrowly scoped promotion authority.",
        "dependencies": ["GCO-QUALIFY-080"],
        "primary_role": "orchestrator",
        "court_seat": "judge",
        "consulted_roles": ["explorer", "architect", "builder", "curator", "integrator", "steward", "optimizer"],
        "required_inputs": [
            f"{EVIDENCE_DIR}/qualification.json",
            f"{EVIDENCE_DIR}/safety-qualification.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "expected_outputs": ["evidence/courts/CASE-GIT-COMMIT-OBSERVATION-QUALIFICATION.json"],
        "read_scope": [
            "docs/architecture/ADR-064-ONE-SHOT-RAW-GIT-COMMIT-OBSERVATIONS.md",
            f"{EVIDENCE_DIR}/baseline-diagnostic.json",
            f"{EVIDENCE_DIR}/safety-qualification.json",
            f"{EVIDENCE_DIR}/smoke-python-3.14.json",
            f"{EVIDENCE_DIR}/smoke-python-3.12.json",
            f"{EVIDENCE_DIR}/candidate-python-3.14.json",
            f"{EVIDENCE_DIR}/candidate-python-3.12.json",
            f"{EVIDENCE_DIR}/qualification.json",
            "evidence/courts/CASE-GIT-COMMIT-OBSERVATION-OPENING.json",
            "evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json",
        ],
        "write_scope": ["evidence/courts/CASE-GIT-COMMIT-OBSERVATION-QUALIFICATION.json"],
        "required_tests": [
            "python docs/execution/dags/git-commit-observation-v1/verify_plan.py",
            f"python docs/execution/dags/git-commit-observation-v1/benchmark.py verify-program --qualification {EVIDENCE_DIR}/qualification.json",
        ],
        "acceptance_criteria": [
            "The court binds one new immutable candidate commit/tree, identities, source and receipt digests, exact scope, tests, performance, safety, dissent, adverse evidence, rollback, and appeal conditions.",
            "Only ADOPT with zero lint, scope, seal, safety, behavior, performance, CI, and rollback findings may authorize the narrowly bounded candidate; every other disposition remains blocked.",
            "No verdict in this court authorizes a superiority claim, generic caching, remote effects, reuse of the rejected candidate, automatic promotion, or knowledge BASELINE-000 retry.",
        ],
        "parallel_safe": False,
        "semantic_locks": ["court:git-commit-observation-qualification"],
        "critical_path_importance": 60,
        "stopping_condition": "Stop after one signed digest-bound disposition records all evidence and dissent; only ADOPT with zero unresolved material findings unblocks the narrowly scoped candidate.",
        "rollback": "Revert only GCO-JUDGE-090's single retained unsquashed commit if correction is authorized; preserve the original verdict externally as superseded and never amend evidence in place.",
    },
]
