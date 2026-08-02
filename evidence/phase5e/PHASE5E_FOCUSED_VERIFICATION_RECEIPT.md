# Phase 5E focused verification receipt

- Exact tested head: `cf51e91f874d6ca81af90e4152f649e0ccfa79e7`
- Workflow run: `https://github.com/kb4beast/hive-mind-os/actions/runs/30674699706`
- Python: 3.11
- Ruff: 0.16.0
- Pyright: 1.1.411
- Compile exit: `0`
- Focused unittest exit: `0`
- Ruff exit: `0`
- Pyright exit: `0`

This receipt covers only the new Phase 5E Integrator modules and focused test file.
It does not resolve or relabel inherited Phase 5D debt, full-suite status, release readiness,
production readiness, authenticated independence, or superiority.

## Focused unittest output
```text
test_all_inherited_debt_is_exact_open_and_release_blocking (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_all_inherited_debt_is_exact_open_and_release_blocking) ... ok
test_each_output_digest_and_envelope_digest_are_checked (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_each_output_digest_and_envelope_digest_are_checked) ... ok
test_example_compiles_deterministically_and_validates (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_example_compiles_deterministically_and_validates) ... ok
test_intake_claims_no_execution_release_or_activation (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_intake_claims_no_execution_release_or_activation) ... ok
test_modules_are_package_private_and_plan_debt_is_present (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_modules_are_package_private_and_plan_debt_is_present) ... ok
test_outputs_are_defensive_against_caller_mutation (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_outputs_are_defensive_against_caller_mutation) ... ok
test_request_requires_exact_containers_and_rejects_unknown_fields (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_request_requires_exact_containers_and_rejects_unknown_fields) ... ok
test_resealed_release_authority_and_debt_escalation_fail (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_resealed_release_authority_and_debt_escalation_fail) ... ok
test_scope_authority_activation_and_next_role_are_fixed (test_phase5e_integrator_playbook.IntegratorIntakeTests.test_scope_authority_activation_and_next_role_are_fixed) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.011s

OK
```

## Ruff output
```text
All checks passed!
```

## Pyright output
```text
0 errors, 0 warnings, 0 informations
```
