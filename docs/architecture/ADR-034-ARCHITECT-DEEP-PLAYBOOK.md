# ADR-034: Inert Architect deep-playbook candidate

- Status: adapted for a bounded stacked draft candidate; activation prohibited
- Date: 2026-07-31
- Extends: ADR-018, ADR-021-PR31, ADR-033
- Runtime selection: unchanged
- Authority: none

## Context

Phase 5 requires the remaining constitutional roles to gain separately versioned,
deep, testable playbooks without collapsing role authority. Phase 5A produced an inert
Orchestrator planning candidate. Phase 5B addresses only the Architect role.

Generation Zero and Phase 2 already define the Architect's constitutional purpose and
canonical prompt lineage. They do not provide one strict request-bound envelope that
separates claim integration, option analysis, architecture, interfaces, threats,
migration, rollback, verification, resources, and handoff.

## Decision

Add two package-private modules:

- `architect_playbook_contracts.py` owns thirteen strict contracts; and
- `architect_playbook.py` composes one deterministic inert successor and ten typed
  design outputs.

The candidate:

1. binds to the exact packaged Phase 2 Architect, Generation Zero prompt, built-in
   `skill.architect`, and constitutional lifecycle;
2. exposes no root API, CLI command, provider, tool, host, scheduler, capability,
   lease, store migration, or runtime selector;
3. retains requested capabilities only as unsupported metadata;
4. requires each adopted or adapted claim to carry admitted evidence, acceptance
   criteria, and an exact mapping into every design option;
5. prevents a claim, interface, boundary, threat, migration, rollback, or
   verification record from borrowing another option's design identifiers;
6. requires every option to independently cover every acceptance criterion,
   invariant, threat, migration step, and rollback step;
7. ranks viable options before blocked options, regardless of caller-supplied score;
8. reserves positive rollback and verification capacity before distributing each
   known resource ceiling across nine design sections;
9. preserves unknown resources as unknown instead of zero;
10. rejects private content, hostile containers, non-finite numbers, duplicate IDs,
    incomplete mappings, uncontained boundaries, incoherent migration/rollback,
    incomplete verification, and coherent semantic resealing; and
11. always leaves implementation, selection, risk acceptance, budget, and activation
    authority false.

The output is architecture metadata. It does not implement or select a design.

## Canonical identity

- Candidate agent: `hive-agent:architect:v2-shadow-1`
- Candidate definition: `hive-agent-definition:architect:v2-shadow-1`
- Base and rollback: `hive-agent-definition:architect:v2-candidate`
- Successor digest:
  `sha256:ecc0ba88c036f1f041f390cc8c68c20d52ec0336eb182c624028290d67f39bda`

## Threats and controls

| Threat | Control |
| --- | --- |
| A high score hides a blocked option | Viability is ordered before score and blocking reasons are explicit. |
| A claim borrows another option's design | Every mapping is checked against the selected option's local ID set. |
| One option borrows another option's verification | Coverage is complete and independently checked per option. |
| A boundary references foreign components or threats | Components, data classes, and threat IDs must be local and exact. |
| Migration cannot be reversed | Dependencies are prior and local; every migration step binds one exact rollback step and vice versa. |
| Reserves are declared but not funded | Exact quantities reconcile rollback reserve, verification reserve, and nine positive section allocations to each ceiling. |
| Caller labels imply independent approval | All supplied actors must remain unauthenticated; selection and implementation stay unauthorized. |
| Outputs are edited and coherently resealed | Canonical validation reconstructs the request-bound design and compares exact bytes. |

## Migration

No stored schema, pointer, facade, CLI, resource catalog, provider, tool, host, or active
runtime is migrated. Development use requires an explicit package-private import. A
future active binding requires a new ADR, behavioral evaluation, authenticated authority,
durable storage, real lease enforcement, reversible champion migration, and independent
promotion evidence.

## Rollback

Remove the Phase 5B modules, tests, inventory, evidence, and CI verifier, then restore
ADR-034's index entry and the prior CI file. No data conversion or history rewrite is
required. The Phase 5A and Generation Zero paths remain unchanged.

## Acceptance boundary

The maximum permitted result is a stacked draft PR when:

- all thirteen contracts fail closed;
- deterministic successor, request, output, and envelope digests reproduce;
- option-locality, complete verification, trust containment, migration/rollback,
  resource, mutation, and resealing regressions pass;
- the isolated wheel imports and verifies the candidate;
- the 133-resource installed-wheel contract remains unchanged;
- the complete hosted Python, Ruff, Pyright, CodeQL, secret, dependency, wheel,
  SBOM, audit, and provenance gates pass on the exact head; and
- the retained procedural review states that one assistant simulated the roles and
  did not create authenticated independent actors.

## Not established

No design quality, live architecture selection, implementation, customer value,
learning, champion migration, promotion, activation, production readiness, release
readiness, or superiority is established. `B-OPS-09` and P20 remain open.
