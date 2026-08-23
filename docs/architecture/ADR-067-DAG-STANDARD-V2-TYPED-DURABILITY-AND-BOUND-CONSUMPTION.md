# ADR-067: DAG Standard V2 typed durability and bound plan consumption

## Status

Corrected local candidate. Earlier Curator/Judge reviews and two full-suite runs were
invalidated by subsequently discovered fail-closed P1s. Fresh independent Curator/Judge
review is required after the corrected frozen payload and qualifying full-CI receipt.
This record does not promote an external runtime or external-plan dispatch.

## Context

The generic round compiler inferred durability providers from locks and English prose.
In the generic-product DAG, provider-looking objectives on `GENERIC-EXECUTOR-400` and
`PUBLIC-RUNTIME-500` could be misclassified. With
`WAVE-HOST-300 -> TASK-REUSE-310`, the heuristic could add the inverse semantic
precedence edge, forming a cycle with the raw dependency. The previous bounded rank
relaxation could stop after an arbitrary iteration cap and emit dependency-invalid
rounds.

The compiler also consumed plan JSON without validating optional `plan_digest` or
per-node `contract_digest`, and emitted `dispatch --plan` for an external plan even
though the installed dispatcher has no such argument.

The historical V1 authoring standard is Git-blob-pinned by the V1 overlay manifest
(`70e43b0a8078a303d44c0109b8dd218a948258c2`). Changing it would invalidate historical
reproduction. This successor therefore adds `DAG_AUTHORING_STANDARD_V2.md` rather
than modifying V1.

## Decision

- Introduce optional V2 node metadata: exclusive `durability_role` values
  `provider`, `consumer`, and `none`; a consumer supplies non-empty named
  `durability_providers`. Typed declarations override prose/lock inference. A
  contradictory declaration, non-provider target, or missing raw dependency is
  rejected before lint/rounds. Nodes without the fields retain the V1 conservative
  heuristic.
- Build the combined raw-dependency plus semantic-precedence graph, detect a
  deterministic cycle before ranking, topologically rank an acyclic graph, and
  post-validate every emitted round's precedence. The old arbitrary convergence cap
  is removed. `--no-semantic-ordering` refuses an unsafe request rather than emitting
  a misleading schedule.
- Preflight every original node declaration before typed validation or scheduling.
  Node IDs are unique and every `dependencies` value is a list of non-empty string IDs
  with no duplicate, self, or unknown target. Lint reports deterministic
  `graph-validity` errors; direct/CLI rounds fail closed even when lint was not called.
  A duplicate declaration is never silently discarded by a normalized graph map.
- Treat a durability- or external-effect-significant `semantic_locks` entry as an
  asserted semantic contradiction for typed `durability_role: "none"`. This narrow
  rejection does not override a typed provider/consumer declaration or alter legacy
  prose inference.
- Read a plan's bytes once per lint/round invocation; parse, recompute every present
  seal over complete canonical material, and use that in-memory document for the
  result. Output distinguishes `verified-sealed`, `partially-sealed`, and
  `digest-unsealed`; it reports integrity separately from typed/legacy durability mode
  and includes the consumed raw-byte/canonical-plan digests without claiming a
  filesystem-wide atomic snapshot or authentication.
- Add the bounded `--expected-plan-digest` argument to both generic subcommands. It
  compares a caller-provided manifest/contract digest to the same consumed canonical
  plan before findings or rounds. A self-consistent substitute with recomputed internal
  seals may pass integrity alone but fails this external expected-input binding.
- Retain executable explicit-node commands only for conventional installed plans.
  External plans return structured `manual-parent-v1` rounds with `command: null` and
  an explicit unavailable-command explanation. No native external dispatch is added.
  The direct compiler derives command availability and mode atomically from the same
  plan boundary and rejects caller-supplied external commands or conflicting modes.
- Pin the untouched V1 standard and every V1 overlay source byte in regression tests.

## Consequences and limits

Typed metadata removes accidental classification; it does not prove an author's
architecture assertion. Internal seals and a matching expected digest establish digest
equality, not authenticated provenance for the caller or manifest. The compiler does
not authenticate a plan's claimed standard-path/Git-blob provenance, authorize a
parent, or implement `PUBLIC-RUNTIME-500`. Those facts remain author-verified or
separately governed.

A newly typed plan that violates the V2 dependency requirement blocks rather than
downgrading to heuristic scheduling. This is deliberate fail-closed behavior. Unsealed
plans remain compatible but are never reported as verified, whether their durability mode
is typed V2 or legacy heuristic.

## Acceptance and rollback

Focused coverage includes the exact descendant-provider cycle, typed semantic
precedence, `none`/semantic-lock contradictions, raw dependency shape/duplicate/unknown
preflight, digest mutation/substitution, a self-consistent substitute rejected by a
supplied expected digest, same-invocation snapshot behavior, false-command removal,
parser compatibility, and V1 byte preservation. Required final validation is the full
repository unittest suite in a child environment with only `GIT_PAGER` removed.

Rollback reverts this bounded amendment together: compiler, tests, V2 standard, this
ADR, court receipt, and ADR index. It preserves the original standard, the sealed plan,
both existing generic-product overlays, and all adverse evidence.
