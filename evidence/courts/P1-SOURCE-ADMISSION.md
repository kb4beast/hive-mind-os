# Phase 1 Source Admission Court

- Case ID: `P1-SOURCE-ADMISSION`
- Register:
  `evidence/sources/PHASE1_PRIMARY_SOURCE_REGISTER.md`
- Decision scope: architecture evidence only; no third-party code copied
- Decided for Phase 1: 2026-07-28
- Status: all registered source groups have an explicit disposition

## Participants and burden

The Phase 1 Explorer/Clerk preserved locators, versions, digests, licenses, and
unavailable evidence. The Advocate presents only the narrow claims below. The
Cross-Examiner rejects source popularity, mutable documentation, anonymous
papers, and a locator alone as proof. The security/privacy Expert requires
minimal collection, default-deny projection, tenant isolation, and no
executable content. The independent Curator and Judge receipts for the final
candidate are separate records.

Admission here means a pinned source may support the stated architecture claim.
It does not admit copied implementation, establish host support, prove
superiority, or close the founding docket’s unrelated source blockers.

## Atomic source claims and dispositions

### `P1SRC-OBSIDIAN-HELP` — `adapt`

- `SRC-OB-01`: An Obsidian vault is a local filesystem folder containing
  Markdown notes.
- `SRC-OB-02`: Ordinary editors can operate on those files.
- `SRC-OB-03`: Obsidian watches local-file changes, while remote Git changes
  still require Git to update the local tree.
- `SRC-OB-04`: `.obsidian/` contains vault configuration and workspace files
  are volatile.
- `SRC-OB-05`: Nested vaults can produce link-update problems.
- `SRC-OB-06`: Properties, Bases, Graph, Canvas, URI, Sync, plugins, and CLI are
  distinct optional surfaces with different trust and update boundaries.

The official help repository is pinned at
`29e89022c6aeb0a9e9971b6f0c98733dbc2eb716` with per-page digests in the
register. The factual claims are admitted by reference only. Because the help
repository has no root license file, Hive Mind OS may cite and independently
implement interoperable behavior but may not redistribute or copy the help
text. This limitation does not block the adopted repository-as-vault
architecture.

### `P1SRC-OBSIDIAN-LICENSE` — `reject`

The application-use license is not documentation-reuse permission and is not
an architecture or implementation specification. Retain the locator for
product-use context only.

### `P1SRC-JSON-CANVAS` — `adapt`

- `SRC-CANVAS-01`: JSON Canvas 1.0 defines portable node and edge objects.
- `SRC-CANVAS-02`: The MIT-licensed format may be an optional projection
  target.

The pinned commit
`456f843cb293df4f4ab1763e22ccb46a80b307c8`, specification digest, and MIT
license are admitted. Canvas remains a rebuildable optional view, not memory
authority and not a Phase 1 runtime deliverable.

### `P1SRC-OTEL-GENAI` — `adapt`

- `SRC-OTEL-01`: Versioned GenAI semantic conventions provide useful
  observability vocabulary for model, agent, and tool spans/metrics.
- `SRC-OTEL-02`: Development-status conventions are not accounting,
  authorization, privacy, or invoice authority.

The pinned commit
`799e014b68f0e786dc44d9117c30758c5f864510`, document digests, and
Apache-2.0 license are admitted as a replaceable interoperability reference.
Hive Mind OS retains native events and its own versioned normalized contract.

### `P1SRC-PROMETHEUS` — `defer`

The bounded-label and instrumentation principles are consistent with the
independent privacy/threat analysis, but the exact cited document bytes were
not retained. The architecture requirement is adopted on first principles;
Prometheus-specific claim admission is deferred until an exact path/version
bundle is docketed. No Phase 1 claim depends on this source.

### `P1SRC-PROVIDER-DOCS` — `quarantine`

The OpenAI, Anthropic, and Google documentation locators are mutable and no
immutable byte/license bundle was retained. They are discovery locators only.
No provider semantics are admitted from them. Generation Zero provider
behavior is established by live code and fixtures; Phase 2 must add
version-pinned provider conformance fixtures before implementing native usage
mapping.

### `P1SRC-MLFLOW` — `defer`

The mutable `latest` pages are not admitted. Absolute and relative evaluation
gates are adopted independently; MLflow integration or copied threshold
semantics require an exact pin, license receipt, measured need, and separate
court.

### `P1SRC-LM-EVAL-HARNESS` — `adapt`

- `SRC-EVAL-01`: Evaluation tasks and versions should be explicit and
  reproducible.
- `SRC-EVAL-02`: A harness is an implementation reference, not proof that a
  Hive Mind OS comparison is fair.

Commit `f4d4b3de3ee6741a7151a9fe74945ee515262f4c`, the guide digest, and MIT
license are admitted for evaluation design reference only.

### `P1SRC-LIVEBENCH` — `adapt`

- `SRC-LIVE-01`: Benchmark freshness and contamination resistance are
  material evaluation concerns.
- `SRC-LIVE-02`: One paper does not establish external validity or superiority
  for Hive Mind OS.

`arXiv:2406.19314v2` and its retained PDF digest are admitted as research
testimony, not code or a required benchmark dependency. The repository’s
stricter point-in-time and sealed-holdout rules remain authoritative.

### `P1SRC-AGENTTELEMETRY` — `quarantine`

Search discovery now identifies a paper titled *AgentTelemetry: A Fault
Detection Benchmark and Toolkit for LLM Agent Observability* at the registered
OpenReview ID, but direct retrieval remains challenge-gated in this
environment and the available paper identifies anonymous authors and an
anonymous repository. No retained PDF digest, stable authorship, peer-review
decision, or implementation license exists in the repository. None of its
numeric or superiority claims is admitted. The locator remains useful for a
future source-ingestion appeal and no Phase 1 architecture depends on it.

### `P1SRC-W3C-PROV-O` — `adapt`

- `SRC-PROV-01`: A standard provenance vocabulary can support optional export
  and federation mappings.
- `SRC-PROV-02`: PROV-O need not become the internal canonical memory schema.

The immutable 2013 Recommendation and digest are admitted under W3C document
use rules as an interoperability reference. Internal adoption is deferred
until measured value outweighs complexity.

### `P1SRC-W3C-JSON-LD` — `defer`

The immutable 2020 Recommendation and digest are authentic, but Hive Mind OS
has not demonstrated a need for JSON-LD in its Phase 2 internal store.
Admission as a required encoding is deferred; a later federation court may
adapt it as an optional projection.

### `P1SRC-PR27-PROCESS-EVIDENCE` — `adopt`

The repository merge commit
`b032a9f32f48889e0889fae8d6dd04eb03f46b63` and its governing court are
admitted as internal baseline/process evidence. They do not prove the Phase 1
redesign.

### Exact “Armory” source — `quarantine`

The mission brief names a concept but supplies no unique locator. Current
search produces multiple unrelated or newly published products and
repositories. Inferring which one the user intended would invent provenance.
No Armory content, architecture, parity, or superiority claim is admitted.
Reopening requires the exact locator, version/commit, bytes, license, atomic
claims, counterclaims, expert testimony, and an independent source court.

## Advocate case

The admitted/adapted sources support only interoperable file formats,
observability vocabulary, reproducible evaluation concerns, and provenance
mapping. The canonical contracts remain grounded primarily in the user’s
requirements, Generation Zero evidence, and repository constitutional rules,
so mutable or unavailable sources cannot silently control the design.

## Cross-examination and dissent

- Documentation facts can change and citation is not permission to copy.
- Development conventions can drift or encode vendor assumptions.
- Optional standards can add complexity and lock-in without measured value.
- Research results may not reproduce or generalize.
- Anonymous and challenge-gated evidence cannot carry a production burden.
- New search results with the word “Armory” do not identify the intended
  source.

These objections are retained by narrowing dispositions rather than deleting
sources.

## Result and appeal

Every Phase 1 source group is now `adopt`, `adapt`, `defer`, `reject`, or
`quarantine`. Deferred and quarantined sources do not block Phase 1 because no
adopted Phase 1 contract depends on their unavailable content. They do block
any later implementation or claim that cites them as authority until their
stated evidence obligation is satisfied.
