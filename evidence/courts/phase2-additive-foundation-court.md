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
- Judge: `Ohm`

## Admitted sources and dispositions

No new semantic or provider claim was introduced; the Phase 1 source register and
court remain their provenance authority. Sixth-remand verification admitted Syft
only as checksum-pinned SBOM tooling, with its release custody and license recorded
in `P2-AUDIT-019`.

| Source class | Phase 2 disposition | Limit |
| --- | --- | --- |
| ADR-018 canonical agent definitions | adopt | inert additive candidate only |
| ADR-019 open memory authority | adopt | local canonical store; no Phase 3 projection |
| ADR-020 provider-native usage/privacy | adapt | repository-owned fixtures only; no live-provider claim |
| SQLite behavior exercised by the repository | adopt | local WAL transaction and append-only triggers |
| OpenTelemetry GenAI vocabulary | adapt | dependency-free local envelope; evolving vocabulary is not accounting truth |
| Syft v1.50.0 release, Apache-2.0 | adopt | checksum-pinned CI verification tool only; no runtime or vulnerability-absence claim |
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

Third implementation candidate
`d20ee1a469b716f1a62d8d4a24c338fe66dda066`: `remand`.

Its full declared CI matrix passed and every earlier remand was closed. Curator
`Kuhn` nevertheless reproduced missing caller paths for required usage attribution
and an unusable string-valued billable reconciliation axis. Steward `Planck`
independently reproduced acceptance of a 4,000-digit token integer, direct
`TraceRecord` construction bypassing projection privacy/bounds, and undetected
cross-repository opportunity-key retargeting. The Builder accepted all five
findings. CI success did not displace the court burden; remediation is recorded
append-only in `P2-AUDIT-013`.

Implementation promotion remains pending fresh exact-candidate Curator/Steward
reconstruction and a different Judge.

Third-remand remediation implementation
`ca40eb59b2d5569e5f3dbcd05a6874cd53b3867a` is the next review candidate. Its
evidence-only descendant may be reviewed as the exact PR head provided the
implementation tree is identical. No acceptance or promotion verdict is asserted
before fresh Curator and Steward reconstruction.

Fourth implementation candidate
`91fd5cff7e7b1e2d2b3203baaf67a2127e629f95`: `remand`.

Curator `Kuhn` independently forged a previously valid attribution object after
construction and proved recorder admission plus the usage schema accepted unbounded
and invalid attribution. The exact-head push matrix passed; the PR matrix also
preserved one adverse Python 3.12 seeded worker-recovery failure despite the same
suite passing on the push event. The Builder accepted the boundary finding and did
not waive or conceal the adverse CI receipt. Remediation is recorded in
`P2-AUDIT-015`; fresh exact-head review remains required.

Fourth-remand remediation implementation
`144e943d6cf830734e40d89d4cee41e4f15de714` is the next review candidate. An
evidence-only descendant may be reviewed as the exact PR head only if its source,
tests, scripts, and project configuration remain byte-identical. No acceptance is
asserted before fresh Curator and Steward reconstruction.

Fifth implementation candidate
`36535f136cbebc553af7693fb6ae5f5dba75c0f2`: `remand`.

Curator `Kuhn` and Steward `Planck` independently constructed and mutated authority
decisions that bypassed the claimed role/policy/lease/adapter/risk/budget
intersection and durably registered a repository. The Builder accepted the finding.
The PR workflow passed, while the push workflow retained an adverse Python 3.14
seeded worker-recovery receipt; the earlier Python 3.12 adverse receipt also remains
in the ledger. Remediation is recorded in `P2-AUDIT-017`; no acceptance is asserted.

Fifth-remand remediation implementation
`ace73253cdd61ef870ed4e2caacb2f4d91b1ef57` is the next review candidate. An
evidence-only descendant may be reviewed as the exact PR head only if its source,
tests, scripts, and project configuration remain byte-identical. Fresh Curator and
Steward acceptance remains required.

Sixth implementation candidate
`d045204c5b7d620078eb0ae3de67397d5ff02a74`: `remand`.

Curator `Kuhn` and Steward `Planck` independently accepted the implementation and
exact compatibility record. Judge `Ohm` found that both green SBOM jobs ignored
unsupported action inputs, discovered zero packages, retained only the wheel, and
attested only the wheel. Courtroom fail-closed rules prohibit substituting a green
job label for the missing SBOM/provenance exhibits. The exact push and PR job IDs,
including the preserved same-SHA Python 3.11 adverse attempt, are recorded in
`P2-AUDIT-018`.

Sixth-remand remediation is recorded in `P2-AUDIT-019`. It changes only the
supply-chain workflow and recovery contract: the Syft release URI, version, archive
digest, and Apache-2.0 license are explicit; the archive is verified before Syft
scans the installed wheel; an independent verifier requires the exact package in a
nonempty SPDX 2.3 document; and upload/provenance explicitly bind both wheel and
SBOM. No acceptance is asserted before fresh exact-head receipts and independent
reconstruction.

Sixth-remand candidate
`69ae532566ba0f780b7fb24832dee70484aa738d`: `adopt`.

Curator `Kuhn` and Steward `Planck` independently returned `accept` from clean
reconstructions. Distinct Judge `Ohm` downloaded the retained two-file artifact,
parsed the project-bearing SPDX 2.3 SBOM, and cryptographically verified the wheel
and SBOM against one exact-head SLSA provenance statement. Both exact-head push and
PR matrices passed. Exact receipts, digests, job IDs, identities, adverse history,
and inventory counts are preserved in `P2-AUDIT-020`.

## Final Phase 2 disposition

`adopt` the inert additive memory and telemetry foundation governed by ADR-021.
Generation Zero remains the selected runtime. No Obsidian projection, provider
support, external delivery, publication workflow, or Phase 3 behavior is activated.
Rollback remains removal of the explicit opt-in while retaining append-only records
and dissent. Phase 2 is complete at the accepted candidate; merging remains outside
this court and was not performed.
