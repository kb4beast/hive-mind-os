# Phase 5C Installed-Wheel Receipt Contract

The Constitutional CI build job must:

1. build the wheel without project dependencies;
2. install it into an isolated target;
3. run the inherited general, Phase 5A, and Phase 5B installed-wheel verifiers;
4. run `scripts/verify_phase5c_installed_wheel.py` against the isolated target;
5. write `dist/phase5c-installed-wheel.json`;
6. include the wheel, SPDX 2.3 SBOM, release integration audit, and all installed-playbook
   receipts in the immutable build-evidence artifact; and
7. include the same subjects in push-event provenance when that event and permission are
   available.

The Phase 5C verifier checks import provenance, all thirteen schemas, all ten outputs,
request/scope bindings, resource reconciliation, Curator handoff truth fields, and absence of
capabilities, tools, authority, execution, test-result, completion, promotion, activation, or
artifact-creation claims.

This file defines the receipt contract. It does not claim a hosted run passed. Exact run/job,
commit, artifact, wheel, SBOM, and available attestation receipts must be retrieved from GitHub
for the final candidate head before describing it as green.
