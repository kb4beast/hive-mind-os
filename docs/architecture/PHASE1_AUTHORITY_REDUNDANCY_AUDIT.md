# Phase 1 Authority and Redundancy Audit

- Status: generation-zero characterization complete; Phase 1 authority design
  adopted and no runtime authority migration performed
- Captured from: `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Repair base: `0948f7ec385238f5825ce7c39dd25de2e9a1035d`
- Mission brief:
  `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`
- Mission brief SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`

## Finding

Generation zero has one runtime role-contract facade, but it does not have one
canonical agent-system record. Role names, fields, prompts, skills, workflow
bindings, schemas, and host observations are repeated across Python and strict
JSON resources. Some copies are tested projections; others are independent
literal lists or instructions and can drift.

This audit does not promote `hive-core`. It remains inert and quarantined.

## Live and duplicated fields

| Surface | Current authority or use | Duplicated/projection fields | Reachability and risk |
| --- | --- | --- | --- |
| `models.Role` | Runtime role-name enum | Eight role identifiers | Imported throughout the runtime; JSON schemas repeat the vocabulary without generation. |
| `roles.ROLE_CONTRACTS` | Runtime mission, outputs, capabilities, and quality gates | All five `RoleContract` fields | Used by `runtime.py`, `mission.py`, prompt rendering, and tests. This is the effective generation-zero runtime authority. |
| `roles.DEFAULT_LIFECYCLE` | Runtime role order | Eight ordered role identifiers | Used by runtime and mission execution. The built-in workflow repeats the order and evidence transitions. |
| `vision.REQUIRED_ROLES` | Compliance list | Same eight role identifiers | A separately maintained tuple; equality is expected but not generated from the lifecycle. |
| `mission._instruction_for` | Per-turn work instruction | Four special role instructions plus fallback mission text | A second behavioral prompt layer outside `RoleContract` and the prompt registry. |
| `prompts/*.txt` | Generation-zero prompt artifacts | Rendered mission, outputs, and gates | Tests require equality with `generation_zero_prompt`; these are committed compatibility copies. |
| `hive-core/agents/*.json` | Inert package agent manifests | Role, mission, outputs, capabilities, gates, prompt path, skill IDs, tool IDs | Parity tests currently make these lossless projections of `ROLE_CONTRACTS`, but generation is manual. |
| `hive-core/prompts/*.json` | Inert package prompt resources | Role-specific instructions and deferred boundaries | Not used by the runtime prompt registry. These can imply behavior that the active runtime does not execute. |
| `hive-core/skills/*.json` and `skills/instructions/*.json` | Inert skill descriptions | Capabilities, procedures, fail-closed rules, source refs, obligations | Capabilities intentionally overlap agent requests; procedures are not runtime behavior. |
| Built-in workflows | Inert lifecycle/OODA/challenger descriptions | Role bindings, evidence names, states | `workflow.default-lifecycle` is parity-checked; OODA and challenger records remain declarative. |
| Role-bearing schemas | Contract validation | Role enums and role-bearing field names | `identity`, `mission-state`, `handoff`, agent, and workflow schemas embed role vocabulary independently. |
| Host capability profiles | Unverified declarations | Host ID/version, capability observations, obligations | Not executable adapters and cannot satisfy `supports()` while conformance is unverified. |

## Adopted field-level dispositions

These are the Phase 1 design authorities governed by ADR-018 and
`PHASE1_CANONICAL_CONTRACTS.md`. Their additive runtime implementation remains
Phase 2 work.

| Field family | Candidate authority | Projection consumers | Compatibility requirement |
| --- | --- | --- | --- |
| Role identifiers | Versioned canonical role definition | Python enum, schemas, workflows, host projections | Preserve all eight generation-zero values and order. |
| Mission, outputs, gates | Versioned canonical role contract | Runtime facade, package agent manifests, prompt composer | Preserve exact v1 strings and tuple order until a separately evaluated v2 activates. |
| Capabilities and permissions | Canonical requested-capability contract plus policy/lease mapping | Agent and skill manifests, tool bindings, host degradation views | A projection may request but never grant authority. |
| Prompt layers | Canonical prompt composition manifest | Prompt registry artifact, runtime system prompt, host prompt projection | Exact layer order, content digests, redactions, and generation-zero digest must be receipted. |
| Skills | Independently versioned typed skill contracts | Agent bindings and host skill projections | Skill reuse cannot merge role identity, judgment, or approval authority. |
| Workflow role bindings | Versioned workflow contract referencing canonical role IDs | Runtime adapters and inert package resources | Preserve the current lifecycle and keep OODA/War Room authority separate. |
| Host artifacts | Generated nonauthoritative projections | Codex, Claude Code, Hermes, future hosts | Drift is a failed build; host availability never proves behavioral conformance. |

## Contradictions and gaps

1. The Python runtime contract is authoritative in practice while the package is
   described as a constitutional facade. There is no machine-readable
   authority marker that makes the relationship explicit.
2. Declared capabilities do not determine generation-zero authority.
   `RoleContract.default_capabilities` and package capability strings are
   compatibility data. Runtime authorization is separately hard-coded through
   `policy.Action`, mission capability classes, and dispatch. Every role is
   granted repository read during mission execution even when its declared
   list omits it; several declared names have no corresponding policy action;
   and Builder commit is authorized through the create-branch action.
3. Parity tests cover built-in agent manifests and default lifecycle order, but
   do not prove that package prompt procedures equal active runtime behavior.
4. `mission._instruction_for` is a live prompt layer outside the prompt
   registry and package inventory.
5. Prompt champion reachability is path-dependent. Normal CLI run/delivery
   construction does not inject `PromptRegistry`, while experiment bootstrap
   expects repository-root `prompts/` files that are not installed package
   resources. A recorded experiment champion therefore need not affect normal
   execution.
6. Context selection and context-manifest creation have separate mission and
   model-backend implementations. Current first-N character truncation favors
   old context and records no omitted IDs or preservation reasons for blockers,
   dissent, authority, provenance, or rollback.
7. `Role` enumeration order is not lifecycle order: Optimizer precedes Steward
   and Integrator in the enum. Consumers must never infer lifecycle order from
   enum iteration.
8. Role enums inside JSON schemas are not generated from `models.Role`.
9. Skill procedures, workflow descriptions, and host profiles are inert; their
   presence must not be counted as executed behavior.
10. There is no canonical v2 projection command, drift receipt, or compatibility
   report.

## Phase 2 acceptance boundary

An additive canonical definition is admissible only if:

- it preserves the generation-zero fixture;
- requested capabilities are mapped to a versioned policy action/role
  ceiling/tool/lease intersection and unknown mappings fail closed;
- every generated artifact has a deterministic digest and source-definition
  reference;
- the runtime can continue using the v1 facade during migration;
- generated files cannot authorize actions;
- prompt and context composition record ordered layer IDs, versions, digests,
  trust/sensitivity, selected and omitted record IDs, and critical-context
  coverage;
- schema, prompt, package, workflow, and host drift fail closed;
- rollback restores the prior canonical pointer without deleting challengers,
  dissent, receipts, or fixtures; and
- a separate Curator and Judge reproduce parity before any champion switches.

## Phase 1 authority result

The effective authority formula is the intersection of constitutional role
ceiling, versioned policy action, explicit lease or required external grant,
adapter enforcement, mission risk, and resource budget. A capability,
manifest, skill, prompt, workflow, host projection, memory record, Obsidian
note, telemetry event, score, or successful outcome is never a grant.

The contradictions above remain Generation Zero defects and Phase 2
acceptance obligations. Phase 1 resolves their design disposition without
claiming that production already enforces the v2 mapping.
