# ADR-081: Tenant-bound learning and draft-only cross-repository lessons

Date: 2026-09-14  
Status: proposed by N01 Architect/Advocate; independent Cross-Examiner returned ADAPT; Witness and Judge pending

## Requirements and sources

Requirements: R07, R08, R09, R10, R11, R13, R18. Sources: `OWNER-ORIGINAL-01`, `OWNER-IMPLEMENTATION-01`, `HANDOFF-01`, `LOCAL-01`, EX08, RUNBOOK C01/C05/C07, and the accepted N00 external-source/archive obligations.

## Decision proposed by the Advocate

Partition memory, caches, logs, artifacts, provider routing, challengers, and evidence by trusted tenant and repository identities. Route app learning only to the app subject. An external-origin Hive lesson remains a sanitized immutable DRAFT obligation until a separate learning court admits it. Target code, assets, logs, secrets, paths, private locators, and raw evidence never enter a Hive lessons contribution. Publication, document merge, lesson adoption, and champion activation are distinct events.

Alternative considered: one global target store with namespace strings and automatic activation after publication. Reject it for this design because model-authored namespaces and status changes are not custody or authority boundaries. A no-learning profile remains a valid ablation, not a weakened privacy profile.

## Court record and pending independent work

Advocate argument: typed custody handles and separate draft/promotion routes implement the owner's lessons-only intent while permitting private app improvement.

Examiner objection to investigate: hashes, errors, embeddings, copied snippets, or generalized prose can still disclose private information; scanners cannot prove universal non-leakage. The independent `N01_EXAMINER_REVIEW.md` at `78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4` returned ADAPT; its concrete renderer/provenance repairs do not close the deferred disclosure claim.

Expert testimony requested: a privacy/security expert should attack storage, provider payload, staged bytes, exception paths, and promotion shortcuts, including non-regex canaries.

Independent disposition requested: a distinct Judge must disposition the boundary and any residual disclosure claim; zero observed leaks must not become a universal guarantee.

## Tests, migration, and rollback

N19–N21/N25/N29 own tenant-collision, export, draft-to-active, and promotion negative tests. Migration quarantines legacy unbound data and assigns no tenant from filenames. Rollback revokes new retrieval/export routes, retains encrypted/audit evidence, and restores the prior per-subject champion pointer without copying target data into Hive.
