# A5 — Governed-full autonomy readiness record

**Node:** A5-900 · **Status:** READINESS RECORD — adjudicated, gates closed
**Base commit:** `7a2e19e769cbeb1b3f3a515037c1173af28c9893` (release tip, tree clean)
**Court record:** [`evidence/pilots/a5/readiness-court.json`](../../evidence/pilots/a5/readiness-court.json)
**Court digest:** `sha256:26257ec5d9c94731a72f6ab51fc0ff73c9bac2b5ce678331b899b1d2ded3ad01`
**Gate matrix:** [`evidence/pilots/a5/gates/gate-matrix.json`](../../evidence/pilots/a5/gates/gate-matrix.json)
**Verdict:** `not-ready`

The court digest is `canonical_digest(readiness-court.json with only its own
`court_digest` field removed)` — the same convention `evidence/pilots/a4/pilot-plan.json`
was independently verified to seal under. This document is deliberately **not** one of
the court's digest-bound exhibits: it has to quote the digest, so digesting it here
would make the two files mutually self-referential and the regress would not terminate.
Its own sha256 is recorded in
[`summary.json`](../../evidence/pilots/a5/summary.json) `file_digests`, which nothing
digests. Same self-reference limit that makes `final_commit` null.

## 1. What this record is, and what it is not

A5 qualification means the **procedure and evidence** for governed-full autonomy are
proven. It never means autonomy is switched on. Nothing in this file, and nothing in
`evidence/pilots/a5/**`, grants any authority to anything.

Governed-full autonomy would mean an agent acting in production under standing
authority. Production authority, spending, legal commitments, and protected-branch
changes are genuine human and governance decisions, not questions a role can resolve.
Every one of them is a gate, and today every one of them is closed by the repository
owner's own recorded decisions.

This record therefore ends in an adjudication, not a celebration. Where a gate is
closed it stays closed and is escalated. Where a locally satisfiable weakness was
found it is written down, including the ones found in this node's own subject matter.

## 2. The single most important finding

**Every defect that mattered was invisible until something genuinely tried to use the
path end to end.**

A4-800 pointed the delivery surface at a real host for the first time and found six
production defects. Five were fixed (`b6ec6b7` close-own-pr and delete-own-branch were
mandated operations with no implementation anywhere; `a6865fb` `PushExecutor` had no
production implementation at all; `f578426` the sandbox rejected every HTTPS remote, so
the governed surface physically could not reach github.com; `091e554` an overridden
signature silently disabled branch quarantine in healing; `5177d4c` there was no lawful
way back from a resolved escalation). The local test suite was green the entire time.

A5 then pointed a probe at the authority objects for the first time and found four
more (§6). The authority and governance regressions are green — nine tests, exit 0 —
and the boundary is still open, because no existing test constructs a second root
envelope or checks that an envelope digest seals its contents.

Then the same pattern caught this record. Two blind reviewers, given adversarial check
lists and none of the author's conclusions, both returned **FAIL** — and one of them
found that the first authority audit had looked one layer too high. It had audited the
`AuthorityRegistry` and never tested the *effect* boundary, which turns out not to
consult the registry at all (**A5-F10**, §6). A hand-built capability token that no
registry ever issued, naming a target the registered envelope had just refused, was
accepted and executed with `status=SUCCEEDED`. That is the strongest single piece of
evidence in this node, and the author did not find it.

The pattern is the finding. A green suite over fakes is evidence that the fakes agree
with the code. An audit that stops where the author expected the boundary to be is
evidence about the author's expectation. Neither is evidence that the boundary holds.
Read every "proven" in this document against that.

## 3. Gate matrix

Full rows, with authority citations and what would open each, are in
[`gates/gate-matrix.json`](../../evidence/pilots/a5/gates/gate-matrix.json).
`closed` means the gate blocks. `open` requires an authenticated external authority
record; agent reasoning never opens a row.

| Gate | Kind | Status | Authenticated | Authority |
|---|---|---|---|---|
| G1 branch fork resolution | owner_decision | **open** | no | HUMAN_AUTHORITY_GATES.md:32 — decided 2026-08-04; grants no authority |
| G2 first real model mission | financial_spend | **closed** | no | :33 "No real model API key, spend, or mission is authorized" |
| G3 external identity and signing | security | **closed** | no | :34 "No stable or production-positioned release until an externally controlled signing identity exists" |
| G4 external append-only retention | operational | **closed** | no | :35 "No external append-only evidence store is authorized" |
| G5 production pilot | production_access | **closed** | no | :36 "No production pilot is authorized" (restated :77–82) |
| G6 comparator access | external_contractual | **closed** | no | :37 read-only intake only; execution and court blocked |
| G7 founding-source licensing | legal_signoff | **closed** | no | :38 obligations remain non-promoting deferrals |
| G8 independent human review | security | **closed** | no | :39 no decision recorded; :21–23 agent separation is **not** human review |
| A4 delivery grant 2026-08-12 | owner_decision | **open** (spent) | no | :61–100 one repository, six operations, rolled back; authorizes nothing for A5 |
| B-GOV-02 authenticated identities | security | **closed** | no | BLOCKERS.md:53 open |
| B-GOV-03 provider mediation | security | **closed** | no | BLOCKERS.md:54 open |
| B-GOV-04 external retention | operational | **closed** | no | BLOCKERS.md:55 open |
| B-OPS-03 verified E2E delivery | operational | **closed** | no | BLOCKERS.md:60 open; the 2026-08-12 amendment says it does not close it (:80) |
| B-OPS-04 production operation | production_access | **closed** | no | BLOCKERS.md:61 open, `release_ready=false` |
| B-OPS-05 no superiority claims | external_contractual | **closed** | no | BLOCKERS.md:62 open |
| B-OPS-06 hard isolation | security | **closed** | no | BLOCKERS.md:63 open |
| B-SRC-01..11 source and licence | legal_signoff | **closed** | no | BLOCKERS.md:41–51 deferred under G7 |
| ESC legal_or_regulatory_signoff | legal_signoff | **closed** | no | no sign-off record exists anywhere in this repository |
| ESC production_access | production_access | **closed** | no | G5 + B-OPS-04 |
| ESC financial_spend | financial_spend | **closed** | no | G2 + :78 "No spend of any kind" |
| ESC protected_branch_merge | protected_branch_merge | **closed** | no | :77 "No merge"; `grants.py:29-31` excludes merge from the grantable vocabulary |
| ESC external_contractual_commitment | external_contractual | **closed** | no | G6 + G7 |

**22 rows. 20 closed. 2 open, and neither grants A5 any authority. 0 authenticated.**

### The weakest link in the authority chain

Measured, not asserted: `git log --format='%G?' -- docs/architecture/HUMAN_AUTHORITY_GATES.md`
over the file's complete history returns **four `N` (no signature) and one `E`
(a signature that cannot be verified on this host)**. Both 2026-08-12 grant commits —
`db34487` and `c78adf4`, author and committer Brian Espinosa — are unsigned.

"The owner said so" therefore rests on repository write access, not on a signature.
Anyone who can write to this repository can add a paragraph to the authority record
that reads exactly like an owner grant. That is B-GOV-02, and it is open. It is the
reason every row above says `authenticated: no`.

## 4. What was proven locally

### Recovery — [`exercises/recovery-exercise.json`](../../evidence/pilots/a5/exercises/recovery-exercise.json)

A fresh clone at a short path recovers this repository completely: exit 0, 940 tracked
files, none missing, `HEAD` and `HEAD^{tree}` identical to source, and
`evidence/pilots/a4/pilot-plan.json` re-hashing to
`324151468418014ed70c22162d2689d3ab7d9ac1770e80fc7ca4b228fc9a9fbc`, the digest of
record. Deleting the clone and re-cloning reproduced the identical bytes.

It also found something (finding **A5-F1**). A fresh clone at an ordinary temp path
(127 characters) with default git config **fails**: exit 128, `unable to checkout
working tree`, leaving a repository that reports all 940 tracked paths as staged
deletions. The longest tracked path is 169 characters and Windows MAX_PATH is 260
*including the terminating NUL*, so a default-config recovery of this repository needs
a destination of at most **89 characters** — measured directly: 88 → exit 0, 89 → exit
0, 90 → exit 128, 91 → exit 128. The remedy — `core.longpaths=true` — is set only in
this working copy's **local** `.git/config`, is not in global or system config, and is
measurably **not inherited** by a fresh clone. The one setting that makes this
repository recoverable lives in the exact artifact a disaster destroys, and nothing in
the repository tells a recovering operator about it.

The first version of this record published **90** here. That number was produced by
`echo`, filed under a key named `measured`, and was the first *failing* length rather
than the last working one. The blind operational reviewer caught it and measured the
correction. An unmeasured number filed as measured is exactly how an error survives
into a readiness record, and it survived into this one until someone adversarial read
it.

A deliberately altered **temp copy** of a retained artifact was rejected on digest
mismatch, and the retained original re-hashed byte-unchanged. That proves
tamper-*evidence*. It does not prove authenticity: the digest list is unkeyed, so a
party who can rewrite both the exhibit and the list can re-seal both. Same structural
limit as A3-700's finding F3.

### Stop — [`exercises/stop-mechanism.json`](../../evidence/pilots/a5/exercises/stop-mechanism.json)

A four-step receipt-ledgered procedure was stopped after step 2 (stop record written,
no further step issued), then hard-killed with `os._exit(9)` during step 3 *after its
effect and before its receipt*, then resumed twice. Result: exactly one receipt per
step, all four steps present, the pre-stop receipts byte-unchanged across both resumes,
and the second resume executed nothing at all.

The hard kill is deliberately the shape of A4's **open defect D1**. It was survivable
here only because the interrupted step was an idempotent local read. D1's version of
that window has an irreversible remote push in it, and it is unfixed (§6).

And the exercise proved less than its first title claimed (**A5-F8**). Every kill in it
was placed *before* the receipt append — the safe placement, which avoids the
interesting case. The blind operational reviewer placed one *inside* the append; the
resume died with an unhandled `JSONDecodeError`, exit 1, and the entire ledger —
including both intact earlier receipts — became unreadable. Re-measured here. "No lost
evidence" holds only for interruptions outside the write window. A second disclosure
was also missing (**A5-F9**): the stop is a flag the process reads at startup, not a
signal delivered to an unwilling process. Nothing here shows an operator can stop a
running agent.

## 5. What is gate-blocked, mapped rather than claimed

| Capability | Status | Gate that owns the production claim |
|---|---|---|
| Off-host / durable retention | not exercised | G4, B-GOV-04 |
| Production rollback | not exercised | G5, B-OPS-04 |
| Incident response (paging, rotation, containment) | **no such mechanism exists in this repository to exercise** | B-OPS-04 |
| Independently verified E2E delivery | partial via A4, not the exit condition | B-OPS-03 |
| Egress evidence for the A4 run | not proven — no socket guard was installed | B-GOV-03 |
| Containment of a governed-full agent | none | B-OPS-06 |
| Independent security and operational review | **impossible for any agent to satisfy** | G8 |

No production system, deployment target, external storage, or paid service was
contacted by this node. This node made no network call of any kind.

## 6. Defects carried into this record

Open at this base commit. Every line number below was re-measured here.

| ID | Severity | What | Where |
|---|---|---|---|
| D1 (A4) | high — can strand a completed irreversible effect | The effect receipt is written **after** the irreversible remote effect, through a temporary filename **longer** than the final name, with no Windows long-path handling; the resulting `reconciliation_required` state is terminal | `mission_store.py:81-92`, `brain_kernel/effect_outbox.py:91-93` |
| F3 (A3) | evidence-integrity | `verify_bundle` never reads `document['verdict']`; a bundle flipped from reject to adopt passes once `integrity.json` is recomputed. Retained bundles are tamper-evident, not authenticated | `verify.py:266-379` (verified here: `verdict` occurs at 58, 179, 185, 194, 250 — none inside that range) |
| D2 (A4) | medium | `find_open_draft_pr` interpolates branch and base into the query string with no percent-encoding | `rest_gateway.py:152-165` (interpolation at 156-158) |
| D3 (A4) | medium | `list_comments` requests `per_page=100` and never follows `Link`, so comment idempotency breaks past 100 comments | `rest_gateway.py:188-196` |
| D4 (A4) | medium | `DeliveryGrant` has `issued_at` and no expiry; grant lifetime lives outside the governance object | `grants.py:94-101` |
| D5 (A4) | medium | `EffectIntent.intent_digest` is format-checked, never recomputed to seal its fields | `contracts.py:527-535` |
| D6 (A4) | medium | The gateway has no ref-read method, which is why A4's own idempotency and rollback verdicts compared `None == None` | `cortex/github/rest_gateway.py` (no `refs/heads` reader) |
| D7 (A4) | evidence-chain | No remote receipt cites the sealed plan digest, and `pilot-plan.json` still reads `pilot_repository: "UNGRANTED"` because re-sealing after the fact would not be a seal | `evidence/pilots/a4/pilot-plan.json` |
| **A5-F1** | operational | Default-config recovery of this repository fails at an ordinary path; the remedy is recorded nowhere in the repository | §4 |
| **A5-F3** | security | `ConstraintEnvelope.digest_value` is format-checked, never recomputed from contents, and `AuthorityRegistry` keys on it — so two envelopes with different authority can share a digest and the later one silently overwrites the earlier | `brain_kernel/contracts.py:342`, `brain_kernel/authority.py:44`; both production sites use the all-zero placeholder (`cortex/repository/local_execution.py:31`, `cortex/repository/mission_adapter.py:35`) |
| **A5-F4** | security | A fresh **root** envelope with any authority registers unconditionally; the no-broadening rule only constrains a declared parent/child pair | `brain_kernel/authority.py:39-44` |
| **A5-F5** | security | Revocation is keyed by the digest string, so re-minting the same authority under a new digest defeats it | `brain_kernel/authority.py:46-47` |
| **A5-F6** | security | `DeliveryGrant` is self-issuable and its seal is unkeyed, so a grant cannot distinguish owner-issued from agent-issued. No production caller of `DeliveryGrant.issue` exists — only two test files | `cortex/github/grants.py:130-169` |
| **A5-F8** | operational | A crash *inside* the receipt-append window destroys the whole ledger; the stop exercise as first written never tested that placement | §4 |
| **A5-F9** | disclosure | The demonstrated stop is self-triggered by a startup flag, not a signal to an unwilling process | §4 |
| **A5-F10** | security — **highest impact** | The effect boundary never consults the `AuthorityRegistry`. `validate_capability_token` recomputes an unkeyed digest over the token's own three fields and compares them to the intent: no registry lookup, no envelope lookup, no expiry, no revocation, no scope. A hand-built token for a refused target was accepted and `EffectGateway.execute` ran the adapter, `status=SUCCEEDED` | `brain_kernel/effects.py:23-39`, `:100-101` |
| **A5-F11** | security | `authorize()` target-scopes only the `write` action; every other action gets an unscoped target. `path_read_scope` is enforced nowhere in `src/**` | `brain_kernel/authority.py:58`, `brain_kernel/contracts.py:310,333,354` |
| **A5-F12** | security (latent) | `is_no_broader_than` compares 4 fields and 3 of `Budget`'s 8, omitting `denied_actions`, `secret_scopes`, `human_gates` and **`max_cost_microunits`** — a child can raise its spend ceiling and still pass. Latent only because nothing spends against that ceiling today | `brain_kernel/contracts.py:352-360`, `:158-165` |
| **A5-F13** | security | `intersect_envelopes` trusts a caller-supplied parent object the registry has never seen | `brain_kernel/authority.py:39-41` |
| **A5-F14** | security (informational) | The kernel's declared `network_allowlist` is compared once and enforced nowhere | `brain_kernel/contracts.py:312,356` |
| **A5-F15** | process — **unresolved** | The candidate was never frozen while under review: across two rounds, three cited artifacts came into existence during the review that cited them. No verdict here should be treated as binding until re-verified against sealed bytes — an act this worker cannot perform | §7 criterion 1 |
| **A5-F16** | documentation | A second forward reference written as a completed fact (a credential-scan addendum cited before it existed). Resolved by producing it | §7 criterion 1 |

## 7. Acceptance criteria, adjudicated

**1. Independent security and operational reviews pass — NOT SATISFIABLE BY ANY AGENT.**
Two reviews were performed by separately prompted role identities with adversarial check
lists and no sight of the author's conclusions.

**Round 1: both returned FAIL.** Between them they found the missing effect-boundary
audit (A5-F10), four further authority defects (A5-F11 to A5-F14), an off-by-one in a
published recovery limit, an untested torn-write case (A5-F8), a missing stop disclosure
(A5-F9), an inoperative rollback command, and three citations to artifacts that did not
exist.

**Round 2: both returned PASS-with-findings**, after every correction was re-derived by
this node and then re-measured a third time by the reviewers themselves. Neither
withdrew a substantive objection, and each attached a standing finding — **A5-F15**, that
the candidate was never frozen while under review, and **A5-F16**, that a second forward
reference was written as a completed fact. Both dissents, both round-1 and round-2, are
recorded verbatim in
[`readiness-court.json`](../../evidence/pilots/a5/readiness-court.json).

None of this satisfies the criterion. Per `HUMAN_AUTHORITY_GATES.md:21-23` it is
procedural separation, **not** authenticated independent human review. G8 is closed and
no agent, including the author of this record, may claim this criterion. What the
process did accomplish is narrower and still worth stating: it found the strongest
finding in the node, which the author had missed, and it caught the author writing
completed facts about work not yet done — three times.

**2. Owner/legal/production gates explicit and authenticated — HALF MET.**
Explicit: yes, 22 rows with authority citations by line. Authenticated: **no** — zero
rows, for the reason measured in §3.

**3. Rollback, incident response, retention, stop proven — PARTIAL, HONESTLY BOUNDED.**
Local rollback, local recovery, digest-bound tamper evidence and the stop/resume path
were exercised and are reproducible. Off-host retention, production rollback and
incident response are gate-blocked and mapped to their rows in §5 rather than claimed.
There is no incident-response mechanism in this repository to exercise.

**4. No autonomous expansion of authority is possible — NOT MET AS WORDED.**
An expansion path exists and was executed in-process. The strongest measurement is
A5-F10: a capability token that no `AuthorityRegistry` ever issued, naming a target the
registered envelope had explicitly refused, was accepted by `validate_capability_token`
and executed by `EffectGateway.execute` with `status=SUCCEEDED`. That makes A5-F3,
A5-F4 and A5-F5 unnecessary work — an attacker need not mint an envelope at all — and
it means the registry's scopes, expiry, revocation and no-broadening rule are advisory
at the point where authority is actually spent. See
[`audits/authority-boundary.json`](../../evidence/pilots/a5/audits/authority-boundary.json)
and [`tests/authority-boundary-probe-2.txt`](../../evidence/pilots/a5/tests/authority-boundary-probe-2.txt).

What actually prevents expansion today is external: a credential scope the agent can
neither read nor widen, host-side branch protection, and the fact that provisioning is
a human act. Those held throughout A4-800. They are not the audited code boundary the
criterion asks for, and with B-OPS-06 open there is no containment tier underneath them
either — A5-F14 adds that the kernel's own network allowlist is inert as well.

## 8. How a human opens each gate

No agent can perform any act in this table. Each requires the named human.

| Gate | Who acts | What they produce | Where it is recorded |
|---|---|---|---|
| G2 / ESC financial_spend | Repository owner | An API key with an explicit spend limit, or a stated budget | `HUMAN_AUTHORITY_GATES.md` amendment, plus a live-session statement |
| G3 / B-GOV-02 | An external certificate or identity authority, installed by the owner | Non-agent-controlled signing credentials, revocable and non-self-issued | An ADR plus regression tests that refuse unsigned authority records |
| G4 / B-GOV-04 | Repository owner | A storage account and a named recovery authority | `HUMAN_AUTHORITY_GATES.md` amendment; then B-GOV-04's exit condition |
| G5 / B-OPS-04 / ESC production_access | Repository owner as deployment authority | Deployment account, approved scope, named users, rollback authority | `HUMAN_AUTHORITY_GATES.md` amendment; then bounded trials with independent receipts |
| G6 / B-OPS-05 | Whoever holds comparator licences | Licensing and access for benchmark comparators | ADR-043 successor plus a benchmark court verdict |
| G7 / B-SRC-01..11 | Source custodians and a licensing reviewer; B-SRC-11 names a human custodian | Per-source licence and reuse evidence | Per-source obligation records under `evidence/sources/_obligations/` |
| G8 | A second person, **or** the owner declaring this an explicit solo project | A signed review, or a recorded solo-project declaration | `HUMAN_AUTHORITY_GATES.md` G8 row, which currently reads "No decision recorded" |
| ESC protected_branch_merge | A human with merge authority | A merge performed under host-side protection | GitHub; no agent path exists by construction |
| ESC legal_or_regulatory_signoff | A human with legal authority | A sign-off artifact | Committed to the repository; no agent may author it |
| ESC external_contractual_commitment | A human able to bind the project | The signed commitment | Outside this repository |

The 2026-08-12 amendment is the template for how this is done well: it named the exact
credential, the exact repository, the exact six operations, and then said in terms what
it did **not** authorize. It is also the template for what is still missing — it is
unsigned.

## 9. Non-claims

- **No production readiness.** `BLOCKERS.md:61` — B-OPS-04 is open and records
  `release_ready=false`.
- **No release readiness.** G3: "No stable or production-positioned release until an
  externally controlled signing identity exists."
- **No superiority, and no comparative claim of any kind.** `BLOCKERS.md:62` — B-OPS-05
  is open: "No superiority statement is permitted"; "absent that verdict, superiority
  language remains prohibited."
- **No independent human review.** G8, per §7 criterion 1.
- **No verified end-to-end delivery.** B-OPS-03 is open and the amendment that
  authorized the A4 pilot states in terms that it does not close it.
- **No claim that governed-full autonomy is enabled, approvable, or imminent.** This
  document is a record of what would be required. It is not a request to grant it.

The operational reviewer's closing observation, adopted here without qualification:

> This node was asked to prove that no autonomous expansion of authority is possible,
> and it returned NOT MET AS WORDED against itself, having found and executed the
> expansion path. The gates hold today because a credential scope cannot be widened by
> the party using it, because branch protection lives on a host the agent does not
> control, and because provisioning is a human act. They do not hold because the code
> prevents it. Anyone reading this record as a step toward switching autonomy on has
> read it backwards.

## 10. Rollback of this node

This node is additive, uncommitted, and changes no runtime code, test, or
configuration. It writes only `docs/execution/A5_GOVERNED_FULL_READINESS.md` and
`evidence/pilots/a5/**`. Before the integrator commits:

```
rm -f  docs/execution/A5_GOVERNED_FULL_READINESS.md
rm -rf evidence/pilots/a5
```

After commit: `git revert` of the node commits. Sibling evidence under
`evidence/pilots/a3/**` and `evidence/pilots/a4/**` was read only and is byte-unchanged.

The first version of this section said
`git checkout -- docs/execution/A5_GOVERNED_FULL_READINESS.md 2>/dev/null`. The blind
security reviewer measured that this **does not work**: the file is untracked, so
`git checkout --` errors, `2>/dev/null` swallows the error, and the file survives the
rollback. A rollback recipe for half the write scope silently failed. It is corrected
above and recorded here rather than quietly replaced.
