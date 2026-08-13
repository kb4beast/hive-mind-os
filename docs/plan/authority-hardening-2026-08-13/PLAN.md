# Authority Hardening — follow-on DAG draft (findings 1–5)

**Status: DRAFT — UNSEALED.** This plan closes the locally satisfiable residue that made
A5-900 adjudicate governed-full autonomy **`not-ready`**
([DAG_EXECUTION_HANDOFF.md](../../execution/DAG_EXECUTION_HANDOFF.md) §11, items 1–5).
The machine-readable contract is [`plan.json`](plan.json) beside this file; it passes
`dag-lint --strict` with zero findings and compiles to three dispatch rounds.

Verify both claims before trusting them:

```bash
python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan docs/plan/authority-hardening-2026-08-13/plan.json --strict --json
```

```bash
python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan docs/plan/authority-hardening-2026-08-13/plan.json
```

## What this plan is not

- It does **not** touch §11.6 (the unsigned authority chain in
  `HUMAN_AUTHORITY_GATES.md`) or any human authority gate. Those are owner decisions;
  a node that "fixed" them would be writing its own authorization.
- It is **not sealed**. Sealing binds `baseline.commit`/`baseline.tree` to the then-current
  `main`, computes `plan_fingerprint`, and authors one runbook per node
  (`docs/execution/runbooks/` style). The placeholders in `plan.json` are deliberate:
  a draft must not carry a baseline that will be stale by sealing time.

## Findings → nodes

| Handoff §11 item | Source finding | Node | Fix surface |
|---|---|---|---|
| 1. Effect boundary authenticates nothing | A5-F10 (+F14) | `TOKEN-1010` | `brain_kernel/effects.py` |
| 1. (chain the boundary must consult) | A5-F3, F4, F5, F11, F12, F13, A4 D5 | `REG-1000` | `brain_kernel/authority.py`, `contracts.py` |
| 2. Bundle verdict unauthenticated | A3-F3 | `VERDICT-1100` | `verify.py` |
| 3. Receipt after irreversible effect + MAX_PATH | A4 D1 | `WAL-1200` | `mission_store.py` |
| 4. Grant authenticity and lifetime | A5-F6, A4 D4 | `GRANT-1020` | `cortex/github/grants.py` |
| 4. Gateway read/idempotency surface | A4 D2, D3, D6 | `GATEWAY-1040` | `rest_gateway.py`, `delivery_adapter.py` |
| 5. Containment unproven on Windows | §11.5 | `SANDBOX-1300` | `sandbox.py`, `tests/test_sandbox.py` |
| closure adjudication | all of the above | `REAUDIT-1900` | evidence + results doc only |

## Contract repair — 2026-08-13, before any worker ran

Measuring REG-1000 against real source before dispatch found the acceptance criterion as
first drafted was the wrong shape, so it was repaired rather than worked around:

Sealing the envelope digest changes the digest→envelope mapping the registry keys on, so
it necessarily re-seals **every** call site that registers an envelope — two production
minting sites (`cortex/repository/local_execution.py:211`, `mission_adapter.py:139`, both
registering placeholder digests) and seven test modules. The first draft said the digest is
recomputed "on construction and on registry admission"; construction-time rejection would
break 13 construction sites across 11 files for **no additional security**, because
`AuthorityRegistry` is the boundary A5-F3 actually names.

Repair: enforcement is specified at registry admission plus a pure minting helper;
REG-1000's write scope is widened to exactly the re-sealing surface; and GATEWAY-1040 gains
a dependency on REG-1000 because its fixtures are inside that surface. The compiled rounds
are unchanged, and `dag-lint --strict` stays clean.

## The graph

```
R1 (parallel, 4 sessions):  REG-1000   WAL-1200   VERDICT-1100   SANDBOX-1300
                              │  │        │
                    ┌─────────┘  └──────┐ └──────────┐
R2 (parallel, 3):  TOKEN-1010     GRANT-1020    GATEWAY-1040
                        │              │              │
R3 (serial, 1):         └────────── REAUDIT-1900 ─────┘  (+ edges from all of R1)
```

Ordering edges beyond raw data dependencies (DAG standard §4, recorded here so nobody
"optimizes" them away):

- `GATEWAY-1040 → WAL-1200`: durability before extending the external-effect surface.
  The receipt-before-effect discipline must exist before the remote gateway grows.
- `TOKEN-1010 → REG-1000` and `GRANT-1020 → REG-1000`: both consume the registry lookup
  and attribution surface REG-1000 creates; REG-1000 is forbidden from touching their
  files and vice versa.

## Non-negotiables carried from the executed plan

These earned their place across 39 nodes; every worker prompt must carry them.

- **Mutation evidence is mandatory.** Every closed finding names a test that fails when
  the fix is reverted. A test that cannot fail is decoration (the MISSION-400
  `assertTrue(True)` lesson).
- **REAUDIT-1900 repairs nothing.** The A5 probes are re-run verbatim from the retained
  transcripts; a finding they still reproduce is recorded OPEN. Never force a node
  complete to finish the plan.
- **Retained evidence is immutable.** `evidence/pilots/**` is in every node's
  `forbidden_scope`. Probes are re-run into new evidence directories, never edited.
- **No live remote effects anywhere in this plan.** GATEWAY-1040 tests run against
  recorded fakes. Any live-host validation goes through the owner credential gate, which
  is out of scope here by construction.
- **`PYTHONPATH=src`** on every test command (three workers independently lost time to
  the editable-install shadow without it).
- Seal evidence directories with `git add -f` — `.gitignore:127` is a repo-wide `*.log`
  and has already swallowed retained gate logs once (QUALIFY-610).

## Author-verified checklist (dag-lint cannot see these — §8)

Verified by hand at drafting time; re-verify at sealing:

- Write scopes are narrow: every entry is a literal file path except REAUDIT-1900's
  `evidence/audits/authority-hardening/**`, a new directory it alone owns.
- `required_tests` are literal runnable commands; `tests/test_delivery_grants.py` is the
  only new test module and belongs to exactly one node (GRANT-1020).
- `parallel_safe` is honest: only REAUDIT-1900 is serial (it adjudicates the union).
- `semantic_locks` name interfaces, not files, and are disjoint within each round.
- Safety-before-activation and benchmark-before-promotion (§4) do not bind here: no node
  activates learned behavior or promotes a component to authoritative.
- `pyproject.toml` is in every node's `forbidden_scope` — the shared-manifest scaffold
  warning is resolved by prohibition, not ownership.

## Sealing checklist (what turns this draft into an executable plan)

1. Owner reviews scope — in particular that §11.6 stays out.
2. Bind `baseline` to the then-current `main` commit and tree.
3. Author one runbook per node (contract → procedure, mandated test names, gotchas).
4. Compute `plan_fingerprint`, install via the control-plane bootstrap, and run
   `dag-lint --strict` as the sealing gate.
5. Dispatch with the explicit node lists `dag-rounds` prints — never the greedy fallback.
