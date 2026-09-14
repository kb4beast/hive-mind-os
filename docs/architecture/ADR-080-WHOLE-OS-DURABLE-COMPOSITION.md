# ADR-080: One durable campaign composition with separate delivery authority

Date: 2026-09-14
Status: proposed by N01 Architect/Advocate; independent Cross-Examiner returned ADAPT; Witness and Judge pending

## Requirements and sources

Requirements: R01, R02, R04, R07, R10, R15, R18. Sources: `OWNER-IMPLEMENTATION-01`, `HANDOFF-01`, `LOCAL-01`, `GOV-ADR-075`, `GOV-ADR-076`, `GOV-ADR-077`, `GOV-ADR-078`, and RUNBOOK contracts C01, C03, and C06.

## Decision proposed by the Advocate

Use one durable campaign composition over the existing scheduler, continuity, binding, outbox, verification, and delivery seams. Mission state derives from the declared event/receipt boundary. Code PR delivery and lessons delivery are explicit later publication stages with distinct grants, credentials, idempotency keys, reconciliation, and qualification inputs. A portable plan, generation manifest, branch name, or local authority envelope cannot activate execution or authorize push, merge, deployment, or signing.

Alternative considered: a second queue/workflow truth store. It may benefit a proven multi-host fleet, but currently adds migration and consistency cost. Another rejected alternative is giving builders forge credentials; that collapses independent qualification and effect authority.

## Court record and pending independent work

Advocate argument: composition at existing typed seams minimizes duplicate state while preserving separately revocable publication authority and effect reconciliation.

Examiner objection to investigate: one service may become a single failure/authority concentration point; recovery could double-deliver after an uncertain effect; compatibility state may be misread. The independent `N01_EXAMINER_REVIEW.md` at `78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4` returned ADAPT; its concrete renderer/provenance repairs do not remove this later runtime burden.

Expert testimony requested: a durability/effect expert should trace crash points, fencing, outbox reconciliation, and grant revocation across N08, N10, N15, and N16. No testimony is fabricated.

Independent disposition requested: a separate Judge must decide the topology and authority separation on exact candidate receipts.

## Tests, migration, and rollback

N01 tests reject unauthorized external effects and copied signature fields; N08/N10/N15/N16 later own fresh-process, crash, and idempotent-effect tests. Migration creates a new immutable configuration/plan generation and refuses ambiguous legacy state. Rollback stops new v2 admissions and selects the prior compatible service/configuration; durable receipts and uncertain-effect obligations remain.
