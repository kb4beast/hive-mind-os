# ADR-017: Inert Constitutional Skills, Read-Only Tools, and Host Evidence

- Status: bounded candidate adapted after cross-examination; promotion blocked
- Date: 2026-07-28
- Decision owners: Architect and Builder
- Independent review: Explorer, separate Architecture Cross-Examiner, and independent security Curator; Judge receipt pending
- Constitutional impact: yes
- Extends: ADR-016

## Context

ADR-016 introduced strict, content-addressed JSON packages while retaining the
eight-role Python facade and existing lifecycle. Its first built-in package
contained agent descriptions but no reusable skill procedures, typed read-only
tool descriptions, dependency-closure binding checks, or conservative host
evidence resources.

This slice must improve extension structure without enabling extension
execution, changing role authority, claiming host support, or duplicating the
War Room projection as an operational state machine.

## Court record and dissent

The Explorer requested component-level provenance, explicit retained
obligations, primary host documentation, and continued source-docket blockers.
The separate Architecture Cross-Examiner issued `adapt — BLOCK`, accepting the
inert structural boundary while rejecting operational-extensibility,
independent-promotion, runtime-rollback, and host-support claims. The later
independent security Curator rejected a proposed
`workflow.war-room` because the existing
schema-v2 War Room is a read-only ledger projection; another workflow would
create duplicate semantics and could imply operational authority. The
Curator also required a challenger workflow to end at recorded
evaluation, not acceptance, activation, or promotion.

The following objections remain unresolved and are preserved:

- Seven admitted video sources still lack complete pinned ingestion.
- The intended Armory source and exact semantics remain unconfirmed and
  unadmitted.
- No Codex, Claude Code, or Hermes executable host adapter exists.
- No host has passed the Hive Mind OS conformance suite or produced
  cancellation, package-discovery, lifecycle, isolation, event, and receipt
  evidence.
- Extension signatures, signer revocation, out-of-process isolation,
  installation, activation, promotion, and atomic rollback remain deferred.
- Package trust, licensing, court status, and host conformance still require an
  external append-only adjudication overlay; manifest strings are not proof.
- The inert catalog has no versioned activation pointer, so `rollback_to`
  metadata is not yet an executable or atomic rollback mechanism.
- Package capability names are not yet mediated through the policy action and
  lease vocabulary, and skill/prompt execution contracts remain deferred.

Accordingly, this ADR makes no source-completeness, host-support, production,
activation, or superiority claim.

## Decision

### Constitutional skills

`hive-core` includes one inert skill manifest and one strict JSON instruction
resource for each constitutional role. Each agent binds only its matching
skill. Every instruction resource records:

- an exact matching skill identifier;
- bounded procedure steps;
- fail-closed conditions;
- component-level source references; and
- nonempty deferred obligations.

Skill capability requests must be a subset of the bound agent's requested
capabilities. Skills remain data and cannot execute code, grant authority,
install dependencies, or promote themselves.

### Read-only tool descriptions

The package includes three inert tool descriptions:

- `tool.repository-inspect` requests `read_repository`;
- `tool.evidence-query` requests `query_ledger`; and
- `tool.contract-validate` requests `run_contract_tests`.

Each is explicitly non-side-effecting and references standalone schemas from a
bounded, recursively validated Draft 2020-12 subset. The package loader rejects
non-strict roots, malformed or unsupported keywords, invalid identifiers,
undeclared required properties, and static, dynamic, or recursive schema
references.
These descriptions do not supply implementations or runtime authority.

An agent may bind a tool only when it already requests that exact capability.

### Reference closure

The inert catalog resolves agent skill and tool identifiers only within the
owning package and its exact digest-pinned transitive dependency closure. It
rejects missing references, wrong component kinds, duplicate identities,
undeclared-package reach, and capability escalation.

### Declarative workflows

`workflow.ooda` records the Observe–Orient–Decide–Act evidence sequence. It does
not replace the stricter replay state contract and cannot execute actions.

`workflow.challenger-experiment` records proposal, isolation, implementation,
independent evaluation, and quarantine. Optimizers may propose a challenger,
but transitions into and out of independent evaluation are Curator-only. Its
successful terminal state is `evaluated`, and the terminal record requires a
court disposition. Evaluation is not activation or promotion.

There is no `workflow.war-room`. War Room remains the read-only, ledger-derived
schema-v2 projection governed by ADR-016.

### Host evidence profiles

Codex, Claude Code, and Hermes resources are conservative evidence profiles,
not adapters or support declarations. Their capability sets are
declared/unadjudicated observations traced to inspected primary pages, use
`evidence_level: declared` and `conformance_status: unverified`, retain explicit
source-admission and conformance obligations, and cannot satisfy `supports()`.
The external documentation URLs are preserved in the package manifest but,
except for the already admitted Hermes repository source `SRC-004`, have not
been admitted to the authoritative source docket or pinned by content digest
and license.

`supports()` returns true only for a profile with `conformance_status: passed`;
passed status requires tested evidence and an external conformance verifier.
Fields in the profile cannot self-authorize support. Vocabulary for package
discovery, cancellation, and receipts is present for future conformance
receipts even though no built-in profile claims it.

## Security and authority

All package resources remain strict JSON and are content-addressed in the
package inventory. The loader performs no import, subprocess, network,
installation, activation, or promotion. Package capability fields remain
requests subject to the existing policy and lease system; catalog validation
cannot authorize an action.

`hive-core` deliberately remains `quarantined`; its manifest trust string is
not an external court verdict. Prompt promotion and rollback reject
quarantined artifacts inside the same pointer lock, and rollback additionally
requires the target to have been a prior same-role promoted champion.
All registry instances for one root share that lock, and pointer mutations also
hold an operating-system file lock. Serving an active quarantined champion
fails closed. A complete cross-process transaction spanning registration,
evidence, and pointer state remains deferred.

Host evidence URLs are provenance, not executable configuration. An
unverified or failed profile is not runtime support even if it declares the
requested capability names. The built-in profile loader rechecks the exact
resource digest at the final read boundary so post-validation mutation cannot
turn an unverified profile into a passing support claim.

The constitutional `ROLE_CONTRACTS` and `DEFAULT_LIFECYCLE` facade no longer
loads the complete candidate package during module import. Optional malformed
skill, tool, workflow, or host resources can therefore be quarantined without
preventing the legacy runtime from importing; parity with `hive-core` remains
an executable test.

War Room events require at least one evidence reference, and OODA-tagged events
must advance observe → orient → decide → act without phase jumps before they
can appear in the projection. The projection remains an unauthenticated
ledger-derived declaration view, not proof of actor identity or evidence
resolution and not an authority surface.

Prompt experiments that beat the champion now record evaluation evidence and
a `pending-independent-court` appeal. The runner cannot append its own
authoritative judgment and cannot move the champion pointer. An authenticated,
policy/lease-bound court service remains required for later promotion.

## Migration

1. Retain `ROLE_CONTRACTS`, `DEFAULT_LIFECYCLE`, and
   `workflow.default-lifecycle` without semantic changes.
2. Add skills and tool descriptions as inert, manifest-inventoried resources.
3. Validate references and capability subsets at catalog construction while
   leaving runtime selection unchanged.
4. Load host evidence profiles separately from adapters and keep every profile
   unverified until independent conformance receipts exist.
5. Build and inspect an installed wheel before relying on packaged resources.
6. Introduce executable adapters, if later adopted, under a separate ADR,
   isolation boundary, policy vocabulary, conformance suite, and promotion
   court.

The source docket remains unchanged and fail-closed. External video and
repository obligations are not discharged by these local components.

## Rollback

Source rollback removes the new component references and resources from
`hive-core` and restores the prior repository state. This is not a runtime
package rollback claim: the catalog has no active-version pointer and cannot
resolve coexisting versions of the same package ID. The unchanged legacy role
facade, default lifecycle, runtime authority, OODA execution boundary, and War
Room projection remain available throughout.

Rollback must preserve this ADR, failed evaluations, dissent, source blockers,
and host evidence records. It must not convert an unverified host profile into
a support claim or activate a challenger.

## Acceptance evidence

- All eight agents bind exactly one same-role skill.
- Component instruction resources preserve source references and deferred
  obligations and reject unknown or missing fields.
- Tool schemas are strict standalone Draft 2020-12 object contracts.
- Skill and tool bindings reject missing, wrong-kind, escalating, and
  undeclared-dependency references.
- The default lifecycle remains byte-for-byte unchanged.
- The challenger workflow ends at evaluation or quarantine and contains no
  activation or promotion event.
- Built-in host profiles are declared, unadjudicated, and unverified;
  `supports()` is false and evidence obligations remain explicit.
- Existing source-docket blockers remain release-blocking.
- A built wheel installed into an isolated target retained all 68 resources
  byte-for-byte: 20 formal schemas and 48 `hive-core` package files.
- Challenger `KEEP` results leave the champion unchanged and record a pending
  appeal; no built-in experiment path emits an authoritative decision or
  promotion event.
- The legacy role facade imports without invoking the optional package loader.
- Empty-evidence and out-of-order OODA War Room events fail closed.
- Exact final wheel receipt:
  `sha256:d19eb1607a25768c0be0b3d275189d6435a3e1b3fc1f5603d7fed07a02eeb943`
  at
  `C:\Users\beesp\AppData\Local\Temp\hmos-final4-7cc5e429b231495db3725ad1aa985f7d`;
  installed import, 22 components, quarantined trust, and 68/68 byte-equal
  resources were reproduced.

Promotion remains deferred until a separate Curator reproduces these checks
and an independent Judge issues a disposition.
