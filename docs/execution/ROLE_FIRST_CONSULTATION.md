# Role-First Resolution and Anti-Cheating Contract

## Required behavior

Before a worker or product runtime asks a human a question, it must classify the missing input.

| Class | Required response | Human permitted? |
|---|---|---|
| role-resolvable ambiguity | consult Architect/Explorer/Orchestrator and decide with evidence | no |
| missing repository evidence | create Explorer evidence work | no |
| software defect or failing control | create repair/remand work | no |
| missing test or acceptance mechanism | Architect + Curator define executable proof | no |
| suspected cheating | Curator + Cross-Examiner + Judge consultation | no, unless true authority also exists |
| tool/provider failure | Steward recovery, failover, retry, or quarantine | no |
| credential or secret | produce bounded human escalation packet | yes |
| legal/regulatory signoff | produce bounded human escalation packet | yes |
| financial spend | produce bounded human escalation packet | yes |
| production access | produce bounded human escalation packet | yes |
| protected branch merge | produce bounded human escalation packet | yes |
| owner value choice | present evidence-backed alternatives and explicit decision | yes |
| personal consent | request explicit consent | yes |
| external contractual commitment | request authorized signoff | yes |

## Typed consultation

A consultation binds the mission, question, reason code, requesting role, consulted roles, round,
evidence references, cheating concern, answer, dissent, decision, authority class, and whether
role-first resolution was exhausted. Maximum rounds default to three. Repeated friendly answers,
missing adverse evidence, circular referrals, or same-role self-confirmation cannot resolve it.

Allowed decisions:

- `RESOLVED`
- `REMAND`
- `REPLAN`
- `BLOCKED_EVIDENCE`
- `TRUE_AUTHORITY_REQUIRED`
- `QUARANTINE`

## Cheating definition

A concern is mandatory when work attempts or appears to attempt:

- acceptance/test weakening, replacement, concealment, or premature access;
- evaluator, holdout, target, or future-commit leakage;
- self-grading or self-promotion presented as independent;
- fabricated, stale, mismatched, selectively omitted, or non-reproducible evidence;
- authority expansion, credential misuse, protected-branch mutation, merge, deployment, spend,
  policy mutation, or concealment outside a grant;
- metric gaming, benchmark overfitting, friendly-reviewer selection, or consultation theater;
- concealment of dissent, adverse tests, failed attempts, open risks, or rollback gaps.

Disposition is `CONFIRMED`, `DISPROVED`, `UNRESOLVED`, or `NOT_APPLICABLE`. Confirmed cheating
quarantines work. Unresolved cheating cannot become ordinary success. Disproof requires retained,
independently inspectable evidence.
