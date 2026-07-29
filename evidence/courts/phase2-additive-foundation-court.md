# Phase 2 additive foundation court

- Case: `P2-FOUNDATION-001`
- Base: `3298078c41ce69103eb2bdce61960a69dc6aab93`
- Scope: Phase 2 only
- Clerk/Orchestrator: `Codex-root`
- Explorer/Expert: `Wegener`
- Architect/Cross-Examiner: `Gibbs`
- Builder: `Codex-root`
- Curator: `Kuhn`
- Steward: `Planck`
- Judge: pending exact-candidate appointment

## Admitted sources and dispositions

No new external source or provider claim was introduced. The Phase 1 source register
and court remain the provenance authority.

| Source class | Phase 2 disposition | Limit |
| --- | --- | --- |
| ADR-018 canonical agent definitions | adopt | inert additive candidate only |
| ADR-019 open memory authority | adopt | local canonical store; no Phase 3 projection |
| ADR-020 provider-native usage/privacy | adapt | repository-owned fixtures only; no live-provider claim |
| SQLite behavior exercised by the repository | adopt | local WAL transaction and append-only triggers |
| OpenTelemetry GenAI vocabulary | adapt | dependency-free local envelope; evolving vocabulary is not accounting truth |
| Provider documentation previously quarantined | quarantine | no inferred billing, cache, or reasoning semantics |
| Prometheus, MLflow, JSON-LD, Armory, AgentTelemetry | defer/quarantine per Phase 1 | no implementation dependency or conformance claim |

Unavailable live invoices and live provider receipts are not invented. The mechanism
must report unavailable/unknown and retain the gap.

## Atomic claims and verdicts

| Claim | Advocate | Cross-examination | Verdict | Receipt |
| --- | --- | --- | --- | --- |
| One new foundation store can atomically bind memory and outbox | Separate databases avoid coupling | Separate databases create cross-store partial commits | adopt | store transaction tests |
| Existing `EvidenceLedger` should gain Phase 2 tables | Reuses a known path | Mutates the frozen Generation Zero database shape | reject | legacy characterization remains green |
| Foundation schemas belong in the legacy catalog | One loader is convenient | Breaks the frozen 20-schema receipt and implies v1 support | reject | separate 17-schema catalog |
| Exact and structured opportunity collisions can converge | SQLite uniqueness plus immediate transaction | Arrival order could erase encounters | adapt: encounter first, stable key, retain both | concurrent race test |
| Semantic similarity can merge opportunities | Reduces duplicates | False merge erases dissent and is model/index dependent | reject | semantic candidate/non-merge test |
| Native provider-shaped usage can be normalized | Enables accounting | Current docs are quarantined; fields may overlap | adapt: bounded numeric paths and versioned partial axes | OpenAI/Anthropic fixtures |
| Missing usage can be treated as zero | Simplifies totals | Fabricates accounting completeness | reject | missing/malformed fixture tests |
| Usage can be rewritten after outcome | Gives a convenient aggregate | Rewrites history and confuses arm with stance | reject | append-only record/relations contract |
| Delivery state can update an outbox row | Common queue design | Hides attempts and violates append-only evidence | adapt: immutable message, attempts, acknowledgement | replay/ack tests |
| Outbound telemetry is required | Familiar operations stack | Adds network/privacy/dependency authority | reject | exporter-disabled OTel envelope |
| v2 candidates may self-declare authority | Makes agent definitions portable | Capability is not authority | reject | authority intersection tests |
| Optional provider wrapping satisfies additive runtime use | Receipts real attempts without changing v1 | Wrapper could be mistaken for default activation | adapt: internal opt-in only, no facade/CLI selector | receipted-provider test |

## Threat and privacy examination

The court examined database compromise, low-entropy digest correlation, prompt/body
leakage, raw error leakage, tenant crossover, concurrent dedup races, false semantic
merges, duplicate delivery, crash between start and terminal, invoice duplication,
generated drift, and provider semantic drift.

Mitigations are scoped queries, explicit identities, private defaults, prohibited body
keys, bounded symbolic errors, append-only triggers, immediate transactions, explicit
unknown accounting, candidate-only semantic relations, disabled export, and
deterministic byte checks. Physical erasure of append-only sensitive data remains an
explicit later legal/design obligation; Phase 2 minimizes content and uses governed
references rather than claiming deletion.

## Preserved dissent

The unified store is a larger compromise target and local bottleneck. The outbox
provides durable replay, not exactly-once external execution or atomicity with legacy
stores. Synthetic fixtures can mask provider drift. OpenTelemetry vocabulary can
change. Content digests can still leak low-entropy material. These limitations block
activation/support claims but do not block an inert, local Phase 2 foundation.

## Preliminary disposition

Architecture: `adopt`.

Initial implementation candidate
`1754f568900a0e19517c0586c0406fe4164d8597`: `remand`.

The Curator and Steward independently reproduced authority, admission, relation,
attempt identity/retry, privacy/cardinality, schema/type, command idempotency,
canonical-source, delivery, integrity, and characterization failures. The Builder
accepted every finding. The append-only remediation record is
`P2-AUDIT-009`; 22 adversarial tests now exercise the failures directly.

Implementation promotion remains pending fresh Curator/Steward reconstruction and a
different Judge on the remediated exact committed candidate. Until that disposition,
Generation Zero remains the only selected runtime.

Second implementation candidate
`b881f75dbc4a23062511fed8c90a2e107ddda8f8`: `remand`.

Its full declared CI matrix passed, but Curator `Kuhn` and Steward `Planck`
independently found incomplete memory kinds, outbox scope, canonical digest/generator
binding, nested contract strictness, per-axis evidence, provider/trace bounds,
conflict propagation, initialization recovery, semantic staging, observed-time
idempotency, public-release provenance, and opportunity-key integrity. CI success did
not displace the court burden. The Builder accepted every finding; remediation is
recorded append-only in `P2-AUDIT-011`.

Implementation promotion remains pending fresh Curator/Steward reconstruction and a
different Judge on the next exact committed candidate.
