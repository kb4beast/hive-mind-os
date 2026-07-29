# Phase 1 Completion Independent Curator Receipt

- Curator and Expert Witness identity:
  `/root/phase1_completion_curator`
- Candidate:
  `0d44b1665d9775b5b889e99c2d56e63db9a010b9`
- PR: `kb4beast/hive-mind-os#29`
- Required base:
  `0948f7ec385238f5825ce7c39dd25de2e9a1035d`
- Reviewed: 2026-07-28
- Verdict: `accept`
- Scope: Phase 1 architecture, evidence, compatibility, and repository-local
  Obsidian policy; no runtime activation

This is an independent reconstruction. The Curator did not act as Builder,
Architect, Advocate, promoter, or Judge and did not rely on commit subjects or
Builder summaries as proof.

## Reconstruction and methods

The Curator independently read `AGENTS.md`, the complete mission handoff and
Phase 1 acceptance criteria, the relevant live role, policy, ledger, mission,
prompt, model/provider, runtime, CLI, package, schema, and projection code, the
complete Phase 1 generator and tests, both generated inventories, ADR-018
through ADR-020, the canonical contracts, rollback plan, authority and runtime
audits, all earlier Phase 1 courts and remands, the source register and
admission court, the 100-claim register, merits court, audit ledger, portable
checkpoint, and the candidate and published-PR diff boundaries.

The candidate was reconstructed in a separate normal detached clone so
verification did not depend on the linked-worktree Git metadata. Direct Git
object comparison established:

- candidate head:
  `0d44b1665d9775b5b889e99c2d56e63db9a010b9`;
- PR #28 head and PR #29 merge base:
  `0948f7ec385238f5825ce7c39dd25de2e9a1035d`;
- PR #29 remains open, draft, and based on
  `codex/repair-ci-test-contract`;
- PR #28 remains open and draft against `main`;
- the candidate and base have the identical `src/hive_mind_os` tree
  `360fda29a0067d9c13d89fdc24b20b5840286bf4`; and
- `git diff --check` passed and no production source, schema, package,
  prompt, database, provider, runtime selector, or CLI implementation changed.

At review time GitHub still published the previous PR #29 head
`ee00967610df9e7d0ec4a5150bac751cc6880105`. Therefore the exact candidate
must still be pushed and receive fresh exact-head checks; this receipt does not
misrepresent unpublished local evidence as a passing PR run.

## Independently reproduced receipts

The focused Generation Zero plus completion suite ran 10 tests under each
supported interpreter:

| Environment | Result |
| --- | --- |
| CPython 3.11, read-only `python:3.11-slim` boundary | 10 passed |
| Windows CPython 3.12 | 10 passed |
| Windows CPython 3.14 | 10 passed |

Each run regenerated the live characterization in memory and matched the
committed fixture and generated inventory. The reproduced contract is:

- 131 `hive_mind_os.__all__` bindings;
- 33 `hive_mind_os.package_system.__all__` bindings;
- 13 semantic CLI parser contracts;
- 304 de-facto module definitions;
- 48 direct event sinks, 53 producing sites, 47 literal event types, 224
  bounded effect sites, and zero unknown matched candidates;
- inventory digest
  `sha256:57ad3e54934f2f1315f71e1d994253ce5d9100e2f161d430354039592e6ec037`;
- inventory-file SHA-256
  `2977cc4e7f2b30b63c5dcf55d3d86cd3a1f648049d8872f1a599131899d48919`;
  and
- fixture SHA-256
  `b679d4dd105df0a4efdd6cbf79b86d2a4aa1ca6255f36982d6a40004d58dd407`.

Ruff passed over `src`, the generator, and both Phase 1 tests. Pyright reported
0 errors, 0 warnings, and 0 information over the same boundary.

An independent Python 3.12 wheel build installed into a new virtual
environment and imported from that environment. Verification found 20 schema
files, 48 `hive-core` package files, 68 total resources, 22 components,
`quarantined` trust, and resource-set digest
`a439cdc93272ff1b3078492a2023447902976e4350335ce6057bb9482267249f`.
That build produced
`hive_mind_os-0.6.0-py3-none-any.whl` with SHA-256
`5cfdbeab89b2ef6bbaa5e8830c06307cd25d01e996b360bdc2000d6cdf53aea2`.
The archive digest differs from the Builder's independently built wheel while
the installed resource digest and contract are identical; deterministic wheel
archive bytes are not claimed.

## Merits findings

1. All seven Phase 1 delivery obligations are represented by separate courts,
   a 100-item atomic claim register, explicit source dispositions, the
   authority/redundancy audit, runtime/effect inventories, executable
   Generation Zero fixtures, and adopted architecture/rollback records.
2. Every registered source group has one of `adopt`, `adapt`, `defer`,
   `reject`, or `quarantine`. Unlicensed Obsidian help text is not copied;
   mutable provider pages, unavailable AgentTelemetry content, and the
   unidentified Armory source are not used as authority.
3. ADR-018, ADR-019, and ADR-020 define the canonical design envelopes
   `hive-agent-definition/v2`, `hive-memory/v1`,
   `hive-obsidian-projection/v1`, and `hive-usage-event/v1`. Their status does
   not select or activate a production champion.
4. Effective authority is fail-closed at the intersection of constitutional
   ceiling, versioned policy action, explicit lease or external grant,
   adapter enforcement, mission risk, and resource budget. A capability,
   package, prompt, skill, host profile, memory record, Obsidian note,
   telemetry record, score, or successful outcome cannot grant authority.
5. Privacy and isolation gates cover secret/private-content exclusion,
   sensitivity and retention, repository and tenant scope, cross-repository
   federation, deletion/tombstone reconciliation, concurrent conflict
   preservation, replay, generated-view re-ingestion, and self-host
   projection/telemetry/idea/delegation recursion.
6. Migration is additive and retains Generation Zero. Rollback disables new
   writers, consumers, projections, or champion pointers while preserving
   records, conflicts, dissent, failures, fixtures, and human-authored notes.
7. Phase 1's only non-evidence repository behavior is the reversible,
   documented `.obsidian/` ignore rule. No Phase 2 schema, writer, exporter,
   projector, host adapter, agent challenger, or learning policy is present.

## Adverse evidence and dissent

- During verification, an unsafe full-suite container exposure of the linked
  worktree's real Git directory allowed a repository-learning fixture to
  create transient commit
  `61a837c0471c45faa74ed8d2a73642c3191cc4cd`. It also rewrote tracked
  worktree bytes. The run was stopped; the commit was never staged for the
  candidate, never pushed, and is unreachable. Exact candidate content,
  branch pointer, index, clean worktree, and merge base were restored and
  independently rechecked before this receipt. This demonstrates why the full
  suite must run in an isolated normal checkout.
- A subsequent detached local clone avoided candidate corruption but its
  complete Python 3.12 run was nonqualifying: a GitHub-protection fixture
  failed because the clone's `origin` was a local filesystem path, and the
  long recovery sequence was stopped after preserving that result. It is not
  represented as a passing full suite.
- Static sink matching remains bounded; aliases, reflection, native code,
  subprocess semantics, and unlisted adapters can evade it.
- Generation Zero still lacks the adopted outbox, complete replay,
  repository identity, privacy classification, provider-native accounting,
  tenant federation, and conflict/recovery mechanisms. Those are explicit
  Phase 2/3 implementation gates, not implemented Phase 1 capabilities.
- The original four court headers retain their historical characterization
  deferral. Their appended merits continuations and this new court chain must
  remain visible so history is not mistaken for the final disposition.
- No host support, production readiness, source completeness, full autonomy,
  or superiority claim is supported.

## Disposition and mandatory conditions

`accept`

The exact candidate satisfies the Phase 1 architecture and compatibility
burden and is eligible for a separate Judge disposition. This acceptance is
not a merge, runtime activation, Phase 2 authorization, or green-delivery
receipt.

Final Phase 1 delivery remains conditional on:

1. a distinct Judge independently adopting the exact candidate or a later
   evidence-only descendant;
2. publication to the existing draft PR #29 without changing its PR #28 base;
3. a fresh exact-published-head complete Python 3.11, 3.12, and 3.14 suite;
4. exact-head Ruff, Pyright, CodeQL, secret scan, dependency review, SBOM,
   clean-wheel installation, provenance, and resource verification; and
5. renewed Curator/Judge review if any material production, generated
   inventory, fixture, scanner, contract, source-disposition, or governing
   architecture content changes.

If any condition fails, the result is remanded. Deferred optional Obsidian
Inbox/shared settings and quarantined Armory, provider-document, and
AgentTelemetry evidence do not block Phase 1 because no adopted Phase 1
contract depends on them; they block only later claims or implementations that
would cite them.
