# Bounded Memory Context Receipt

CONTEXT-230 compiles role-scoped context from immutable memory metadata and
content-addressed evidence. A context request binds the mission, work item,
attempt, role, charter digest, authority digest, explicit sensitivity scopes,
and deterministic time. Retrieval applies access, lifecycle, scope, validity,
freshness, and provenance gates before ranking.

The existing `ContextManifest` remains the compact selection contract. Its warm
and cold record IDs are accompanied by an immutable binding receipt under the
caller-selected context root. Each binding records the selected record digest,
source references, sensitivity, validity window and freshness score, authority
level and request authority digest, mission, work, role, access roles/scopes,
and evaluator visibility. The binding has its own canonical digest and cannot
be rewritten. Memory bodies are never copied into manifests or binding receipts.

Curator/evaluator compilation excludes records marked unavailable to evaluators
and all `scratchpad` or `self_assessment` classes, including Builder scratchpad
material. Records without source references are excluded from compiled context
and counted as missing provenance. A cold reference is metadata only; selecting
it requires an explicit new manifest revision, leaving the prior manifest and
its receipt unchanged.

Memory correction, contradiction, expiry, and quarantine are append-only
lifecycle facts. The original record and artifact remain addressable, while the
active projection is rebuilt from immutable records, lifecycle events, and
conflict records. Repository-learning point-in-time episodes retain target and
future commits as hidden inputs until the corresponding seal and reject access
to their SHAs.

Acceptance evidence is covered by
`tests/test_hive_cortex_context.py` and the existing kernel memory/context and
repository-learning suites. Rollback is a revert of the node commit; retained
artifacts, manifests, receipts, and adverse lifecycle evidence are not rewritten.
