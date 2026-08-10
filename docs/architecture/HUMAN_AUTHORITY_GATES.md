# Human Authority Gates

**Status:** active boundary record  
**Established:** 2026-08-03 by P5.2

The P14–P20 program is withdrawn as an executable roadmap. Its external-input
requirements survive here as explicit gates; they are not work an agent may work
around, simulate, or convert into a claim of completion.

| Gate | Required human or external input | Blocks |
|---|---|---|
| G1 — Branch fork resolution | Owner decision on P0.4: archive and cherry-pick selected hardening, or merge the branch. | P0.4 |
| G2 — First real model mission | An approved model-authentication boundary (API key with spend limit, or a locally signed-in subscription), explicit real-call permission, and a bounded local scope. | P1.5, B-OPS-03 |
| G3 — External identity and signing | Non-agent-controlled credentials from an external authority. | B-GOV-02, B-GOV-03 |
| G4 — External append-only retention | Storage account and recovery authority. | B-GOV-04 |
| G5 — Production pilot | Deployment account, approved scope, users, and rollback authority. | B-OPS-04 |
| G6 — Comparator access | Licensing and access for benchmark comparators. | B-OPS-05 |
| G7 — Founding-source licensing | Video ingestions and source-license resolutions. | B-SRC-01 through B-SRC-11 |
| G8 — Independent human review | A second person, or an explicit solo-project declaration. | Any claim of independent human judgment |

G8 is a truth boundary: separately prompted agent identities are procedural separation,
not authenticated independent human review. The current blocker backlog remains
[BLOCKERS.md](../plan/BLOCKERS.md); this file records only authority dependencies.

## Original owner decisions recorded on 2026-08-04

The repository owner selected the verification-first recommendation for G1–G7. The
controlling decision and evidence are [ADR-043](ADR-043-VERIFICATION-FIRST-OPEN-SOURCE-POSTURE.md).

| Gate | Current owner decision |
| --- | --- |
| G1 | Resolved without a merge: P0.4 heads are already represented in `main`; preserve their refs as history. |
| G2 | No real model API key, spend, or mission is authorized. P1.5 remains closed. |
| G3 | No stable or production-positioned release until an externally controlled signing identity exists. |
| G4 | No external append-only evidence store is authorized. |
| G5 | No production pilot is authorized. |
| G6 | Read-only intake is authorized for the three pinned MIT comparator records in ADR-043; executing them and a qualifying court remain blocked. |
| G7 | Existing unresolved source and license obligations remain non-promoting deferrals. |
| G8 | No decision recorded; independent human review remains open. |

## Owner decision amendment — 2026-08-06

The repository owner authorizes local real-model calls through the already signed-in Codex
ChatGPT subscription only. No API key may be requested, read, passed to a subprocess, or
used for this authority path, and no API usage-based spend is authorized. The `codex_subscription`
transport must use its default subscription model unless the owner explicitly supplies a
subscription-eligible model choice.

This authority permits bounded local model turns and a later public-repository exercise only.
It does not authorize a GitHub, package registry, signing, storage, deployment, or other
third-party credential; it does not authorize remote delivery; and it does not close
`B-OPS-03`. The real-provider evidence burden, independent reproduction, authenticated
identity, hard isolation, and all other gates remain separate.

## Deferred program

The owner-owned, untracked `NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` program
is deferred in full. It does not authorize Obsidian, memory-plane, telemetry,
federation, or host-extension work unless a user explicitly requests that program.
