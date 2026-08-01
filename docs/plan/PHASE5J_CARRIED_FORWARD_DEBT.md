# Phase 5J carried-forward debt

- **Authority:** explicit maintainer direction to preserve unresolved findings, normal-merge the bounded
  Phase 5J packet, and carry unresolved work forward.
- **Applies to:** PR #60 and the Phase 5J source branch.
- **Next owning phase:** Phase 5K External Adoption Evidence Intake.
- **Posture:** accepted integration debt; not an external review, adoption, P14 authorization, release,
  production, deployment, promotion, or superiority decision.

This addendum extends `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`. All thirty Phase 5D–5I open or
reopened items remain active. The following five Phase 5J items are additional and open.

| ID | Finding and evidence | Current impact | Required resolution / exit condition | Status |
|---|---|---|---|---|
| P5J-DEBT-01 | Phase 5J creates a frozen packet manifest, reviewer requirements, unsigned decision templates, and an `external-action-required` handoff. No authenticated external review was run and no outcome was selected or signed. | ADR-015 remains proposed and P14 remains blocked. | Obtain distinct authenticated Curator, Judge, and Orchestrator evidence through the external handoff. Verify signatures, role separation, scope, expiry, revocation, replay protection, and external retention before admitting any decision. | open |
| P5J-DEBT-02 | No Phase 5J inventory generator, chained Phase 5E–5J inventory artifact, installed-wheel verifier, package-resource verification, or permanent CI installation step was added. Permanent verification still stops at Phase 5D. | Packaged external-review packet availability and current-tree inventory integrity are unverified. | Add chained Phase 5E–5J inventories and installed-wheel verification, update permanent CI, and retain successful exact-head artifacts. | open |
| P5J-DEBT-03 | The packet defines external identity, signing, expiry, revocation, replay, conflict, and retention requirements, but no real identity issuer, signing key, decision evidence, retention account, or revocation authority was supplied. | The repository cannot authenticate or retain an independent adoption decision. | Supply external evidence through a non-agent-controlled boundary. Never commit credentials or private signing material. Verify forged, replayed, expired, revoked, cross-scope, and self-issued evidence fails closed. | open |
| P5J-DEBT-04 | Constitutional CI run `30681791236` on source head `f4b96077df02327d966b1c389d584e97efb04ec2` passed all three Python matrices, build/SBOM, CodeQL, secret scan, and dependency/license review. Ruff failed only inherited Phase 5D findings and global Pyright was skipped. | Phase 5J has broad source compatibility evidence but no fully green static/type receipt. | Preserve `docs/plan/PHASE5J_TERMINAL_RECEIPT.md`; repair inherited Ruff and Pyright debt and obtain one exact-head fully successful Constitutional CI run. | open |
| P5J-DEBT-05 | Phase 5J remains package-private, inert, authority-free, and closeout documentation follows the tested source head. Packet readiness is not review completion. | No exact-final-head, authenticated-review, adoption, P14-eligibility, release, production, deployment, promotion, or superiority claim may be inferred. | Implement a bounded external-evidence intake and verifier, then wait for actual external evidence. A later verified permitting result may unlock only the exact next phase and cannot clear unrelated debt. | open |

## Evidence that remains valid

- All Phase 5J tests passed in Constitutional CI run `30681791236` as part of the full suites on
  Python 3.11, 3.12, and 3.14.
- The intermittent worker sweep passed in that run but remains reopened pending deterministic root
  cause and repeated evidence.
- No Phase 5J Ruff finding was reported.
- Packet status is `ready-for-external-review`; review status remains `not-run`.
- Authenticated participants and signed decision presence remain false.

## Handoff to Phase 5K

Phase 5K must create an **External Adoption Evidence Intake** that can validate future external review
artifacts without manufacturing them. It must:

1. bind evidence to the exact repository, Phase 5J merge commit, packet head/tree, document digests,
   participant role, issuer, key identifier, decision, scope, timestamp, expiry, nonce, and retention
   reference;
2. require distinct Curator, Judge, and Orchestrator participants;
3. reject self-issued, unsigned, forged, replayed, expired, revoked, cross-scope, conflicted, or
   incompletely retained evidence;
4. preserve `adopt`, `adapt`, `reject`, `defer`, and `abstain` without treating non-permitting outcomes
   as approval;
5. emit only `awaiting-external-evidence` while no authentic evidence is supplied;
6. keep ADR-015 adoption, P14/P20 eligibility, release, production, deployment, promotion,
   superiority, authority, and activation false;
7. remain package-private and outside supported API, CLI, provider, scheduler, registry, store, and
   runtime selection; and
8. stop at the external human handoff rather than creating identities, signatures, decisions, or
   retention evidence inside the procedural session.
