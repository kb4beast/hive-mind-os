# ADR-043: Verification-first open-source posture and comparator intake

- **Status:** Adopted
- **Date:** 2026-08-04
- **Scope:** public open-source positioning, owner authority decisions, and read-only comparator intake

## Context

Hive Mind OS currently provides a local, deterministic way to verify a committed
agent-authored change against a sealed executable acceptance specification and retain a
receipt bundle. It does not provide a general coding agent, production operation, remote
delivery, hard hostile-code isolation, or routine real-model execution.

P5.2 withdrew P14–P20 as an executable roadmap and retained their external dependencies
as Human Authority Gates. The owner then selected the verification-first recommendation
for G1–G7, with the explicit exception that comparator access (G6) must begin now.

## Decision

The public project remains a provider-neutral, local-first verification tool. It must not
present the broader target operating system as current product capability.

| Gate | Owner decision | Effect |
| --- | --- | --- |
| G1 — Branch fork resolution | Archive the P0.4 decision without another merge. The three remote P0.4 patch heads are patch-equivalent to `main`; the local owner-gate head is an ancestor of `main`. Preserve the refs as history. | No branch deletion, merge, or cherry-pick is required. G1 is resolved. |
| G2 — First real model mission | Do not authorize a live provider, API key, or spend. | Real-model missions and P1.5 remain closed. |
| G3 — External identity and signing | Keep v0.x explicitly prototype-only. Require an externally controlled signing identity before any stable or production-positioned release. | No signing or authorship claim is added. |
| G4 — External append-only retention | Do not provision an external evidence store. | Local receipts and the existing Git archive remain the only retention boundary; no external-retention claim is allowed. |
| G5 — Production pilot | Do not authorize a pilot. | No users, deployment account, or production-readiness claim is added. |
| G6 — Comparator access | Authorize read-only intake of the three pinned public repositories in the record below. | Access is established only for provenance and future benchmark design; no comparator code may be executed, copied, or presented as a completed benchmark. |
| G7 — Founding-source licensing | Retain the current non-promoting deferrals for unresolved source custody and license obligations. | No unresolved source may support implementation, promotion, or a public capability claim. |
| G8 — Independent human review | No decision was requested or recorded. | The gate remains open; agent separation is not represented as independent human review. |

## G6 comparator-intake record

The owner authorizes the following records for read-only source and license intake. The
captured license bytes, commit pins, retrieval time, and restrictions are in
[`comparator-intake-2026-08-04`](../../evidence/sources/comparator-intake-2026-08-04/manifest.json).

| Founding reference | Repository and immutable pin | License signal |
| --- | --- | --- |
| `SRC-003` — Operator OS | `rangerrick337/operator-os` at `150004fc630505045a301cce32a4781824f89ac6` | MIT, captured at the pin |
| `SRC-004` — Hermes Agent | `NousResearch/hermes-agent` at `f5be9236e00ddf2f2a412697f267078fc4ee068e` | MIT, captured at the pin |
| `SRC-009` — related OpenHands paper | `OpenHands/OpenHands` at `1a88ae637757758241c8cf571923fdab7839a89b` | MIT, captured at the pin; the code repository is separately captured here |

This is not legal advice or a compatibility determination for models, data, service terms,
trademarks, or a future executable benchmark. It records only the observed repository
license files and permits the limited intake described above.

## Court record

- **Advocate:** a narrow, offline verifier is the current useful open-source offering. It
  can earn evidence and contributors without a model account, hosted service, or false
  autonomy claim. Three public, pinned MIT repositories are sufficient to begin a future
  comparator-intake record.
- **Cross-examiner:** a repository's MIT file does not authorize a hosted model, dataset,
  trademark use, production pilot, code execution, code copying, or a superiority claim.
  The three systems are not yet equalized comparators, and the required isolation,
  authenticated receipts, held-out tasks, budgets, and independent judges are absent.
- **Evidence witness:** each repository's primary GitHub license endpoint was retrieved at
  `2026-08-04T13:47:07Z`; the raw returned license bytes and SHA-256 digests are retained
  in the intake record. The P0.4 branch evidence is recorded from local Git's
  patch-equivalence and ancestry checks.
- **Judge:** the repository owner made the decisions in this record. The implementation
  agent may record and enforce them but may not expand them.
- **Disposition:** adopt the bounded verification-first posture and G6 read-only intake;
  defer all broader capabilities and preserve the remaining blockers.

## Consequences

`B-OPS-05` remains open. A qualifying comparison still requires at least three materially
distinct pinned systems, two task families, equalized authority and budgets, repeated
held-out runs, retained losing results, safety floors, and independent judgment. Nothing
in this record permits a superiority statement.

## Rollback

Revert this record and the linked authority annotations to restore the prior undecided
posture. The captured license exhibits, branch history, and unresolved source obligations
remain preserved and must not be rewritten.
