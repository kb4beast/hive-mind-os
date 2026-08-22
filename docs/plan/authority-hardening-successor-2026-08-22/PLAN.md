# Authority hardening successor — current execution DAG

**Overall state: LOCAL CANDIDATE IMPLEMENTED; INDEPENDENT REVIEW PENDING; EXTERNAL
ROOT BLOCKED.** This is the current, deeper authority DAG. It replaces neither the
historical 39-node Cortex plan nor the unsealed nine-node authority-hardening draft;
it records the successor work required by the latter's retained negative audit.

The machine-readable graph is [`plan.json`](plan.json). It is intentionally a planning
and evidence contract, not an installation into the live controller: the v1 draft
cannot be retroactively sealed and this successor has not yet received a Curator
receipt. Its pre-change base is `2eef403f4aaf6c482390a241e8f9952cce20e5bc`.

## State legend

- **Amber — implemented, awaiting independent verification:** a local code change and
  its Builder regression tests exist, but it is not a court disposition.
- **Blue — pending:** an independent role has not yet performed its required work.
- **Red — blocked by external authority:** execution needs non-agent-controlled key
  custody/verifier configuration and a deployment ceremony.
- **Gray — blocked by an ancestor:** final judgment cannot occur before both the
  independent review and the external root.

## Nodes, responsibility, level, and lesson

| Level | Node | Responsible role | State | Learning / lesson retained |
| --- | --- | --- | --- | --- |
| 0 | `GRANT-2010` | Builder + Integrator | amber | Fixture-only anchoring is not deployment; bare ledgers must deny issuance and spending. |
| 0 | `EFFECT-2020` | Builder + Integrator | amber | A token is only live while its issuing registry can check expiry and revocation. |
| 0 | `LEGACY-2030` | Builder + Integrator | amber | A compatibility seam that bypasses authority is an authority bypass; refuse until migrated. |
| 0 | `DURABILITY-2050` | Steward | blue | External-root promotion needs current, durable custody and revocation receipts, not an old test claim. |
| 1 | `AUTONOMOUS-2040` | Builder + Integrator | amber | Caller-controlled flags do not grant remote I/O to a retired runtime. |
| 1 | `RAW-GITHUB-2070` | Architect + Integrator + Curator | blue | A safe caller does not make a public unsafe primitive safe. |
| 1 | `ROOT-3000` | Owner-controlled root operator | red | An issuer string and process-local digest are attribution records, not authentication. |
| 2 | `CURATOR-2900` | independent Curator | blue | Re-run adverse probes against the exact candidate; do not inherit a Builder claim. |
| 3 | `JUDGE-3910` | independent Judge | blue | Local adoption is a separate verdict and cannot claim full authority. |
| 4 | `PROMOTION-3990` | independent Judge + root operator | gray | Full promotion waits for the external root and raw-API migration. |

## Edges and completion conditions

```text
GRANT-2010 ────────────────────────────────────┐
EFFECT-2020 ───────────────────────────────────┼──> CURATOR-2900 ─> JUDGE-3910 ─┐
LEGACY-2030 ───────────────> RAW-GITHUB-2070 ──┤                               ├──> PROMOTION-3990
DURABILITY-2050 ─> AUTONOMOUS-2040 ────────────┤                               │
DURABILITY-2050 ─> ROOT-3000 (external) ───────┴───────────────────────────────┘
```

The first four nodes are locally implementable and independently testable.
`DURABILITY-2050` must establish a current durable-receipt basis before any external
root integration. The Curator must reproduce the local assertions on the exact candidate,
preserve dissent and validate the historical residuals. `ROOT-3000` cannot be dispatched
by an agent: it needs a non-agent-controlled verifier/key source, origin/rotation/
revocation policy, and a deployment receipt. `JUDGE-3910` can judge only the scoped
local candidate. `PROMOTION-3990` cannot truthfully reach `COMPLETE` until both
`ROOT-3000` and the explicitly open raw-GitHub migration are resolved.

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
