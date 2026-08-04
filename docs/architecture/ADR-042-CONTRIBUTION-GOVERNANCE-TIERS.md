# ADR-042: Contribution governance tiers

- **Status:** Adopted
- **Date:** 2026-08-03
- **Scope:** public repository contributions

## Decision

The `main` branch requires one approving review and code-owner review while the project has
one maintainer. A code-owner's one approval satisfies both requirements for an outside
contributor. This is a temporary structural policy: it must be reconsidered when a second
maintainer can provide independent review.

The repository has two contribution tiers:

- **Governance-lite** permits only documentation-only typo, formatting, link, and
  non-substantive clarification fixes. These changes require focused validation and one
  maintainer approval, but not a courtroom disposition, evidence from all eight specialist
  roles, or an ADR.
- **Governed** applies to every other change. Kernel/runtime, policy, courtroom, schemas,
  source and evidence records, public contracts, architecture, security controls, and
  repository automation remain heavyweight. They retain the existing evidence and
  acceptance obligations.

When classification is uncertain, the governed tier applies.

## Rationale

Requiring two approvals plus an owner review from a one-maintainer project made an outside
contribution impossible to merge. A bounded light tier makes ordinary maintenance
contributions possible without changing the proof burden for safety-critical or
architecture-bearing changes.

## Threats and limits

One approval does not create independent review, and code-owner enforcement does not
prevent a maintainer with administrator bypass from overriding host rules. The light tier
must never be used to bypass a behavior, policy, courtroom, or schema change; reviewers
must reclassify such a pull request as governed.

## Verification

`tests/test_governance.py` checks the one-review declaration, the contributor materials,
and the explicit heavyweight exclusions. Host-side branch protection is configured to
require the same one approving review and code-owner review.

## Rollback

Set the declared and host-side required approval count back to two and revert this record
and the contribution guidance. Existing public contribution materials remain harmless
documentation if the tier is retired.
