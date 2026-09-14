# ADR-079: Whole-OS campaign topology and flexible local execution

Date: 2026-09-14  
Status: proposed by N01 Architect/Advocate; independent Examiner, Witness, and Judge disposition pending

## Requirements and sources

Requirements: R01, R02, R03, R05, R06, R15, R17, R18. Sources: `OWNER-IMPLEMENTATION-01`, `HANDOFF-01`, `LOCAL-01`, `GOV-DAG-01`, `GOV-ADR-072` through `GOV-ADR-078`, and accepted N00 inventory `WOS-N00-20260914-01`. The analytical H02 selection is design evidence only; production and superiority remain deferred.

## Decision proposed by the Advocate

Adopt a versioned 34-node portable campaign whose nodes fix objectives, dependencies, requirements, evidence, output contracts, semantic locks, normalized write paths, route hypotheses, review obligations, migration, and rollback. Builders retain freedom to reorder local implementation steps and repair within those boundaries. Preserve direct role ownership and the external DAG boundary. Preserve the 13-stage `external-all-aspect-tournament-v2` as schema-v1 compatibility rather than rewriting its historical meaning.

Alternative considered: retain the fixed small-improvement tournament as the only topology. It is simpler and remains preferable for a narrow trusted repair, but does not represent the accepted whole-OS lifecycle. Distributed workflow replacement remains deferred until measured scale evidence justifies its migration burden.

## Court record and pending independent work

Advocate argument: extending the existing portable compiler with a closed v2 work-package layer reuses proven identity, DAG, authority, and generation seams without coupling delivered applications to Hive. Exact locks make concurrency a contract rather than a `planning_group` guess.

Examiner objection to investigate: a larger declarative graph can hide ambiguous ownership, stale source mappings, excessive ceremony, or accidental self-approval; lock normalization may serialize safe work or miss aliases. No N01 Examiner statement has been authored by this Advocate.

Expert testimony requested: an independent Integrator/Steward should reproduce v1 compatibility, v2 round compilation, dependency recovery, and path-conflict behavior on the exact candidate. No N01 expert testimony is claimed here.

Independent disposition requested: a Judge distinct from the Architect/Advocate/Builder must issue `adopt|adapt|defer|reject|quarantine` for this proposal and each affected requirement. Status remains proposed until that artifact exists.

## Tests, migration, and rollback

`tests/test_whole_os_plan_contract.py` proves 34-node coverage, exact dependency binding, requirement closure, lock/path presence, lock-aware serialization, negative compilation, and preservation of the v1 13-stage profile. Migration admits schema v2 only for new generations; schema v1 remains readable/compilable. Rollback selects the v1 compiler/profile for new admissions and preserves v2 plan/generation bytes as append-only evidence. No active host plan or signed artifact is changed.
