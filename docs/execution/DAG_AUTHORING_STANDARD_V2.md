# DAG authoring standard V2 — typed durability and bound consumption

## Status and compatibility

This is a versioned successor to `DAG_AUTHORING_STANDARD.md`; it does not edit,
reinterpret, or reseal that historical V1 document. A plan/release that adopts V2
MUST retain a source binding to this path and its exact Git blob in its own
provenance. The generic compiler implementation is `.autopilot/bin/dag_standard.py`
with `DAG_STANDARD_VERSION = 2`.

V1 and other legacy plans remain consumable when they omit the V2 fields below.
Their **durability mode** is reported as `legacy-heuristic`; their independent
**integrity status** derives only from the plan/node seal fields. Thus the sealed
generic V1 materialized plan is truthfully both `verified-sealed` and
`legacy-heuristic`. A digestless legacy plan is `digest-unsealed` and MUST NOT be
described as verified. A typed V2 plan can likewise be `digest-unsealed`; seal status
never selects durability mode.

V2 does not add native external-plan dispatch. It makes the present limitation
truthful while `PUBLIC-RUNTIME-500` remains out of scope.

## 1. Typed durability node semantics

V2 introduces the following optional node-contract fields:

```json
{
  "durability_role": "provider | consumer | none",
  "durability_providers": ["DURABLE-100"]
}
```

The values are exclusive and precisely typed.

| Role | Required fields | Meaning |
| --- | --- | --- |
| `provider` | `durability_providers` MUST be absent | This node establishes the durable state named consumers rely upon. |
| `consumer` | `durability_providers` MUST be a non-empty, unique list of non-empty node IDs | This node relies on each named provider. Each provider MUST explicitly declare `provider` and be a transitive raw dependency of the consumer. |
| `none` | `durability_providers` MUST be absent | This node neither provides nor consumes durability semantics. It MUST NOT assert crash/restart/resume/replay or external-effect semantics. |

Unknown values, lists in place of a role, an orphan provider list, duplicates, self
references, unknown IDs, non-provider IDs, a missing transitive raw dependency, or
`none` paired with an asserted durability/external-effect claim fail closed before
lint or rounds. A `semantic_locks` entry matching the compiler's durability vocabulary
(for example `durability-qualification`, `checkpoint`, or `reconciler`) or its
delimiter-bounded external-effect vocabulary (for example `remote-write`, `deploy`,
or `publish`) is such a machine-significant assertion. These are contradictory machine
contracts, not prose warnings. This narrow lock check applies only to `none`; it does
not reclassify a typed provider or consumer from its declared role.

When the typed fields are present, they take precedence over `objective`,
`acceptance_criteria`, and `semantic_locks`. In particular, a typed consumer that
mentions checkpoints or resumes is never inferred to be a provider. Do not weaken
objective or acceptance prose to affect classification. Omit the fields only for
legacy behavior, where the compiler retains the V1 heuristic and warning severity.

## 2. Canonical seals and same-invocation consumption

`dag-lint` and `dag-rounds` read plan bytes once, UTF-8-decode and parse that one
snapshot, validate it, then construct the graph used for the same invocation. They
do not reopen the plan path after validation.

Canonical JSON is UTF-8 `json.dumps` with `ensure_ascii=False`, sorted object keys,
compact separators `(',', ':')`, and `allow_nan=False`.

1. A node `contract_digest` is `sha256:` plus the SHA-256 of the complete node
   object with only `contract_digest` removed.
2. A top-level `plan_digest` is the digest of the complete parsed plan object,
   including its ordered node list and any node digests, with only top-level
   `plan_digest` removed.
3. A present digest MUST be exactly lowercase `sha256:` plus 64 hexadecimal
   characters and MUST equal its recomputation. A mismatch rejects the command
   before lint findings or rounds are emitted.

Both fields remain optional for old documents. The machine-reported integrity
statuses are:

| Status | Truthful meaning |
| --- | --- |
| `verified-sealed` | A valid top-level plan digest and a valid contract digest for every node were consumed. |
| `partially-sealed` | At least one valid optional seal was consumed, but the full plan/node seal set is incomplete. |
| `digest-unsealed` | No plan or node digest was supplied. The plan was parsed, not verified. |

JSON output always carries `consumed_source_bytes_digest` (the raw byte snapshot) and
the recomputed canonical `consumed_plan_digest`, whether or not the document carried
its own `plan_digest`. This binds the bytes actually consumed in that invocation. It
does **not** claim filesystem atomicity, caller authentication, or prevention of a
later rewrite of the pathname; a later invocation consumes and validates its own
snapshot.

### Expected-digest caller binding

`dag-lint` and `dag-rounds` accept an optional
`--expected-plan-digest sha256:<64-lowercase-hex>` argument. When supplied, the
compiler compares it to the canonical digest of its consumed byte snapshot and rejects
the invocation before findings or rounds on mismatch. This is the required handoff
from a manifest-pinning integrator: it rejects a self-consistent replacement whose
internal plan/node seals have merely been recomputed.

The flag may bind an unsealed legacy plan too, because the consumed canonical digest is
always recomputed. The caller remains responsible for obtaining the expected value from
a trusted manifest or equivalent contract. A matching digest demonstrates equality to
that supplied value; it does not authenticate who supplied it.

The JSON `expected_plan_binding` object reports whether a value was supplied, the
expected/consumed digests, and `matched` for an exact comparison. `matched` is not an
authentication claim about the expected value's source. `integrity` and
`durability_semantics` remain separate objects.

## 2.1 Durability-mode output

The machine-reported `durability_semantics.mode` is independent from integrity:

| Mode | Meaning |
| --- | --- |
| `typed-v2` | Every node uses the V2 typed declaration. |
| `mixed-v2-and-legacy-heuristic` | Some nodes use V2 metadata and remaining nodes use the V1 heuristic. |
| `legacy-heuristic` | No node has typed durability metadata. |

## 3. Combined ordering graph

Before typed durability validation, level calculation, or round emission, the compiler
preflights every original node declaration. Node IDs must be unique and every
`dependencies` field must be a JSON list of non-empty string IDs with no duplicate,
self, or unknown target. `dag-lint` reports these as `graph-validity` errors and skips
later graph-dependent checks; `dag-rounds` independently rejects them. A normalized
node map is never allowed to discard a declaration or raw prerequisite and then emit a
schedule.

For a valid raw topology the compiler constructs one directed prerequisite graph:

- raw edge `dependency -> dependent` for every plan dependency; and
- semantic edge `durability provider -> consumer` for every typed relationship,
  plus V1 warning-derived legacy relationship.

It deterministically detects a cycle in this combined graph and raises a typed error
containing the cycle. It does not use a bounded rank-relaxation loop. For an acyclic
graph it topologically ranks nodes, packs conflict-free rounds, then checks that
every raw and semantic prerequisite occurs in a strictly earlier emitted round.
No dependency-invalid or semantic-ordering-invalid rounds are returned.

`--no-semantic-ordering` remains only for a plan that has no semantic constraints.
It refuses rather than emits an unordered schedule when constraints exist. It is not
an execution bypass.

## 4. Execution-mode output

The installed `dispatch` parser consumes only the repository's conventional
`.autopilot/plan.json`; it does not accept `dispatch --plan`. Therefore:

- a conventional installed plan returns `execution.mode: "installed-dispatch-v1"`
  and each round contains an executable explicit-node command; and
- any external/non-conventional `--plan` returns
  `execution.mode: "manual-parent-v1"`, `command: null`,
  `executable_dispatch_command_available: false`, and an explicit explanation
  that no executable dispatcher command is available.

The direct compiler API derives command availability and execution mode from the same
plan/repository boundary. It rejects a caller-supplied command for an external plan and
rejects a caller-supplied execution mode that disagrees with that boundary; an API caller
cannot manufacture a runnable command in `manual-parent-v1` mode.

The structured external rounds remain useful to a parent that opens workers and
integrates in the declared order. That parent workflow is author-verified; this
compiler neither dispatches it nor claims that a shell command exists.

## 5. V2 enforcement matrix

| Requirement | Enforcement | Evidence / limit |
| --- | --- | --- |
| Existing graph, scope, contention, contract-presence, and legacy warnings | Machine-checked as specified by V1 | V1 remains normative for unchanged checks. |
| Typed role/list shape and contradictions | Machine-checked, fail closed | Validated before lint/rounds. |
| Raw node IDs and dependency shape/targets | Machine-checked, fail closed | Every original declaration is checked before typed validation or schedule emission; lint reports `graph-validity`, rounds reject independently. |
| Named typed provider exists, is typed `provider`, and is a raw ancestor | Machine-checked, fail closed | Prevents a typed semantic edge from hiding a dependency cycle. |
| Correct domain assignment of `provider`/`consumer`/`none` | **AUTHOR-VERIFIED** | The type removes prose ambiguity; it cannot prove an author's architecture claim. |
| Legacy prose/lock fallback | Machine-checked warning only | Preserved only when typed metadata is absent. |
| Combined dependency/semantic cycle | Machine-checked, fail closed | Error names the detected path; no rounds are emitted. |
| Round prerequisite order | Machine-checked, fail closed | Postcondition checks every raw and semantic edge. |
| Present plan/node digest | Machine-checked, fail closed | Complete canonical material as §2; no later path reread. |
| Caller-supplied expected plan digest | Machine-checked, fail closed | Compares the caller value to the canonical digest of the consumed byte snapshot before output. |
| Digest-unsealed/partial integrity state | Machine-reported | These states are explicitly not a verification claim. |
| Typed/legacy durability mode | Machine-reported | Classification mode is separate from integrity/seal status. |
| Standard path/blob provenance | **AUTHOR-VERIFIED** by this compiler | A generated-plan verifier may bind it; this generic compiler does not authenticate a document path or Git object. |
| Conventional command parser compatibility | Machine-checked by regression test | Only the current installed-plan command is emitted. |
| Direct command/mode consistency | Machine-checked, fail closed | An external plan cannot receive a supplied executable command or a conflicting execution mode. |
| External parent execution/integration | **AUTHOR-VERIFIED** | `manual-parent-v1` is a truthful bootstrap mode, not product-native dispatch. |

## 6. V2 acceptance and rollback

The focused test suite covers typed false-provider descendants, malformed and
contradictory declarations (including `none` plus machine-significant semantic locks),
raw dependency shape/duplicate/unknown-target preflight, the exact legacy
task-to-descendant-provider cycle, termination, digest mutation/substitution, a
self-consistent substitute rejected by a caller-provided expected digest, one-snapshot
use, external manual-parent output, installed command parsing, and byte-for-byte V1
preservation. Full repository CI remains `python -m unittest discover -s tests -v`.

Rollback is a single revert of the V2 compiler amendment, V2 standard, ADR, court
receipt, and tests. It does not edit the V1 standard, `.autopilot/plan.json`, or either
generic-product overlay. Any plan that already relies on the V2 fields must stop for a
versioned replan rather than silently downgrade its semantics.
