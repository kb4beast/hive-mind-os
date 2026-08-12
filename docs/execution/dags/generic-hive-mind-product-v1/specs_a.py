"""Node specifications for the generic Hive Mind product-completion DAG.

Generated-plan data only. This module performs no repository or network effects.
"""

SPECS = [{'id': 'BASELINE-000',
  'objective': 'Gate execution on an authorized, independently reviewed merge of PR #144; this '
               'node never merges it.',
  'dependencies': [],
  'parallel_safe': False,
  'critical_path_importance': 100,
  'semantic_locks': ['gate:baseline'],
  'read_scope': ['AGENTS.md', 'docs/execution/DAG_AUTHORING_STANDARD.md', '.autopilot/plan.json'],
  'write_scope': ['evidence/generic-dag-baseline.json'],
  'required_tests': ['python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan '
                     'docs/execution/dags/generic-hive-mind-product-v1/plan.json --strict',
                     'python .autopilot/bin/autopilot.py --repo-root . doctor --json'],
  'acceptance_criteria': ['PR #144 is already merged with retained ancestry and terminal required '
                          'CI.',
                          'Exact main/tree, merge, review, CI, plan fingerprint, and receipt '
                          'validity are digest-bound.',
                          'Any stale prerequisite blocks the overlay.']},
 {'id': 'FOUNDATION-010',
  'objective': 'Adopt or complete the existing sealed MISSION-400 and then DURABLE-410 nodes '
               'without duplicating their implementation.',
  'dependencies': ['BASELINE-000'],
  'parallel_safe': False,
  'critical_path_importance': 99,
  'semantic_locks': ['capability:durable-foundation'],
  'read_scope': ['.autopilot/plan.json',
                 'docs/execution/runbooks/MISSION-400.md',
                 'docs/execution/runbooks/DURABLE-410.md'],
  'write_scope': ['evidence/generic-dag-foundation.json'],
  'required_tests': ['python .autopilot/bin/autopilot.py --repo-root . doctor --json',
                     'python .autopilot/bin/autopilot.py --repo-root . status --json'],
  'acceptance_criteria': ['Exactly one integrated receipt exists for each sealed node.',
                          'MISSION-400 proves one canonical mission runtime; DURABLE-410 proves '
                          'checkpoints, replay, and no duplicate effects.',
                          'Incomplete work is delegated to the original contracts; this gate edits '
                          'no product code.',
                          'The mapping record binds both candidates, tests, receipts, and main.']},
 {'id': 'PLAN-CORE-100',
  'objective': 'Implement plan-generation lineage and the typed PortablePlanBundle without '
               'changing the sealed v1 plan.',
  'dependencies': ['FOUNDATION-010'],
  'parallel_safe': False,
  'critical_path_importance': 98,
  'semantic_locks': ['schema:plan-lineage', 'schema:portable-plan'],
  'read_scope': ['.autopilot/control-plane.json',
                 '.autopilot/receipt.schema.json',
                 'docs/execution/DAG_AUTHORING_STANDARD.md',
                 'src/hive_mind_os/brain_kernel/contracts.py'],
  'write_scope': ['.autopilot/bin/controller.py',
                  '.autopilot/bin/durable_controller.py',
                  '.autopilot/bin/release_barrier.py',
                  '.autopilot/receipt.schema.json',
                  '.autopilot/tests/test_plan_lineage.py',
                  'src/hive_mind_os/portable_plan.py',
                  'tests/test_portable_plan.py',
                  'docs/execution/portable-plan.schema.json',
                  'docs/execution/PLAN_LINEAGE.md'],
  'required_tests': ["python -m unittest discover -s .autopilot/tests -p 'test_plan_lineage.py' -v",
                     "python -m unittest discover -s tests -p 'test_portable_plan.py' -v"],
  'acceptance_criteria': ['Generations authenticate parents and node mappings; unchanged receipts '
                          'carry forward byte-identically while changed contracts requalify.',
                          'Removed nodes remain historical, new nodes inherit no completion, and '
                          'ambiguity, downgrade, cycle, or flat fingerprint substitution fails.',
                          'Portable plans model repository and non-repository subjects with typed '
                          'resources, capabilities, adapters, authority, budgets, recovery, '
                          'integration, and token policy.',
                          'Explicit overlay plans work without replacing .autopilot/plan.json; '
                          'existing receipts remain valid.']},
 {'id': 'BUILD-SYSTEM-200',
  'objective': 'Make BUILD_DAG standard-bound and ship one canonical digest-pinned linter/round '
               'compiler plus an original repository-owned planner prompt.',
  'dependencies': ['PLAN-CORE-100'],
  'parallel_safe': False,
  'critical_path_importance': 97,
  'semantic_locks': ['iface:build-dag', 'iface:dag-compiler'],
  'read_scope': ['docs/execution/DAG_AUTHORING_STANDARD.md',
                 'docs/execution/runbooks/PRODUCT-GENERIC-DAG.md',
                 '.autopilot/bin/dag_standard.py'],
  'write_scope': ['src/hive_mind_os/autopilot_workflow.py',
                  'src/hive_mind_os/dag_standard.py',
                  'src/hive_mind_os/planner_prompt.py',
                  '.autopilot/bin/dag_standard.py',
                  'tests/test_autopilot_workflow.py',
                  '.autopilot/tests/test_dag_standard.py',
                  'tests/test_planner_prompt.py',
                  'docs/execution/PORTABLE_AUTOPILOT.md',
                  'docs/execution/PLANNER_PROMPT.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_autopilot_workflow.py' -v",
                     "python -m unittest discover -s .autopilot/tests -p 'test_dag_standard.py' -v",
                     "python -m unittest discover -s tests -p 'test_planner_prompt.py' -v"],
  'acceptance_criteria': ['Initialization pins/materializes the standard by version, SHA-256, byte '
                          'count, and package identity.',
                          'BUILD_DAG cannot succeed until canonical lint has zero errors and every '
                          'warning has a recorded disposition.',
                          'Targets use a digest-checked packaged compiler, not an LLM '
                          'reimplementation.',
                          'The planner prompt is original, versioned, license-clean, '
                          'content-addressed, and proposes data without granting authority.',
                          'Missing, stale, substituted, downgraded, or pre-standard requests fail '
                          'closed; CHECK stays task-free.']},
 {'id': 'ADAPTER-INDEX-210',
  'objective': 'Implement subject/resource adapters, capability registry, and exact-tree '
               'repository indexing for arbitrary repositories and other subjects.',
  'dependencies': ['PLAN-CORE-100'],
  'parallel_safe': True,
  'critical_path_importance': 92,
  'semantic_locks': ['iface:subject-adapters', 'iface:repository-index'],
  'read_scope': ['src/hive_mind_os/autopilot_workflow.py',
                 'src/hive_mind_os/git_adapter.py',
                 'src/hive_mind_os/model_provider.py',
                 'src/hive_mind_os/brain_kernel/context.py'],
  'write_scope': ['src/hive_mind_os/subject_adapter.py',
                  'src/hive_mind_os/resource_adapter.py',
                  'src/hive_mind_os/adapter_registry.py',
                  'src/hive_mind_os/repository_index.py',
                  'tests/test_subject_adapter.py',
                  'tests/test_adapter_registry.py',
                  'tests/test_repository_index.py',
                  'docs/execution/SUBJECT_ADAPTERS.md',
                  'docs/execution/REPOSITORY_INDEX.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_subject_adapter.py' -v",
                     "python -m unittest discover -s tests -p 'test_adapter_registry.py' -v",
                     "python -m unittest discover -s tests -p 'test_repository_index.py' -v"],
  'acceptance_criteria': ['Repository paths are one resource adapter, not a core assumption; '
                          'artifacts, web sources, datasets, APIs, cloud, tickets, databases, and '
                          'custom resources are typed.',
                          'Adapter selection is deterministic, lowest-sufficient, vendor-neutral, '
                          'evidence-bound, and denies missing/conflicting authority before '
                          'execution.',
                          'The index binds repository identity, exact tree, analyzer, and '
                          'environment; unchanged blobs reuse, changed/deleted blobs update.',
                          'Cross-language metadata is conservative and non-executing; source '
                          'bodies, secrets, unsafe links, oversized binaries, and mutable state '
                          'are not cached.',
                          'Third-party adapters are inert until registered and independently '
                          'validated.']},
 {'id': 'WAVE-HOST-300',
  'objective': 'Implement immutable wave manifests, checkpoints, candidate sealing, bounded host '
               'supervision, and one CAS integration transaction per round.',
  'dependencies': ['BUILD-SYSTEM-200'],
  'parallel_safe': False,
  'critical_path_importance': 96,
  'semantic_locks': ['schema:wave-state', 'iface:host-adapter', 'iface:integration-transaction'],
  'read_scope': ['src/hive_mind_os/portable_plan.py',
                 'src/hive_mind_os/dag_standard.py',
                 'src/hive_mind_os/brain_kernel/verification.py',
                 'src/hive_mind_os/mission_store.py',
                 '.autopilot/bin/host_execution.py'],
  'write_scope': ['src/hive_mind_os/wave_manifest.py',
                  'src/hive_mind_os/host_adapter.py',
                  'src/hive_mind_os/host_runtime.py',
                  'src/hive_mind_os/brain_kernel/candidate_state.py',
                  'src/hive_mind_os/brain_kernel/contracts.py',
                  'src/hive_mind_os/brain_kernel/projection.py',
                  'src/hive_mind_os/integration_transaction.py',
                  'src/hive_mind_os/git_adapter.py',
                  'tests/test_wave_runtime.py',
                  'tests/test_host_adapter.py',
                  'docs/execution/WAVE_RUNTIME.md',
                  'docs/execution/HOST_ADAPTERS.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_wave_runtime.py' -v",
                     "python -m unittest discover -s tests -p 'test_host_adapter.py' -v"],
  'acceptance_criteria': ['A manifest binds generation, compiler/standard, frozen subject/tree, '
                          'ordered nodes, contracts, resources, context, tests, budgets, and '
                          'integration.',
                          'States include CHECKPOINTED, CANDIDATE_SEALED, VERIFYING, '
                          'INTEGRATION_READY, RECOVERABLE, REPLAN_REQUIRED, and terminals.',
                          'Sealing ends mutable authority; verification survives claim expiry and '
                          'orchestrator restart.',
                          'Host operations create/poll/message/checkpoint/cancel/resume/adopt '
                          'idempotently with wall-clock bounded waits and honest usage.',
                          'Workers never mutate target; the integrator merges sealed candidates in '
                          'declared order, validates once, and CAS-advances target once.',
                          'Drift, mutation, conflict, crash, or response loss leaves target '
                          'unchanged and recoverable.']},
 {'id': 'TASK-REUSE-310',
  'objective': 'Implement exact task fingerprints, existing-work detection, semantic dependency '
               'receipts, and safe candidate/task reuse before model launch.',
  'dependencies': ['ADAPTER-INDEX-210', 'BUILD-SYSTEM-200'],
  'parallel_safe': True,
  'critical_path_importance': 94,
  'semantic_locks': ['schema:task-fingerprint'],
  'read_scope': ['src/hive_mind_os/repository_index.py',
                 'src/hive_mind_os/portable_plan.py',
                 '.autopilot/receipt.schema.json'],
  'write_scope': ['src/hive_mind_os/task_reuse.py',
                  'tests/test_task_reuse.py',
                  'docs/execution/TASK_REUSE.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_task_reuse.py' -v"],
  'acceptance_criteria': ['Fingerprints bind plan/node, subject/tree, relevant surface, dependency '
                          'receipts, authority, compiler/policy, and environment.',
                          'Dispositions distinguish exact reuse, verify existing, resume active, '
                          'repair existing, execute new, stale, conflict, and blocked.',
                          'Only validated integrated receipts complete work; unaccepted branches '
                          'reduce to verification/repair.',
                          'Changed blobs, dependencies, authority, policy, environment, '
                          'corruption, or cross-subject identity invalidate reuse.']},
 {'id': 'RUNTIME-TOKEN-320',
  'objective': 'Make mission execution token-efficient through adaptive role dispositions, '
               'dependency-routed ContextCompiler envelopes, and measured token accounting.',
  'dependencies': ['ADAPTER-INDEX-210', 'FOUNDATION-010'],
  'parallel_safe': True,
  'critical_path_importance': 95,
  'semantic_locks': ['iface:runtime-token-economy'],
  'read_scope': ['src/hive_mind_os/brain_kernel/context.py',
                 'src/hive_mind_os/brain_kernel/roles.py',
                 'src/hive_mind_os/model_provider.py',
                 'src/hive_mind_os/ledger.py'],
  'write_scope': ['src/hive_mind_os/brain_kernel/role_applicability.py',
                  'src/hive_mind_os/token_ledger.py',
                  'src/hive_mind_os/brain_kernel/role_runtime.py',
                  'src/hive_mind_os/model_backend.py',
                  'tests/test_hive_cortex_role_applicability.py',
                  'tests/test_hive_cortex_token_economy.py',
                  'docs/execution/TOKEN_ECONOMY.md'],
  'required_tests': ['python -m unittest discover -s tests -p '
                     "'test_hive_cortex_role_applicability.py' -v",
                     "python -m unittest discover -s tests -p 'test_hive_cortex_token_economy.py' "
                     '-v'],
  'acceptance_criteria': ['Every role yields MODEL_EXECUTE, DETERMINISTIC_CHECK, NOT_APPLICABLE, '
                          'DEFERRED, or BLOCKED plus an evidence-bound result.',
                          'Small tasks use fewer than eight model calls without hiding lifecycle '
                          'accountability.',
                          'Direct dependencies get compact bodies, transitive ones digest refs, '
                          'unrelated context explicit omission, and cold retrieval evidence.',
                          'Existing ContextCompiler is the only budget/tier system; oldest-first '
                          'character truncation is fallback only.',
                          'Calls record measured, estimated, or unavailable input/output/cache '
                          'tokens; unavailable is not zero.']}]
