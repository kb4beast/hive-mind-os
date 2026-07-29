# Phase 1 Atomic Claim Register

- Case ID: `P1-ATOMIC-CLAIM-REGISTER`
- Source: `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`
- Source SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`
- Status: 100 material claims preserved and individually disposed
- Governing contracts:
  `docs/architecture/PHASE1_CANONICAL_CONTRACTS.md`

`adopt-design` means the architecture requirement is adopted now while its
production implementation remains assigned to the delivery phase shown.
`adapt-design` retains the requirement with the stated bound. `defer` and
`quarantine` are explicit dispositions, not silent omission.

## Obsidian and open-brain claims

| ID | Atomic claim | Disposition | Delivery |
| --- | --- | --- | --- |
| `OB-001` | A repository folder can be opened directly as the initial Obsidian vault. | adopt-design | Phase 1 policy |
| `OB-002` | Existing repository Markdown is immediately readable without an importer. | adopt-design | Phase 1 policy |
| `OB-003` | Obsidian is a human workbench and not a Python execution host. | adopt-design | Phase 1 boundary |
| `OB-004` | The OS must remain usable without Obsidian. | adopt-design | Phase 3 |
| `OB-005` | No account, paid Sync service, community plugin, or proprietary database may be required. | adopt-design | Phase 3 |
| `OB-006` | Local filesystem changes may refresh automatically, but remote Git synchronization remains explicit. | adopt-design | Phase 1 documentation |
| `OB-007` | `.obsidian/` configuration is local-only and ignored initially. | adopt-design | Phase 1 `.gitignore` |
| `OB-008` | Curated shared Obsidian settings require a later security and update court. | defer | Separate post-Phase 3 court |
| `OB-009` | Generated brain notes are deterministic projections of canonical memory. | adopt-design | Phase 3 |
| `OB-010` | Generated notes cannot grant authority or mutate canonical state. | adopt-design | Phase 3 |
| `OB-011` | Generated and human-authored namespaces must remain separate. | adopt-design | Phase 3 |
| `OB-012` | Projection writes require staging, validation, expected-prior-digest comparison, and atomic replacement. | adopt-design | Phase 3 |
| `OB-013` | Concurrent human edits must produce preserved conflicts, not silent overwrite. | adopt-design | Phase 3 |
| `OB-014` | Safe-public projection must default-deny sensitive content and record redactions. | adopt-design | Phase 3 |
| `OB-015` | Generated views must not be re-ingested as sources, ideas, or telemetry. | adopt-design | Phase 3 |
| `OB-016` | A human Obsidian Inbox is an untrusted proposal path with dry run, validation, idempotency, policy, and court gates. | defer | Optional separate Phase 3 court |
| `OB-017` | Bases and JSON Canvas may be optional portable views, never canonical truth. | adapt-design | Phase 3 |
| `OB-018` | Obsidian plugins, watchers, executable Markdown, nested vaults, and Sync writers are unjustified in Phase 1. | reject | Phase 1 |

## Memory and opportunity claims

| ID | Atomic claim | Disposition | Delivery |
| --- | --- | --- | --- |
| `MEM-001` | Canonical memory must be open, local-first, provider-neutral, append-only, and versioned. | adopt-design | Phase 2 |
| `MEM-002` | Every record needs stable identity, repository instance, tenant, type, schema version, provenance, digest, and timestamps. | adopt-design | Phase 2 |
| `MEM-003` | Every record needs sensitivity, retention, access purpose, confidence, status, and owner. | adopt-design | Phase 2 |
| `MEM-004` | Supersession and tombstones preserve history without pretending sensitive payloads can never be erased. | adopt-design | Phase 2 |
| `MEM-005` | Private hidden chain-of-thought is excluded from memory. | adopt-design | Phase 2 |
| `MEM-006` | Working memory records bounded resumable mission state. | adopt-design | Phase 2 |
| `MEM-007` | Episodic memory records runs, actions, retries, errors, handoffs, and receipts. | adopt-design | Phase 2 |
| `MEM-008` | Semantic memory records durable facts, concepts, sources, claims, and relations. | adopt-design | Phase 2 |
| `MEM-009` | Procedural memory records versioned skills, playbooks, runbooks, and evaluations. | adopt-design | Phase 2 |
| `MEM-010` | Prospective memory records deferred work, review dates, dependencies, and wakeups. | adopt-design | Phase 2 |
| `MEM-011` | Decision memory records alternatives, testimony, dissent, verdicts, assumptions, and rollback. | adopt-design | Phase 2 |
| `MEM-012` | Opportunity memory records every idea and its lifecycle. | adopt-design | Phase 2 |
| `MEM-013` | Counterfactual memory retains failures, rejected ideas, losing designs, and negative results. | adopt-design | Phase 2 |
| `MEM-014` | Social memory records actor identity, independence, ownership, delegation, and accountability. | adopt-design | Phase 2 |
| `MEM-015` | Evaluation and resource memory records cohorts, holdouts, metrics, budgets, tokens, cost, time, tools, and waste classification. | adopt-design | Phase 2 |
| `MEM-016` | Governance memory records leases, permissions, denials, quarantine, appeals, and rehabilitation. | adopt-design | Phase 2 |
| `MEM-017` | Every material mission object requires a memory record or explicit not-applicable disposition. | adopt-design | Phase 2 |
| `MEM-018` | Every Explorer encounter requires a durable relation or disposition, including filtered and duplicate candidates. | adopt-design | Phase 2 |
| `MEM-019` | Exact duplicate ideas are deterministically prevented under concurrency. | adopt-design | Phase 2 |
| `MEM-020` | Semantic similarity is only a candidate index and cannot silently merge contradictions or refinements. | adopt-design | Phase 2 |
| `MEM-021` | False semantic merges require measurable error bounds and an appeal path. | adopt-design | Phase 2 |
| `MEM-022` | Retrieval must receipt selected and omitted memory IDs, ordering, purpose, policy, and critical-context coverage. | adopt-design | Phase 2 |
| `MEM-023` | Quarantined memory is excluded from normal retrieval and forensic access is receipted. | adopt-design | Phase 2 |
| `MEM-024` | Federation must enforce repository and tenant isolation and prevent cross-vault identity from becoming canonical. | adopt-design | Phase 3 |
| `MEM-025` | Self-hosting must prevent projection, ingestion, telemetry, idea, and delegation recursion. | adopt-design | Phase 3 |

## Agent, skill, prompt, and portability claims

| ID | Atomic claim | Disposition | Delivery |
| --- | --- | --- | --- |
| `AG-001` | One versioned agent definition must own each challenger’s identity and behavioral contract. | adopt-design | Phase 2 |
| `AG-002` | All eight constitutional roles remain mandatory and separately identifiable. | adopt-design | Phase 2 |
| `AG-003` | A ninth constitutional role requires a constitutional ADR, migration, tests, and independent promotion. | adopt-design | Later constitutional court |
| `AG-004` | Role enum iteration cannot define lifecycle order. | adopt-design | Phase 1 contract |
| `AG-005` | Agent definitions must include typed inputs, outputs, quality gates, stop conditions, and evaluation references. | adopt-design | Phase 2 |
| `AG-006` | Agent definitions must include requested capabilities, authority ceiling, memory boundaries, budgets, and rollback. | adopt-design | Phase 2 |
| `AG-007` | Capability declarations are requests and never grants. | adopt-design | Phase 1 authority boundary |
| `AG-008` | Effective authority is the intersection of role ceiling, policy, lease/grant, adapter enforcement, risk, and budget. | adopt-design | Phase 2 |
| `AG-009` | Unknown capability-to-policy mappings fail closed. | adopt-design | Phase 2 |
| `AG-010` | Skills are typed, versioned, bounded, independently testable procedures rather than role biographies. | adopt-design | Phase 2 |
| `AG-011` | Skill reuse cannot merge actor, verifier, approver, or judge identity. | adopt-design | Phase 2 |
| `AG-012` | Tools are typed enforced adapters and descriptions alone cannot authorize or execute. | adopt-design | Phase 2 |
| `AG-013` | Prompts are deterministic content-addressed projections of ordered canonical layers. | adopt-design | Phase 2 |
| `AG-014` | Context composition must preserve blockers, dissent, authority, provenance, rollback, and selected/omitted receipts. | adopt-design | Phase 2 |
| `AG-015` | Host projections are nonauthoritative and must report unsupported or degraded semantics. | adopt-design | Phase 7 |
| `AG-016` | A manifest or JSON profile alone cannot establish host support. | adopt-design | Phase 7 |
| `AG-017` | The core fails closed when a host cannot preserve authority, independence, evidence, or rollback. | adopt-design | Phase 7 |
| `AG-018` | Explorer may research broadly but cannot modify production or approve its own findings. | adopt-design | Phase 4 |
| `AG-019` | Explorer must perform repository/history/user/external discovery, counterargument, cross-domain synthesis, and honest stopping. | adopt-design | Phase 4 |
| `AG-020` | Explorer candidates require provenance, collision handling, executable acceptance criteria, metrics, and explicit disposition. | adopt-design | Phase 4 |
| `AG-021` | The other seven roles require equivalent depth and independent behavioral evaluation. | adopt-design | Phase 5 |
| `AG-022` | OODA, lifecycle, courtroom, War Room, handoff, and evidence are workflow state, not duplicate role authority. | adopt-design | Phase 2 |
| `AG-023` | New extensions begin inert and quarantined, with source/license, schema, isolation, evaluation, and rollback gates. | adopt-design | Phase 2 and Phase 6 |
| `AG-024` | An extension cannot alter the constitution, policy, evidence burden, evaluator, or its own promotion path. | adopt-design | Phase 2 |
| `AG-025` | The exact intended Armory source is unidentified, so no Armory semantics are admitted. | quarantine | Reopen only with exact source evidence |

## Usage, telemetry, budget, and learning claims

| ID | Atomic claim | Disposition | Delivery |
| --- | --- | --- | --- |
| `TEL-001` | Every model and governed tool attempt needs a usage event or explicit unknown-accounting failure. | adopt-design | Phase 2 |
| `TEL-002` | Provider-native usage fields and meanings remain immutable with provenance. | adopt-design | Phase 2 |
| `TEL-003` | Normalized usage is versioned and derived without overwriting native observations. | adopt-design | Phase 2 |
| `TEL-004` | Input/output, cached/uncached, reasoning, modality, and billable dimensions are orthogonal axes. | adopt-design | Phase 2 |
| `TEL-005` | Inclusive and exclusive token dimensions are never blindly summed. | adopt-design | Phase 2 |
| `TEL-006` | Missing usage is unknown, never zero. | adopt-design | Phase 2 |
| `TEL-007` | Estimates, provider reports, host reports, price cards, and invoices remain separate observations. | adopt-design | Phase 2 |
| `TEL-008` | Cost records require amount, currency, price-card version, provenance, and uncertainty. | adopt-design | Phase 2 |
| `TEL-009` | Every retry has its own attempt receipt and one terminal relationship. | adopt-design | Phase 2 |
| `TEL-010` | Usage correlation includes repository, mission, run, step, role, idea, case, experiment, stance, evaluation arm, and trace. | adopt-design | Phase 2 |
| `TEL-011` | Default telemetry excludes prompt/response bodies, secrets, hidden reasoning, and private repository content. | adopt-design | Phase 2 |
| `TEL-012` | Sensitive summaries, digests, identifiers, and errors still require classification, retention, redaction, and access audit. | adopt-design | Phase 2 |
| `TEL-013` | Metrics use bounded labels and high-cardinality IDs remain in governed records or traces. | adopt-design | Phase 2 |
| `TEL-014` | Local collection works with exporters disabled and no outbound service. | adopt-design | Phase 2 |
| `TEL-015` | Exporters are replaceable and cannot expand collection authority. | adopt-design | Phase 2 |
| `TEL-016` | Hierarchical resource leases reserve checkpoint capacity and stop safely at hard limits. | adopt-design | Phase 6 |
| `TEL-017` | Loop, stall, retry-storm, and context-churn detectors escalate proportionally and reversibly. | adopt-design | Phase 6 |
| `TEL-018` | Quarantine is scoped, receipted, appealable, rehabilitatable, and never based only on token volume. | adopt-design | Phase 6 |
| `TEL-019` | Champion/challenger comparison seals tasks, commits, memory, identities, tools, budgets, models, metrics, and access logs. | adopt-design | Phase 6 |
| `TEL-020` | Both arms face absolute value/trust gates; either may fail and inconclusive evidence promotes neither. | adopt-design | Phase 6 |

## Governance, delivery, and compatibility claims

| ID | Atomic claim | Disposition | Delivery |
| --- | --- | --- | --- |
| `GOV-001` | Phase 1 freezes Generation Zero before any replacement. | adopt-design | Phase 1 |
| `GOV-002` | The 131 root, 33 package, and 13 CLI supported contracts cannot silently drift. | adopt-design | Phase 1 regression |
| `GOV-003` | De-facto module definitions are migration evidence, not a new support promise. | adapt-design | Phase 1 |
| `GOV-004` | Every material source and claim receives provenance, advocacy, cross-examination, expert review, judgment, dissent, and rollback mapping. | adopt-design | All phases |
| `GOV-005` | Unavailable sources remain blocking evidence obligations and their content is not invented. | adopt-design | All phases |
| `GOV-006` | Source registration is not source admission. | adopt-design | Phase 1 source court |
| `GOV-007` | Phase 1 architecture adoption does not authorize Phase 2 production implementation. | adopt-design | Phase 1 |
| `GOV-008` | No PR is merged and `main` is not modified by this delivery. | adopt-design | Phase 1 delivery |
| `GOV-009` | Characterization limitations, adverse evidence, dissent, and losing alternatives remain append-only. | adopt-design | Phase 1 evidence |
| `GOV-010` | Rollback is executable or objectively inspectable and cannot erase challengers, evidence, or dissent. | adopt-design | All phases |
| `GOV-011` | Full tests, security, package, provenance, and independent exact-head receipts gate completion. | adopt-design | Phase 1 delivery |
| `GOV-012` | The next eligible objective after a complete Phase 1 is Phase 2 additive memory and telemetry foundation. | adopt-design | Phase 2 |

## Court result

All 100 claims have an explicit disposition and delivery boundary. Phase 1
adopts the architecture contracts without claiming their later-phase runtime
implementation. The exact Armory semantics remain quarantined, optional
Obsidian intake/shared settings remain separately deferred, and no source gap
is represented as completed evidence.
