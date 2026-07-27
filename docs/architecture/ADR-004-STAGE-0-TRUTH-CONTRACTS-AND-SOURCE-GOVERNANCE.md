# ADR-004: Stage 0 Truth Contracts and Source Governance

- **Status:** Accepted for bounded Stage 0 repository implementation; source and remote-host
  obligations remain open
- **Date:** 2026-07-27
- **Scope:** Stage 0 backlog items 3–4 and the in-repository portions of source coverage,
  implementation-state audit, and protected-governance delivery

## Context

ADR-002 established a reproducible current-state audit. ADR-003 replaced label-like receipt
acceptance with content-addressed executable validation. The next Stage 0 obligations were:

1. formal machine-readable contracts;
2. a source-pack fingerprint that binds actual bytes;
3. separate governed intake of the user-supplied sibling classic-GPT pack and images;
4. machine blocking for claims derived from incomplete evidence;
5. truthful maturity reporting; and
6. repository governance and CI suitable for constitutional code.

The prior tracked GPT fingerprint hashed declarations, not the files. Its runtime-state JSON
was an example rather than a formal schema. The sibling pack existed outside Git history,
contained a stale instruction filename, omitted its actual instruction and images from its
manifest, and supplied no license or executable validator. Existing `implemented` labels
also did not distinguish typed prototypes from production proof.

## Decision

### Formal contracts

Ship strict Draft 2020-12 schemas for source, claim, event, identity, capability lease,
policy decision, tool intent, tool receipt, mission state, handoff, and artifact manifest.
Package them with the Python distribution. A standard-library validator implements the
contract subset used by these schemas and rejects unknown fields, runtime type confusion,
invalid enums, malformed portable paths, and unresolved local references.

The mission-state validator additionally checks relationships JSON Schema cannot express
concisely: unique roles/actions/receipts/executions, exact mission/state/action/policy/lease
receipt binding, handoff binding, actor/verifier separation, all-eight-role completion,
resolved blockers, and successful receipts for every side effect.

### Byte-bound tracked GPT pack

Advance the tracked pack to schema 3. Its manifest stores ordered paths, priorities, byte
counts, and lowercase SHA-256 digests. The fingerprint is computed from the validated ordered
inventory. Loading fails on an extra file, missing file, reordered declaration, byte
substitution, marker loss, UTF-8 failure, or incompatible manifest schema. An unvalidated
declaration-only pack has no usable fingerprint.

### Governed sibling snapshot

Preserve all 16 original sibling files under
`evidence/sources/SRC-023-classic-gpt-pack/raw/`, including the stale manifest and both image
exhibits. A superseding governed manifest:

- selects `HIVE_MIND_OS_INSTRUCTIONS_V2.txt` as the canonical instruction file;
- inventories every byte and binds the ordered inventory with SHA-256;
- regenerates `HIVE_OS_ALL_IN_ONE.md` from the ten canonical modules in tests/CI;
- records `imgo.jpg` as a non-independent possible-common-origin exhibit for `SRC-002`;
- records `Logo.png` as a derived, non-independent summary;
- preserves the stale analyzed head as historical context, not a current pin; and
- keeps license, authorship, and image chain of custody explicitly unresolved.

Register the pack as new `SRC-023`, never as a mutation of `SRC-022`. Capture four atomic
claims as `CLM-081`–`CLM-084`, all deferred at capture burden until provenance and reuse
rights are resolved.

### Source and implementation truth

The docket auditor records raw-byte digest failures, mutable or ambiguous repository pins,
missing exact commit object types, incomplete ingestion, incomplete provenance, and
unresolved licenses. Every claim depending on incomplete provenance, ingestion, digest, or
repository pin evidence receives an explicit machine-blocking issue. Existing courtroom
decisions remain preserved, but cannot be cited through that blocker for design,
implementation, or promotion.

Add the capability maturity scale:

`specified → structurally_prototyped → executed_in_isolation → independently_verified_e2e → production_proven`

Map current typed implementations no higher than `structurally_prototyped`. The current-state
audit separately labels classic-GPT simulation and partial in-process enforcement, and keeps
the production-proof set empty.

### Repository governance

Commit CODEOWNERS, a machine-checked desired branch-rules contract, Dependabot configuration,
and commit-pinned CI actions. CI covers Python 3.11/3.12/3.14 tests, Ruff, Pyright, CodeQL,
secret scanning, dependency/license review, wheel construction, SPDX SBOM generation, build
artifact retention, and Sigstore-backed GitHub artifact attestation.

Repository files cannot prove GitHub host settings are active. The rules contract therefore
keeps `verification_status` equal to `not_verified_on_remote` and blocks a protected-host
claim until a disjoint observer verifies equivalent active rules.

## Threat delta

| Threat | Control | Residual risk |
|---|---|---|
| Marker-preserving source substitution | Exact byte count and SHA-256 inventory | SHA-256 is integrity, not source authenticity |
| Manifest omission/addition/reorder | Exact set and ordered-record validation | Manifest author identity is not signed locally |
| Runtime state invents authority or completion | Strict schemas plus cross-record truth checks | No external enforcement gateway yet |
| Sibling pack silently replaces prior sources | Additive `SRC-023` and explicit relationships | Authorship/license remain unresolved |
| Image treated as independent proof | Non-independent exhibit classification and blockers | Original `SRC-002` bytes remain missing |
| Typed prototype marketed as production | Capability-maturity audit with empty production set | Future evidence still needs independent adjudication |
| Mutable source ref supports adoption | Pin/object audit plus dependent-claim blocker | Exact external pins still require source retrieval |
| Workflow supply-chain drift | Full action commit SHAs and exact build backend | Action transitive bundles require ongoing review |
| Author self-approves constitutional changes | Two-review/code-owner/last-push rule contract | Host activation is not yet independently verified |

## Acceptance evidence

- Schema catalog and contract truth-boundary tests.
- Tracked source-pack add/remove/substitute/reorder/schema incompatibility tests.
- Sibling snapshot exact-inventory, stale-manifest, deterministic bundle, and image
  classification tests.
- Docket conservation and incomplete-source dependent-claim blocking tests.
- Current-state audit capability-maturity and complete coverage tests.
- Governance tests proving all workflow actions use 40-character commit SHAs and all required
  review/check categories are declared.
- Ruff, Pyright, full test suite, clean build, and a post-commit CurrentStateAudit receipt.

## Migration

- Tracked classic-GPT pack schema 2 becomes schema 3. Callers must load and validate repository
  bytes before obtaining a fingerprint.
- Portable mission state schema 2 becomes schema 3. Legacy examples remain historical evidence
  in ADR-003 and prior audit artifacts.
- CurrentStateAudit schema 4 becomes schema 5 to add source coverage, machine-blocked claims,
  and implementation maturity.
- Docket count advances additively from 22/80 to 23/84. No source, claim, prior manifest, or
  earlier audit is deleted.

## Rollback

Rollback is additive supersession. Restore the prior runtime pack and CurrentStateAudit
readers only through new schema versions; do not delete schema-3/5 artifacts, `SRC-023`,
`CLM-081`–`CLM-084`, the raw source snapshot, adverse findings, or prior digests. CI and
governance rules may be superseded by a stricter reviewed configuration, never silently
weakened to obtain a passing run.

## Open obligations

- Seven videos (`SRC-005`, `SRC-006`, `SRC-016`–`SRC-020`) still lack complete admitted
  transcript/source ingestion.
- Original raw bytes for `SRC-001`, `SRC-002`, `SRC-013`, and `SRC-022` are not preserved.
- `SRC-010`, `SRC-011`, `SRC-014`, and `SRC-015` still need whole-repository commit/tree pins;
  all external sources need retrieval/license coverage appropriate to their use.
- `SRC-023` lacks a verified reuse grant and complete chain of custody.
- Active GitHub repository rules and genuinely independent approval remain unverified.
- No signed external actor identity, durable append-only store, complete-mediation gateway,
  provider reconciliation, production operation, or superiority evidence is claimed.
