# ADR-016: Governed Extension Packages and Portable Host Projections

- Status: bounded structural candidate accepted/adapted; promotion deferred
- Date: 2026-07-28
- Decision owners: Architect and Integrator
- Independent review: hostile Curator pass and Judge disposition recorded; separate Steward still required
- Constitutional impact: yes
- Supersedes: none

## Context

Hive Mind OS currently preserves eight constitutional specialist roles, formal
contracts, a durable mission store, an append-only evidence ledger, policy
decisions, sandbox boundaries, and a fixed lifecycle. Those behaviors must not
be lost while agent, skill, workflow, tool, and host definitions become easier
to extend.

The existing implementation keeps role contracts in one Python mapping and
routes much of mission execution through fixed code. That is inspectable, but
it provides no governed extension package contract, dependency resolver,
quarantine state, or host-conformance boundary. Model-provider adapters are not
equivalent to running the same governed mission through Codex, Claude Code,
Hermes, or another agent host.

Source-reference conservation also drifted: the vision contract used mutable or
case-normalized URI variants and omitted the admitted sibling source pack. A
subset assertion did not detect the mismatch. Exact source parity is required
before extension work can claim complete provenance.

## Court record and Judge disposition

The architecture discovery used inventory, advocate, cross-examiner, and
portability-expert passes. Implementation slice 1 uses separate Builder,
Integrator, and security Curator identities. Because the agent-thread limit was
reached, the maintenance review reused `/root/portability_expert`, an identity
that had already served Architect and Advocate duties. That review produced
useful findings, but it is not evidence from a separate Steward identity and
does not satisfy the required architecture-versus-maintenance independence.
An independent implementation Judge accepted/adapted this bounded structural
candidate. The ruling permits the inert package catalog, compatibility facade,
OODA replay contracts, and read-only War Room projection to remain as a
structural foundation. It explicitly defers promotion, executable extension
loading, host-support claims, source-completeness claims, and superiority
claims. The dispositions below form part of that bounded ruling:

| Claim | Judge disposition | Conditions |
|---|---|---|
| Use manifest-backed packages for agents, skills, tools, workflows, and host adapters | `adapt` | Manifests are data-only, versioned, content-addressed, validated fail-closed, and cannot grant authority |
| Preserve the eight specialist roles as constitutional accountability identities | `adopt` | A package may implement or specialize a role; adding a constitutional role requires a new ADR and tests |
| Model OODA as a durable workflow pattern | `adapt` | Slice 1 binds actors, evidence, decisions, policy, intents, receipts, outcomes, sequence, and stop state; per-transition budget, lease, and rollback references are deferred |
| Provide a War Room projection | `adapt` | It is read-only and ledger-derived; missing evidence is reported as unknown or not recorded |
| Compile canonical packages to Codex, Claude, Hermes, or other host formats | `adapt` | Generated host files are projections, never the authority or canonical source |
| Install or import arbitrary third-party Python inside the kernel | `quarantine` | Execution remains outside the trusted process until isolation and policy mediation are proven |
| Permit an agent to promote its own challenger | `reject` | Independent evaluation and judgment remain mandatory |
| Treat one source file per agent as proof of extensibility | `reject` | Extensibility depends on contracts, discovery, validation, compatibility, authority, and rollback |
| Claim all source scenarios are implemented | `defer` | Incomplete video ingestion, licensing, pins, and held-out verification remain blocking obligations |
| Adopt exact third-party “Armory” semantics | `defer` | The intended source must first be confirmed and admitted with a pinned version, digest, license, and atomic claims |

No superiority disposition is issued. This slice introduces compatibility
structure and characterization tests, not comparator evidence. Promotion
remains blocked until a genuinely separate Steward reproduces the maintenance
evidence, a built wheel proves installed resource inclusion, and the retained
source, host, execution, and activation obligations are resolved at their
applicable burdens.

## Bounded structural decision

### Canonical package boundary

Hive Mind OS will use a package manifest as the canonical description of an
extension. Package schema v1 supports `agent`, `skill`, `tool`, and `workflow`
components. The manifest identifies the package, exact semantic version,
declared capabilities, exact dependencies, source provenance, court references,
and file integrity data. A `host-adapter` component kind and executable
entrypoints are deferred; schema v1 does not claim them.

The manifest is not an authorization document. Declared capabilities are
requests that still require policy decisions and resource leases. Loading,
validation, installation, activation, promotion, and rollback are distinct
states. Invalid, conflicting, unknown, or untrusted packages fail closed.

An agent package supplies an accountable implementation or specialization of a
constitutional role. Skill schema v1 supplies an inert procedure description,
instruction reference, capability requests, reference files, and test
references. Typed skill inputs and outputs, explicit resource envelopes,
runtime retries, compensation, and skill evaluation contracts remain deferred.
A tool package describes a side-effect boundary but does not activate one. A
workflow package describes durable state transitions. A future host adapter may
translate session and workspace mechanics without changing kernel authority,
but no host-adapter package or runtime claim is implemented in this slice.

### Constitutional role compatibility

The existing `ROLE_CONTRACTS` mapping and `DEFAULT_LIFECYCLE` tuple remain public
compatibility surfaces. They may become manifest-backed facades only when an
exact equivalence test proves all role identities, missions, outputs,
capabilities, quality gates, and lifecycle ordering are unchanged.

The constitutional role enumeration is not dynamically extended by ordinary
package discovery. A new agent normally binds to one of the eight roles. A new
constitutional role changes completion semantics and therefore requires a
separate architecture decision, contract version, migration, and independent
court.

### OODA workflow

OODA is a workflow pattern rather than a role or ambient loop:

1. **Observe** records repository, source, event, outcome, and receipt evidence.
2. **Orient** records relevant context, constraints, threats, alternatives, and
   dissent.
3. **Decide** records the selected option, acceptance criteria, budget, stop
   condition, proposed tool intents, and rollback.
4. **Act** submits typed intents through policy, lease, sandbox, and receipt
   boundaries.
5. Independent validation feeds the next Observe transition.

An OODA phase is not reported unless an explicit durable event records it.
Iteration cannot expand authority, weaken acceptance criteria, or mutate the
live champion.

The slice-1 replay model enforces phase order and reference requirements around
decide, act, receipt, outcome, and terminal state. It does not yet encode a
budget reference, capability-lease reference, rollback reference, or stop
condition on every transition. Those bindings are next-slice obligations and
must not be inferred from surrounding mission state.

### War Room

Projection schema v1 remains the default compatibility contract. Projection
schema v2 is opt-in and adds read-only War Room rooms derived from scheduler,
mission-store, and evidence-ledger state. It exposes recorded OODA phase,
observed actors, budgets, checkpoints, evidence references, OODA-cycle
references, command-intent references, hypotheses, decision events, receipt
events, quarantine events, and recent validated War Room records. Only explicit
`war_room.event` envelopes that conform to the formal schema and bind to the
ledger mission and actor are admitted. Court, lease, risk, and source-obligation
fields require a future additive schema version and are not inferred from
untyped event payloads.

The projection cannot execute commands and reports `authority: none`. It
does not expose arbitrary event payloads. Future interactive controls must
create typed objectives or tool intents and pass through normal policy; a UI
must never bypass the kernel.

### Portable hosts

Portability is split into independently versioned contracts:

1. Model providers generate model turns.
2. Host adapters manage sessions, cancellation, resume, event streams,
   subagents, and workspaces.
3. Tool adapters mediate external effects.
4. Host projections render canonical package definitions into host-native
   instructions and configuration.

Codex, Claude Code, Hermes, and other host files are generated artifacts.
Capability negotiation fails closed when a host cannot satisfy the package
requirements. Host conformance must cover discovery, cancellation, resume,
tool restrictions, workspace isolation, event correlation, and receipts
before that host may be advertised as supported.

## Security and failure model

Package metadata is untrusted input. Slice 1 validates schema versions,
identities, exact dependency pins, cycles, content digests, strict JSON,
portable paths, regular files, symlinks, Windows reparse points, file inventory,
and inert loading. It records enumerated license and trust states, prohibits a
pending or incompatible license from being marked trusted, and requires
unresolved replacement or rollback pins to remain quarantined.

Independent verification of the declared license, archive ingestion,
signatures and signer revocation, secret and environment access, network
enforcement, replay protection across catalogs, self-approval, and concurrent
promotion remain deferred security obligations.

Slice 1 does not execute dynamically discovered third-party code. Later
execution must be out of process or within an independently verified isolation
tier and must still use typed intents, policy decisions, leases, resource
budgets, receipts, and compensation.

## Migration

1. Capture golden behavior for public imports, schemas, role contracts,
   lifecycle ordering, mission reports, projections, stored mission state,
   ledger events, prompt digests, denials, resume, and failure artifacts.
2. Add package schemas, manifest types, registries, and built-in packages
   without changing runtime selection.
3. Prove built-in role manifests exactly equal the legacy contracts.
4. Switch public role mappings to a manifest-backed facade only after that
   equivalence test passes.
5. Add workflow patterns in shadow mode while the existing sequential
   lifecycle remains authoritative.
6. Enable projection schema v2 only through explicit selection; schema v1
   remains the default.
7. Add host adapters one at a time behind a shared conformance suite. Do not
   advertise a host before conformance evidence exists.
8. Add package challenger evaluation and independent promotion after isolation,
   policy vocabulary, signatures, and rollback receipts are implemented.

Schema changes are additive. Existing schema names, identifiers, role values,
imports, CLI behavior, and stored mission formats remain valid. New schema
versions require new names or identifiers rather than mutation of an old
contract.

## Rollback

The legacy literals and lifecycle are the initial champion. Until runtime
promotion exists, rollback is a code/configuration reversion to those
compatibility surfaces.

After governed promotion exists, activation is intended to use an atomic
champion pointer; no such activation API exists in slice 1.
Rollback switches the pointer to the previous pinned digest; it does not delete
the challenger, evidence, dissent, evaluation results, receipts, or source
obligations. Projection schema v2 can be disabled independently because schema
v1 remains the default. Host projection failures do not change the canonical
package or kernel state.

Rollback must fail closed if the previous package digest, compatibility
contract, or required evidence is unavailable.

## Acceptance evidence for slice 1

- Vision source URIs exactly equal the authoritative docket URIs, including
  count and order.
- Existing schemas retain their names and identifiers.
- New package schemas validate through the same contract catalog.
- Built-in package discovery is deterministic and rejects invalid or duplicate
  packages.
- Legacy role contracts and lifecycle remain exactly equivalent if the facade
  is enabled.
- Projection schema v1 retains its exact top-level shape and default behavior.
- Projection schema v2 is explicit, read-only, evidence-derived, and fail-closed
  on unsupported versions.
- Existing focused and full regression suites pass.

The retained validation receipts report:

- The post-repair hostile Curator suite passed 71 tests with 1
  platform-dependent skip. It reproduced OODA initial and progressed stops,
  schema/runtime parity, malformed and forged War Room payloads, package
  provenance and trust boundaries, exact version pins, null actors, reparse
  checks, and the absence of install or activation APIs.
- The root full regression suite passed 389 tests with 3 skips and 1,744
  subtests in 938.26 seconds.
- Ruff completed with no findings. Pyright completed with 0 errors, 0 warnings,
  and 0 informational findings.
- The Optimizer measured `hive_core_catalog()` at 5.84 milliseconds and
  recorded a +7.93% import-time delta. This is retained performance dissent:
  built-in catalog loading is reused through one private module-level value,
  but import overhead must remain monitored as the package inventory grows.

These receipts satisfy the bounded structural acceptance burden only. Wheel
verification remains blocking: source-tree resource tests and package-data
rules do not prove that a built and installed wheel contains every schema,
manifest, agent, workflow, and prompt resource. The current environment lacked
the required build backend for that independent artifact check.

A genuinely separate Steward review also remains blocking. The earlier
maintenance review reused `/root/portability_expert`, which had already served
Architect and Advocate duties, so its valuable findings do not satisfy identity
separation.

Source ingestion and licensing obligations remain open, including incomplete
video evidence and the deferred exact Armory source. No Codex, Claude Code,
Hermes, or other host adapter has passed a conformance suite. No package
installation, activation, executable plugin loading, autonomous promotion,
signer verification, or champion-pointer mechanism exists in this slice.

## Consequences

The architecture gains an explicit extension seam without granting extension
packages ambient authority. It also gains a truthful path to multi-host
operation, rather than treating inference API support as host compatibility.

The immediate cost is additional manifests, validation, conformance, migration,
and independent evaluation work. Typed skill execution, signer/quarantine
governance, autonomous installation and promotion, host-adapter packages, and
multi-host support remain intentionally incomplete until their higher-burden
evidence is available.
