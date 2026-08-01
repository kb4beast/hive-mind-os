# Phase 5J external independent-adoption review handoff

## Purpose

This is a reviewer-facing handoff for a real external review of ADR-015 and the proposed P14–P20
program. It is not an approval, signature, identity attestation, adoption decision, P14 authorization,
or release decision.

## Frozen repository context

- Repository: `kb4beast/hive-mind-os`
- Integration branch: `agent/phase5a-orchestrator-shadow`
- Phase 5I merge commit: `49b78e211053f8aec427351680c3fd683044420d`
- Packet branch: `agent/phase5j-independent-adoption-review-packet`
- Packet PR: use the Phase 5J PR opened from this branch
- Source branches must remain preserved
- `main`, `release/version_1.1`, and PR #49 are outside this review and must not be changed

At review start, record the exact Phase 5J PR head SHA and tree. Reject any later head movement unless
the review is restarted and every identity, scope, evidence, and signature binding is recomputed.

## Required external participants

The participants must be distinct, authenticated, non-self-issued, revocable, and conflict checked:

1. **Curator** — evaluates completeness, adverse evidence, sources, debt, tests, and claim boundaries.
2. **Judge** — selects one permitted disposition: `adopt`, `adapt`, `reject`, `defer`, or `abstain`.
3. **Orchestrator** — confirms exact scope, dependencies, authority, rollback, expiry, and next action.

The packet preparer, code author, affected candidate, or a shared unauthenticated identity cannot
satisfy these roles.

## Required review inputs

Review the exact bytes and bindings for:

- ADR-015;
- `docs/plan/01_POST_P13_OVERVIEW.md`;
- `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`;
- `docs/plan/PHASE5I_TERMINAL_RECEIPT.md`;
- this Phase 5J contract, implementation, tests, ledger, and handoff;
- all thirty open or reopened Phase 5D–5I debt items;
- Constitutional CI runs named in the debt plan, including adverse worker and static/type evidence;
- all six missing external-input classes.

Do not treat local digests, merged PRs, procedural role labels, passing subsets, or this handoff as
proof of authenticated independence or external retention.

## Required evidence from each participant

Each participant must return evidence bound to the exact packet head, tree, repository, tenant, role,
scope, decision, timestamp, expiry, authority, and evidence index. Evidence must include:

- identity issuer and verification method;
- role separation and conflict-of-interest disclosure;
- signature and key identifier;
- expiry and revocation data;
- replay nonce or equivalent anti-replay binding;
- externally retained immutable or append-only record reference;
- explicit reviewed document and evidence digests;
- dissent, exclusions, unresolved obligations, and scope limitations;
- rollback and emergency revocation requirements.

Secrets and private signing material must never be committed to the repository.

## Decision rules

- `adopt` may permit only the exact proposed program and may unlock only the next permitted phase.
- `adapt` must state exact required changes and narrowed scope before another review.
- `reject` preserves the packet and all evidence without activating the program.
- `defer` must list missing evidence and a future review trigger.
- `abstain` records the participant’s inability to issue a disposition and cannot count as approval.

No disposition clears Phase 5 debt, source/license blockers, production-readiness gates, superiority
burdens, or later P14–P20 exit criteria by itself.

## External-review completion checklist

- [ ] Exact PR head and tree frozen
- [ ] Curator identity and signature verified
- [ ] Judge identity and signature verified
- [ ] Orchestrator identity and signature verified
- [ ] Conflicts and role separation verified
- [ ] All thirty debts reviewed and preserved
- [ ] All adverse and inconclusive evidence reviewed
- [ ] One permitted Judge disposition recorded
- [ ] Curator recommendation recorded
- [ ] Orchestrator scope/rollback/expiry confirmation recorded
- [ ] Signed records retained outside agent-controlled storage
- [ ] Replay, expiry, revocation, and tamper checks passed
- [ ] Result returned with exact scope and exclusions

Until every applicable item is evidenced, status remains:

```text
review_status: not-run-or-incomplete
adr_015_adopted: false
p14_eligible: false
p20_eligible: false
release_ready: false
production_ready: false
authority: none
activation: inert
```

## Copyable external reviewer instruction

```text
Repository: kb4beast/hive-mind-os
Review branch: agent/phase5j-independent-adoption-review-packet
Integration base: 49b78e211053f8aec427351680c3fd683044420d

Perform an independent adoption review of ADR-015 and the full proposed P14–P20 program. Freeze and
record the exact Phase 5J PR head and tree before reviewing. Review the complete debt plan, terminal
receipts, adverse evidence, all thirty open/reopened Phase 5D–5I items, and all six missing external
input classes.

Use distinct authenticated Curator, Judge, and Orchestrator participants. Verify non-self-issued
identity, role separation, conflicts, signatures, exact scope, expiry, revocation, replay protection,
and external append-only retention. Do not use repository-local labels, local digests, passing CI
subsets, or procedural role simulation as proof of independence.

The Judge may select only adopt, adapt, reject, defer, or abstain. Preserve dissent, exclusions,
missing evidence, losing/adverse results, and rollback requirements. Any adoption may unlock only the
next explicitly permitted phase; it cannot clear debt, release, production, source/license, or
superiority gates.

Return signed, externally retained evidence bound to the exact repository, head, tree, documents,
participant roles, scope, decision, authority, expiry, revocation, and evidence index. Do not commit
secrets or private signing material. Until valid evidence is independently verified, keep ADR-015
adoption, P14/P20 eligibility, release, production, deployment, promotion, superiority, authority,
and activation false.
```
