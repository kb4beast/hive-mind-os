"""Node specifications for the generic Hive Mind product-completion DAG.

Generated-plan data only. This module performs no repository or network effects.
"""

SPECS = [{'id': 'GENERIC-EXECUTOR-400',
  'objective': 'Implement the generic runtime that validates plans, compiles rounds, launches '
               'workers, checkpoints, seals, verifies, integrates, resumes, and applies versioned '
               'graph patches.',
  'dependencies': ['WAVE-HOST-300', 'TASK-REUSE-310', 'ADAPTER-INDEX-210'],
  'parallel_safe': False,
  'critical_path_importance': 98,
  'semantic_locks': ['iface:generic-dag-executor'],
  'read_scope': ['src/hive_mind_os/portable_plan.py',
                 'src/hive_mind_os/dag_standard.py',
                 'src/hive_mind_os/wave_manifest.py',
                 'src/hive_mind_os/host_adapter.py',
                 'src/hive_mind_os/adapter_registry.py'],
  'write_scope': ['src/hive_mind_os/dag_executor.py',
                  'src/hive_mind_os/host_runtime.py',
                  'src/hive_mind_os/integration_transaction.py',
                  'src/hive_mind_os/task_reuse.py',
                  'tests/test_dag_executor.py',
                  'docs/execution/DAG_EXECUTOR.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_dag_executor.py' -v"],
  'acceptance_criteria': ['Execution refuses lint errors, undisposed warnings, stale '
                          'generations/manifests, missing adapters, invalid authority, or resource '
                          'conflicts.',
                          'Ready nodes become conflict-free rounds; all permitted workers start '
                          'before bounded polling and BFS depth is not execution authority.',
                          'Workers receive one frozen manifest and node delta; completed siblings '
                          'survive blocked/failed workers.',
                          'Parent restart adopts tasks, candidates, tests, transactions, and '
                          'effects without duplication.',
                          'Graph patches are plan-lineage records and cannot weaken acceptance, '
                          'authority, independence, or evidence.']},
 {'id': 'CONTROL-TOKEN-410',
  'objective': 'Add shared round capsules, node deltas, exact-candidate test reuse, tool snapshot '
               'reuse, compact evidence, and measured sidecar calibration.',
  'dependencies': ['GENERIC-EXECUTOR-400', 'RUNTIME-TOKEN-320'],
  'parallel_safe': False,
  'critical_path_importance': 94,
  'semantic_locks': ['iface:control-token-economy', 'iface:sidecar-calibration'],
  'read_scope': ['src/hive_mind_os/dag_executor.py',
                 'src/hive_mind_os/task_reuse.py',
                 'src/hive_mind_os/repository_index.py',
                 'src/hive_mind_os/brain_kernel/context.py',
                 '.autopilot/bin/sidecar_execution.py'],
  'write_scope': ['src/hive_mind_os/context_capsule.py',
                  'src/hive_mind_os/test_result_cache.py',
                  'src/hive_mind_os/evidence_compaction.py',
                  '.autopilot/bin/sidecar_execution.py',
                  '.autopilot/tests/test_sidecar_execution.py',
                  'src/hive_mind_os/token_ledger.py',
                  'tests/test_control_token_economy.py',
                  'tests/test_sidecar_calibration.py',
                  'docs/execution/CONTROL_TOKEN_ECONOMY.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_control_token_economy.py' -v",
                     'python -m unittest discover -s .autopilot/tests -p '
                     "'test_sidecar_execution.py' -v",
                     "python -m unittest discover -s tests -p 'test_sidecar_calibration.py' -v"],
  'acceptance_criteria': ['One immutable shared capsule exists per round; workers get only node '
                          'deltas, direct dependencies, and cold refs.',
                          'Test reuse requires exact candidate, command, tests, locks/config, '
                          'toolchain, OS, and safe environment.',
                          'Passing logs compact; failures retain first causal and all distinct '
                          'material errors plus raw digest.',
                          'Snapshot/cache drift, corruption, or secret-like data fails closed.',
                          'Sidecar net savings use measured parent avoided minus sidecar '
                          'input/output/coordination; static estimates are fallback, negative '
                          'classes stop.',
                          'A fixture proves materially lower context than naive fan-out without '
                          'weaker acceptance.']},
 {'id': 'PUBLIC-RUNTIME-500',
  'objective': 'Expose build, validate, rounds, execute, resume, status, cancel, graph, and '
               'reconcile, and connect them to subject-neutral execution.',
  'dependencies': ['CONTROL-TOKEN-410', 'BUILD-SYSTEM-200'],
  'parallel_safe': False,
  'critical_path_importance': 97,
  'semantic_locks': ['iface:public-subject-runtime'],
  'read_scope': ['src/hive_mind_os/autopilot_workflow.py',
                 'src/hive_mind_os/planner_prompt.py',
                 'src/hive_mind_os/portable_plan.py',
                 'src/hive_mind_os/subject_adapter.py',
                 'src/hive_mind_os/token_ledger.py'],
  'write_scope': ['src/hive_mind_os/dag_cli.py',
                  'src/hive_mind_os/cli.py',
                  'src/hive_mind_os/subject_execution.py',
                  'src/hive_mind_os/dag_executor.py',
                  'src/hive_mind_os/adapter_registry.py',
                  'tests/test_cli_dag.py',
                  'tests/test_subject_execution.py',
                  'docs/execution/DAG_CLI.md',
                  'docs/execution/SUBJECT_EXECUTION.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_cli_dag.py' -v",
                     "python -m unittest discover -s tests -p 'test_subject_execution.py' -v"],
  'acceptance_criteria': ['dag execute always validates exact plan and refuses stale manifests, '
                          'missing adapters, protected-target authority, or unsupported execution.',
                          'Commands work from any cwd with explicit subject/repository/plan; '
                          'read-only commands never mutate.',
                          'A caller can plan or execute repository and non-repository subjects '
                          'through the same runtime without Hive-specific paths.',
                          'Planning-only, local/no-SCM, and authorized delivery modes are '
                          'explicit; caches/lessons are subject-isolated.',
                          'No GitHub, language, model vendor, Hive node ID, or branch name is '
                          'assumed.']},
 {'id': 'GENERIC-FIXTURES-600',
  'objective': 'Create disposable cross-language and non-repository fixtures using installed '
               'public APIs without source changes.',
  'dependencies': ['PUBLIC-RUNTIME-500'],
  'parallel_safe': False,
  'critical_path_importance': 90,
  'semantic_locks': ['fixture:generic-product'],
  'read_scope': ['src/hive_mind_os/subject_execution.py',
                 'src/hive_mind_os/dag_executor.py',
                 'tests/test_mission_loop_provider.py'],
  'write_scope': ['tests/test_generic_dag_fixtures.py', 'docs/execution/GENERIC_DAG_FIXTURES.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_generic_dag_fixtures.py' -v"],
  'acceptance_criteria': ['Fixtures cover Python, Node/TypeScript, C#, Go or Rust, monorepo, '
                          'docs-only, no-test, target-advancing, offline/local, research/artifact, '
                          'and business/workflow subjects.',
                          'Each uses installed public APIs/adapters, not a Hive shortcut.',
                          'Plans, rounds, candidates, effects, receipts, recovery, and tokens are '
                          'deterministic, disposable, license-safe, secret-free, and point-in-time '
                          'bounded.']},
 {'id': 'FAILURE-QUALIFICATION-610',
  'objective': 'Qualify concurrency, target drift, hidden dependencies, host loss, checkpoint '
               'adoption, candidate mutation, integration conflict, and duplicate-effect recovery.',
  'dependencies': ['GENERIC-FIXTURES-600'],
  'parallel_safe': True,
  'critical_path_importance': 95,
  'semantic_locks': ['qualification:failure'],
  'read_scope': ['src/hive_mind_os/dag_executor.py',
                 'src/hive_mind_os/host_runtime.py',
                 'src/hive_mind_os/integration_transaction.py',
                 'src/hive_mind_os/brain_kernel/candidate_state.py'],
  'write_scope': ['tests/test_generic_dag_failure_matrix.py',
                  'evidence/generic-dag-failure-qualification.json',
                  'docs/execution/GENERIC_DAG_FAILURE_QUALIFICATION.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_generic_dag_failure_matrix.py' "
                     '-v'],
  'acceptance_criteria': ['A silent worker cannot hang the parent; completed siblings and sealed '
                          'candidates remain adoptable.',
                          'Random finish order yields one deterministic integration tree.',
                          'Target advance, hidden API, stale manifest, resource/merge conflict '
                          'replan before target mutation.',
                          'Parent/worker failures resume without duplicate model work, tests, '
                          'pushes, pull requests, comments, deployments, or other effects.',
                          'Cross-host coordination loss fails closed with self-verifying '
                          'evidence.']},
 {'id': 'TOKEN-BENCHMARK-620',
  'objective': 'Benchmark naive full-context/full-role execution against indexed, reused, '
               'dependency-routed execution across representative subjects.',
  'dependencies': ['GENERIC-FIXTURES-600', 'CONTROL-TOKEN-410'],
  'parallel_safe': True,
  'critical_path_importance': 94,
  'semantic_locks': ['qualification:token'],
  'read_scope': ['src/hive_mind_os/token_ledger.py',
                 'src/hive_mind_os/context_capsule.py',
                 'src/hive_mind_os/task_reuse.py',
                 'src/hive_mind_os/brain_kernel/role_runtime.py'],
  'write_scope': ['tests/test_generic_dag_token_benchmark.py',
                  'evidence/generic-dag-token-benchmark.json',
                  'docs/execution/GENERIC_DAG_TOKEN_BENCHMARK.md'],
  'required_tests': ['python -m unittest discover -s tests -p '
                     "'test_generic_dag_token_benchmark.py' -v"],
  'acceptance_criteria': ['Naive/optimized lanes have equal snapshots, acceptance, authority, '
                          'model route, budgets, and seeds.',
                          'Measure input/output/cache tokens, calls, retries, reads, tests, '
                          'sidecars, and accepted outcomes; unavailable stays unavailable.',
                          'The controlled target shows at least 30 percent fewer input tokens '
                          'without weaker acceptance and makes no universal savings claim.',
                          'Results are reproducible and candidate-bound.']},
 {'id': 'GENERIC-QUALIFICATION-630',
  'objective': 'Issue a fail-closed verdict for generic DAG authoring, execution, adapters, '
               'recovery, token economy, and cross-subject portability.',
  'dependencies': ['FAILURE-QUALIFICATION-610', 'TOKEN-BENCHMARK-620'],
  'parallel_safe': False,
  'critical_path_importance': 99,
  'semantic_locks': ['qualification:generic-product'],
  'read_scope': ['evidence/generic-dag-failure-qualification.json',
                 'evidence/generic-dag-token-benchmark.json',
                 'docs/execution/DAG_AUTHORING_STANDARD.md',
                 'docs/execution/DAG_EXECUTOR.md'],
  'write_scope': ['tests/test_generic_dag_qualification.py',
                  'evidence/generic-dag-qualification.json',
                  'docs/execution/GENERIC_DAG_QUALIFICATION.md'],
  'required_tests': ["python -m unittest discover -s tests -p 'test_generic_dag_qualification.py' "
                     '-v',
                     'python -m unittest discover -s tests -v'],
  'acceptance_criteria': ['One installed build handles required repository and non-repository '
                          'fixtures without source changes.',
                          'Plans are standard-bound, lint-clean, versioned, adapter-complete, '
                          'authority-safe, independently verified, and exact-candidate-bound.',
                          'Failure/token evidence reproduces on the candidate.',
                          'No Hive-specific repository, node, branch, language, vendor, or GitHub '
                          'assumption exists in the generic path.',
                          'Unsupported/external capabilities are stated honestly and block '
                          'maturity claims; cross-platform CI/security are terminal.']},
 {'id': 'HANDOFF-700',
  'objective': 'Publish the open-source guide and return control to the original sealed functional '
               'DAG without rewriting its remaining nodes.',
  'dependencies': ['GENERIC-QUALIFICATION-630'],
  'parallel_safe': False,
  'critical_path_importance': 100,
  'semantic_locks': ['release:generic-product'],
  'read_scope': ['README.md',
                 'USER_GUIDE/README.md',
                 'docs/execution/PORTABLE_AUTOPILOT.md',
                 'docs/execution/GENERIC_DAG_QUALIFICATION.md',
                 '.autopilot/plan.json'],
  'write_scope': ['USER_GUIDE/07_GENERIC_DAG_EXECUTION.md',
                  'docs/execution/GENERIC_DAG_RELEASE.md',
                  'evidence/generic-dag-product-handoff.json'],
  'required_tests': ['python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan '
                     'docs/execution/dags/generic-hive-mind-product-v1/plan.json --strict',
                     'python -m unittest discover -s tests -v'],
  'acceptance_criteria': ['A new user can clone, build, validate, execute, resume, inspect, and '
                          'reconcile portable DAGs through public commands.',
                          'The guide covers subjects, adapters, authority, tokens, recovery, and '
                          'external gates.',
                          "The handoff binds qualification evidence and names the sealed program's "
                          'next lawful round without modifying its plan/receipts.',
                          'A final draft PR into main is opened without auto-merge and remains '
                          'unmerged.']}]
