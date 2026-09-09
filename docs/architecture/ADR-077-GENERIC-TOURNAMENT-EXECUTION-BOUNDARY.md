# ADR-077: Generic tournament execution and external evidence boundaries

Date: 2026-09-09
Status: adopted for local implementation; hostile-code and independent-principal claims remain conditional

## Sources and atomic claims

- `origin/main@2e08f2ba06f54fc5cd80e566e5b8948cbf7d4f03`, retrieved 2026-09-09, repository license applies. The baseline provides a portable plan, authenticated local run events, an operator-local process sandbox, idea lineage, and the 13-node tournament fixture.
- Local owner-supplied handoff `HANDOFF-FINISH-GENERIC-TOURNAMENT-DAG-2026-09-09.md`, SHA-256 `0aebc14d8e1fef3c8773db4fc497bbfbde896a499537d848e0a4b7cdb84ab2b0`, received 2026-09-09, private operational provenance. Its distinct claims are: orchestration data belongs outside the target; execution must be plan-driven; verification commands need sealed adapters; hostile-code isolation and independent principals must not be overstated; evidence and comparators must be content/version addressed; promotion requires separate authority.

The handoff is evidence of desired behavior. It is not used as a credential, execution signature, release grant, or permission to push, merge, deploy, spend, or access secrets.

## Court

Advocate (Architect identity): explicit execution metadata eliminates topology-name coupling and makes arbitrary plans inspectable before effects. Sealed adapters remove model-selected command execution, and content-addressed evidence prevents duplicate citations from inflating a decision.

Cross-examiner (Curator identity): a local process boundary does not deny network or general host filesystem access on every platform; actor strings and session IDs do not prove separately administered principals; a new schema field can break old plans; an enabled promotion callback can still be powerful.

Expert witness (Steward identity): the existing clone, deadline, process-tree cleanup, append-only event, and authority code should remain the substrate. Backward-compatible parsing can preserve inert old plans while the local executor fails closed unless execution metadata is present. A sandbox capability receipt can truthfully distinguish compatibility isolation from hostile-code isolation.

Judge (Integrator identity), distinct from the identities above: **adapt**.

## Decision

1. Tournament preparation resolves aliases and rejects output equal to or below the target repository before creating a directory or database.
2. `PortableNode.execution` declares stage kind, execution role and capability, read/write mode, exclusive writer behavior, required outputs, transitions, recovery selection, and cancellation. Old inert plans remain readable; local execution requires the contract.
3. The local executor dispatches by compiled execution metadata, dependencies, capabilities, budgets, and resource leases. The 13-node plan remains a fixture, not an identifier whitelist.
4. Python unittest, Node/TypeScript, Rust compiler-check, and Go adapters own their argv. Missing adapters are verification obligations. The Rust adapter compiles test-configured source to metadata on hosts without a usable linker; it does not claim that those tests executed. Hostile-code requirements fail closed unless the configured sandbox advertises filesystem, network, process, and resource isolation. The local process adapter is labelled trusted-local-only.
5. Local brain projections expose stable ID, title, parent/child, same-idea revision, latest event/disposition, responsibility/return path, rationale, next action, and receipt links without treating Markdown as authority.
6. Independent-principal profiles require content-bound pinned attestations and distinct principal, credential, administrator, and trust-domain identities. Attestation digests cover roles, expiry, and every identity field so a pin cannot authenticate substituted metadata. Local single-operator mode remains explicit.
7. Exhibits deduplicate by content digest. Comparators require pinned version/artifact/outcome and license provenance. Held-out comparisons produce reproducible receipts. The narrow promotion adapter is disabled by default and requires a separately attested promoter and verifier plus a candidate-bound grant whose digest was pinned outside the promotion request; it has no merge, push, or deploy action.

## Acceptance and rollback

Acceptance is executable in `tests/test_tournament_cli.py`, `tests/test_compiled_tournament.py`, `tests/test_verification_adapters.py`, `tests/test_evidence_court.py`, `tests/test_local_evidence_packet.py`, and the local-runtime/recovery suites, followed by `python -m unittest discover -s tests -v` with `PYTHONPATH=src`.

Rollback is one branch revert. Prepared/run/brain artifacts remain external and append-only; discarding the branch cannot mutate a target repository, champion pointer, protected reference, or external system. The exact limitation retained as dissent is that `LocalProcessSandbox` is not hostile-code isolation, particularly on Windows where CPU/memory and network denial are unavailable. Such a configuration must not satisfy a hostile target request.
