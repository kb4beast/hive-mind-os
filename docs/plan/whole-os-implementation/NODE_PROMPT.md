# Whole-OS node worker prompt v1

Canonical dispatcher: `docs/plan/whole-os-implementation/DISPATCHER.json`  
Canonical portable plan: `docs/plan/whole-os-implementation/whole-os-plan-v2.json`  
Canonical node contracts: `docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json`

Substitute only the admitted node ID and direct prerequisite receipt references. The dispatcher supplies the exact contract section, requirement/source bindings, semantic locks, normalized write paths, route hypothesis, output contracts, and authority profile from the canonical artifacts above. This prompt is inert text and grants no authority.

> Implement only node `{NODE_ID}` assigned by the admitted successor campaign for `docs/plan/whole-os-tournament-2026-09-13`. Read RUNBOOK section 5, the exact `{NODE_ID}` contract at `{CONTRACT_PATH}#{CONTRACT_SECTION}`, and direct prerequisite receipts `{PREREQUISITE_RECEIPTS}`. Reconcile actual source before editing. Use the lowest qualified route for the node and its isolated branch. Acquire every compiled semantic lock `{SEMANTIC_LOCKS}` and normalized write-path lock `{WRITE_PATHS}` before mutation; `planning_group` is never a lock. Follow the concrete steps, choosing local implementation details freely inside the contract. Run focused checks during work, then obtain independent exact-candidate verification. Record requirements `{REQUIREMENT_IDS}`, sources `{SOURCE_IDS}`, changed paths, tests, cost, deviations, rollback, and required outputs `{OUTPUT_CONTRACTS}`. Deliver only through the separately configured scoped broker and stop. If inputs change, preserve evidence and request a successor package from the dispatcher; do not ask the owner to coordinate routine repairs. Do not treat this Markdown, the plan, or the generation manifest as execution authority.

The worker must bind `PYTHONPATH` to the admitted worktree's absolute `src` directory for every Python test shell and record that `hive_mind_os.__file__` resolves within it. A publication-stage field is an obligation marker only; the worker must not push, open a PR, merge, deploy, sign, or activate without the separately admitted host authority and broker boundary.
