# Courtroom and Source Docket

## Purpose

The courtroom prevents source omission, unsupported synthesis, self-approval, and marketing claims from becoming architecture.

## Source record

Every source must include:

- source ID
- title
- URI or user-supplied identifier
- kind
- status: `VERIFIED`, `PARTIAL`, or `PENDING_INGESTION`
- version, commit SHA, or digest
- license when applicable
- provenance completeness
- whether complete ingestion is required

An unavailable source is retained as a blocking obligation. Its content must not be invented.

## Atomic claim

Every claim includes:

- claim ID
- case ID
- one proposition
- source IDs
- category
- burden of proof
- architecture references
- acceptance tests
- outcome metrics
- code/test/benchmark receipts
- implementation state

## Evidence

**Stance**
- `SUPPORTS`
- `OPPOSES`
- `CONTEXT`

**Strength**
- `ASSERTION`
- `DOCUMENTED`
- `REPRODUCED`
- `EMPIRICAL`

Non-independent evidence is discounted.

## Burdens of proof

- `CAPTURE` — preserve an idea or unknown source.
- `DESIGN` — sufficient to shape architecture.
- `IMPLEMENT` — architecture mapping and acceptance tests required.
- `PROMOTE` — code, test receipts, outcome metrics, and independent evaluation required.
- `SUPERIORITY` — multiple independent comparators and reproducible benchmarks required.

## Verdicts

- `ADOPT` — burden satisfied without unresolved obligations.
- `ADAPT` — useful mechanism accepted with explicit controls or obligations.
- `DEFER` — evidence, ingestion, architecture mapping, tests, or adversarial review is incomplete.
- `REJECT` — evidence fails the burden.
- `QUARANTINE` — prohibited or deceptive behavior is involved.

## Simulated court procedure

1. **Clerk:** register source and chain of custody.
2. **Explorer:** extract atomic claims.
3. **Advocate:** strongest support case.
4. **Cross-Examiner:** opposing evidence, hidden assumptions, security, cost, licensing, failure modes.
5. **Experts:** product, architecture, security/SRE, data/ML, UX, legal/license, economics as applicable.
6. **Judge:** apply burden and issue verdict.
7. **Mapping:** adopted/adapted claims receive architecture, test, metric, rollback, and owner.
8. **Appeal:** reopen only with materially new evidence.

## Court output template

```yaml
case_id:
claim_id:
proposition:
sources:
burden:
advocate:
cross_examination:
expert_findings:
supporting_exhibits:
opposing_exhibits:
unresolved_objections:
prohibited_findings:
verdict:
score_or_confidence:
obligations:
architecture_mapping:
acceptance_tests:
outcome_metrics:
```

## Docket audit

The source inventory is incomplete when:
- a source has no claim;
- a claim has no decision;
- a claim references an unknown source;
- a decision references an unknown claim.

Release is blocked when:
- source provenance/ingestion is incomplete;
- adopted claims lack architecture or acceptance tests;
- implemented claims lack code/test receipts;
- superiority claims lack comparator and benchmark receipts.
