# Human Authority Gates

**Status:** active boundary record  
**Established:** 2026-08-03 by P5.2

The P14–P20 program is withdrawn as an executable roadmap. Its external-input
requirements survive here as explicit gates; they are not work an agent may work
around, simulate, or convert into a claim of completion.

| Gate | Required human or external input | Blocks |
|---|---|---|
| G1 — Branch fork resolution | Owner decision on P0.4: archive and cherry-pick selected hardening, or merge the branch. | P0.4 |
| G2 — First real model mission | API key, spend limit, and real-call permission. | P1.5, B-OPS-03 |
| G3 — External identity and signing | Non-agent-controlled credentials from an external authority. | B-GOV-02, B-GOV-03 |
| G4 — External append-only retention | Storage account and recovery authority. | B-GOV-04 |
| G5 — Production pilot | Deployment account, approved scope, users, and rollback authority. | B-OPS-04 |
| G6 — Comparator access | Licensing and access for benchmark comparators. | B-OPS-05 |
| G7 — Founding-source licensing | Video ingestions and source-license resolutions. | B-SRC-01 through B-SRC-11 |
| G8 — Independent human review | A second person, or an explicit solo-project declaration. | Any claim of independent human judgment |

G8 is a truth boundary: separately prompted agent identities are procedural separation,
not authenticated independent human review. The current blocker backlog remains
[BLOCKERS.md](../plan/BLOCKERS.md); this file records only authority dependencies.

## Deferred program

The owner-owned, untracked `NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` program
is deferred in full. It does not authorize Obsidian, memory-plane, telemetry,
federation, or host-extension work unless a user explicitly requests that program.
