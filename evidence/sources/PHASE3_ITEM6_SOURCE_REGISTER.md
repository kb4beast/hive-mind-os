# Phase 3 item 6 source and claim register

## Provenance boundary

Item 6 adds no newly retrieved external source. Its internal requirements are pinned
to base `376a4a6082f6bdf154ba6252ccb70062a17a549b`. The founding docket was reviewed
but is not cited for federation, tenant-isolation, recursion, or self-host claims
because it contains no such atomic proposition.

| Source ID | Exact retained source | Atomic use | License/provenance disposition |
| --- | --- | --- | --- |
| `P3I6-INTERNAL-DESIGN` | `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`, blob `5674febd4fdd6b9ac8a4be9bc4c003881412ba5a`, lines 828–883 | repository/tenant/lineage identity, safe-public portfolio choices, relative-link identity, nested-vault prohibition, generated-directory exclusion, recursion fields/guards, challenger path | repository-owned design record; MIT repository |
| `P1-MEM-CLAIMS` | `evidence/courts/P1-ATOMIC-CLAIM-REGISTER.md`, blob `ea78117b66a1546b440523c888388cc2b254eeb6` | `MEM-024`, `MEM-025` | repository court record; MIT repository |
| `P1SRC-OBSIDIAN-HELP/SRC-OB-05` | `evidence/courts/P1-SOURCE-ADMISSION.md`, blob `2c6fd1668395c67b8588f370e158ad09bff96a4c`; `evidence/sources/PHASE1_PRIMARY_SOURCE_REGISTER.md`, blob `99fe94c5fefc06e7748ec05ef85912dc904d7960`; official help commit `29e89022c6aeb0a9e9971b6f0c98733dbc2eb716`; retained Manage-vaults page SHA-256 `c57c9d0d93ce60b805a0419584ff3aa7ecd2a35315e6c79c81207aab60585ee3` | nested vaults can produce link-update problems | `adapt` by reference only; documentation license unresolved; no help text or code copied |
| `P3I6-ITEM2-BOUNDARY` | `docs/architecture/PHASE3_PUBLIC_PRIVATE_MEMORY_CONTRACT.md` blob `602848215e381fc8e158a79498365539c9c3b85e`; `evidence/phase3/phase3_memory_separation_inventory.json` blob `1182b62a810f8839bbff0fba8e3bfdd019edd9ae` | safe-public admission and protected-store exclusion | exact inherited contract/inventory at base |
| `P3I6-ITEM3-BOUNDARY` | `docs/architecture/PHASE3_COGNITIVE_NOTES_CONTRACT.md` blob `5a8dda41f2008591c914c952f1b2fd85493e3c41`; `evidence/phase3/phase3_cognitive_notes_inventory.json` blob `5baeae967550c7a68179125f8c6b6135925f3390` | strict cognitive manifest/note inputs and generated namespace | exact inherited contract/inventory at base |
| `P3I6-ITEM4-BOUNDARY` | `docs/architecture/PHASE3_OBSIDIAN_VIEWS_CONTRACT.md` blob `54f13f5e88875dc61c83dc04c61735820ef0ef7f`; `evidence/phase3/phase3_cognitive_views_inventory.json` blob `e8ad847aaf4121d0525abda2d7a28e8352f330dd` | generated-view authority boundary | exact inherited contract/inventory at base |
| `P3I6-ITEM5-BOUNDARY` | `docs/architecture/PHASE3_OBSIDIAN_VAULT_REFRESH_CONTRACT.md` blob `ae62c2f6a8c3ca10651850a3f579e6ca62f6eb2d`; `evidence/phase3/phase3_obsidian_vault_refresh_inventory.json` blob `e4313b6ef1700a647ff7432fad570d59bc9a4061` | local vault/write boundary and item-5 sealed input | exact inherited contract/inventory at base |

No unavailable content is inferred. No network protocol, identity standard,
distributed database, documentation reuse right, or external superiority evidence is
claimed.

## Atomic claims, dispositions, and receipts

`Builder` owns implemented guards; `Integrator` owns later adapter wiring;
`Optimizer` owns later challenger evaluation. Removing the generated portfolio is
the common item-6 rollback unless a row says otherwise.

| ID | Atomic proposition | Disposition | Evidence/acceptance mapping | Counterclaim or deferred obligation |
| --- | --- | --- | --- | --- |
| `FED-001` | Federation must not cross tenants. | `adapt` | exact tenant equality and cross-tenant rejection tests; Builder | Caller-supplied strings are not authentication. |
| `FED-002` | Portfolio identity must be local; source identity is provenance only. | `adapt` | manifest/note identity tests and schemas; Builder | Ordinary-clone, fork, mirror, and lineage reconciliation are deferred. |
| `FED-003` | Only strict released safe-public notes may federate. | `adapt` | full payload/schema/hash/scope negative tests; Builder | Upstream public-release authenticity remains trusted. |
| `FED-004` | Source and portfolio vaults must never overlap or nest. | `adapt` | canonical `<vault>/hive-mind/generated-cognitive` inputs derive source-vault roots; check/project sibling-in-vault and pairwise nested-source regressions prove zero output mutation; Builder | Path-alias and platform coverage remains bounded. |
| `FED-005` | Generated output must not recursively become ingestion, projection, telemetry, idea, or delegation work. | `adapt` | five negative decision tests; Builder | This deterministic primitive is not persistent enforcement. |
| `FED-006` | Repeat and changed-subject treatment needs bounded scoped identity and epoch rules. | `adapt` | collapse, scope, bounds, and regressed-epoch tests; Builder | Persistent cross-process history is deferred. |
| `FED-007` | Delivery must be reversible and source read-only. | `adapt` | no-replace, drift, staging, final-revalidation, and rollback receipts; Builder | Updates, deletion, multi-writer recovery, and fsync durability are deferred. |
| `FED-008` | Relative Markdown is portable; Wikilinks, mutable paths, block references, and cross-vault links cannot be canonical identity. | `adapt` | materialized portfolio-local records contain no cross-vault canonical links; Architect | General link portability is not proved. |
| `FED-009` | Explorer should exclude generated memory/projection directories from novelty scans. | `defer` | no Explorer adapter is changed by item 6; Integrator owns a later enforced exclusion and regression | A guard function alone cannot establish scan exclusion. Rollback: no adapter activation. |
| `FED-010` | Self-improvement must use the normal versioned challenger, independent evaluation, authority, and rollback path. | `defer` | no challenger/promotion path is changed; Optimizer owns later held-out evaluation | No learning or promotion claim is admitted. Rollback: retain current champion. |
| `FED-011` | Every affected adapter must enforce the self-host decision before side effects. | `defer` | item 6 exposes only the strict decision primitive; Integrator owns adapter enforcement tests | No full-system no-loop claim is admitted. Rollback: leave adapters inactive. |
| `FED-012` | A portfolio may use sanitized materialized records or clearly nonauthoritative deep links. | `adapt` to materialized records | strict local rerendering, bounded hashes, and no source mutation; Builder | Deep links remain an unimplemented nonauthoritative alternative. |

## Alternatives heard

| Alternative | Supporting case | Adverse evidence | Disposition |
| --- | --- | --- | --- |
| No change / defer item 6 | smallest surface and zero new write path | leaves `MEM-024`/`MEM-025` without executable bounded evidence | `reject` for this candidate scope; remains the rollback |
| Manifest/index-only portfolio | less copied output and cheaper refresh | does not create the inspectable local note surface required by the selected item; usefulness remains unmeasured | `defer` pending representative workload evidence |
| Nonauthoritative cross-vault deep links | low duplication | paths are mutable, cross-vault links are not portable canonical identity, and tenant/source availability stays coupled | `defer` as explicitly nonauthoritative only |
| Sanitized materialized local records | stable local bytes, new local IDs, source independence, reproducible validation | duplicates released bytes and needs bounded refresh/recovery | `adapt` for opt-in first publication only |
| Shared writable federated store | direct multi-repository query/update | ownership, isolation, lineage, deletion, concurrency, and recovery are unproved | `defer` |

No alternative has a usefulness, scale, cost, privacy, security, or superiority
verdict. The selected design is only the narrowest executable item-6 candidate that
satisfies the admitted internal obligations.
