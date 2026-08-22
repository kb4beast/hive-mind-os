# Authority hardening successor — current execution DAG

**Overall state: RAW GITHUB AND ROOT-INTEGRATION CANDIDATES IMPLEMENTED; INDEPENDENT REVIEW,
EXTERNAL CUSTODY, AND PROMOTION BLOCKED.** This is the
current, deeper authority DAG. It replaces neither the
historical 39-node Cortex plan nor the unsealed nine-node authority-hardening draft;
it records the successor work required by the latter's retained negative audit.

The machine-readable graph is [`plan.json`](plan.json). It is intentionally a planning
and evidence contract, not an installation into the live controller: the v1 draft
cannot be retroactively sealed. The Curator receipt binds the locally hardened
candidate `3196edf00cdbb8e52388b8a98afabc8bfb833cad` (tree
`36f477e03a803286e300e73e0d1daa88d35fbe5a`); its pre-change base is
`2eef403f4aaf6c482390a241e8f9952cce20e5bc`.

## State legend

- **Green — independently reviewed local evidence:** the exact candidate passed
  independent probes and the full repository gate; this is not an external-authority claim.
- **Amber — retained limitation:** a local result is safe but intentionally incomplete
  for an external-authority claim.
- **Amber / blue — implementation awaiting independent review:** the Builder's local
  result exists, but a new Curator/Judge path must reproduce and disposition it.
- **Blue — pending:** an independent role has not yet performed its required work.
- **Red — blocked by external authority:** execution needs non-agent-controlled key
  custody/verifier configuration and a deployment ceremony.
- **Gray — blocked by an ancestor:** final judgment cannot occur before both the
  independent review and the external root.

## Nodes, responsibility, level, and lesson

| Level | Node | Responsible role | State | Learning / lesson retained |
| --- | --- | --- | --- | --- |
| 0 | `GRANT-2010` | Builder + Integrator | green | Fixture-only anchoring is not deployment; bare ledgers must deny issuance and spending. |
| 0 | `EFFECT-2020` | Builder + Integrator | green | A token is only live while its issuing registry can check expiry and revocation. |
| 0 | `LEGACY-2030` | Builder + Integrator | green | A compatibility seam that bypasses authority is an authority bypass; refuse until migrated. |
| 0 | `DURABILITY-2050` | Steward | green / amber | Local recovery is adapted and evidence-backed; external root custody remains blocked. |
| 1 | `AUTONOMOUS-2040` | Builder + Integrator | green | Caller-controlled flags do not grant remote I/O to a retired runtime. |
| 1 | `RAW-GITHUB-2070` | Architect + Integrator | amber / blue | An adapter that delegates to raw delivery merely moves the bypass one layer down. |
| 1 | `ROOT-INTERFACE-3010` | Builder + Integrator | amber / blue | A verifier interface makes integration possible, but a fixture verifier is not an external operator. |
| 2 | `CURATOR-2900` | independent Curator | green | Independent local review is recorded, with full dissent retained. |
| 2 | `RAW-CURATOR-2970` | independent Curator | blue | Test the legacy client used by the executor, not only its controlled caller. |
| 2 | `ROOT-CURATOR-3020` | independent Curator | blue | A verifier protocol can be locally correct while no verifier exists outside the process. |
| 2 | `ROOT-3000` | Owner-controlled root operator | red | An issuer string and process-local digest are attribution records, not authentication. |
| 3 | `JUDGE-3910` | independent Judge | green | Scoped local adoption is final; it cannot claim full authority. |
| 3 | `RAW-JUDGE-3920` | independent Judge | blue | A local effect context blocks bypasses; it does not authenticate a root. |
| 3 | `ROOT-JUDGE-3930` | independent Judge | blue | Integration readiness is not root deployment, custody, or authority. |
| 4 | `PROMOTION-3990` | independent Judge + root operator | gray | Full promotion waits for the external root and raw-API migration. |

## Edges and completion conditions

```text
GRANT-2010 ────────────────────────────────────┐
EFFECT-2020 ───────────────────────────────────┼──> CURATOR-2900 ─> JUDGE-3910 ─┐
LEGACY-2030 ─> RAW-GITHUB-2070 ─> RAW-CURATOR-2970 ─> RAW-JUDGE-3920 ──────────┼──> PROMOTION-3990
DURABILITY-2050 ─> AUTONOMOUS-2040 ────────────┤                               │
DURABILITY-2050 ─> ROOT-INTERFACE-3010 ─> ROOT-CURATOR-3020 ─> ROOT-JUDGE-3930 ┤
                                      └────────> ROOT-3000 (external) ──────────┘
```

The three level-zero authority controls are Curator-verified on the first exact candidate;
the retired autonomous transport is also proven locally inert. `RAW-GITHUB-2070` now
quarantines public raw writes and moves the production workspace push under a live,
grant-bound effect invocation (ADR-064), but it is amber/blue until `RAW-CURATOR-2970`
and `RAW-JUDGE-3920` independently review this later candidate. `ROOT-INTERFACE-3010`
now provides the replaceable attestation/verifier integration contract (ADR-065), but it is
also amber/blue until `ROOT-CURATOR-3020` and `ROOT-JUDGE-3930` review it. It records no
claim that a fixture verifier is an external operator. `DURABILITY-2050` has a Steward
**ADAPT** verdict for local recovery only: it deliberately does not establish external root
custody. The original independent Judge has adopted only the earlier scoped local controls
and has expressly left promotion blocked.
`DURABILITY-2050` must establish a current durable-receipt basis before any external
root integration. The new Curators must reproduce their candidates on the exact head,
preserve dissent, and validate the historical residuals. `ROOT-3000` cannot be dispatched
by an agent: it needs a non-agent-controlled verifier/key source, origin/rotation/revocation
policy, and a deployment receipt. `JUDGE-3910` can judge only the first scoped local
candidate; `RAW-JUDGE-3920` and `ROOT-JUDGE-3930` can judge only their respective successor
contracts. `PROMOTION-3990` cannot truthfully reach `COMPLETE` until both the external root
and both independently judged local successors are resolved.

## Non-negotiable evidence rules

- Do not mark the 2026-08-13 plan complete; it remains `DRAFT-UNSEALED`.
- Do not call local SHA-256 seals or in-process provenance an authenticated owner root.
- Do not restore legacy direct delivery just to make an integration test pass.
- Preserve the original retained audit, adverse probes, and the distinction between
  local closure and external trust establishment.
- Run the repository CI gate, then record the exact commit/tree, changed paths, test
  commands, independent review, and rollback reference before any promotion decision.

## External-root handoff

The owner-controlled operator must provide a verifier/root that is outside the agent
process, with documented custody, issuer identity, rotation/revocation policy,
deployment target, and a safe rollback. The successor can prepare to consume that
authority but must not create or impersonate it. Until this handoff exists, remote
delivery remains outside the completed portion of the DAG.
