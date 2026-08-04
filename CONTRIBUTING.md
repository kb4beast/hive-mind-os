# Contributing to Hive Mind OS

Thanks for helping make Hive Mind OS easier to use and trust. This guide gives every
contributor one clear path from a small correction to a reviewed pull request.

## The contribution path

1. Fork the repository, create a focused branch, and make one coherent change.
2. Classify the change using the tiers below. When in doubt, use the governed tier.
3. Run the smallest relevant check. For a docs or typo-only change, inspect the rendered
   Markdown and verify any changed links; explain any check you did not run.
4. Open a pull request using the template and state its tier and validation.
5. Resolve review comments. A pull request to `main` needs **one approving review**.
   Code-owner review remains required, so the maintainer's single approval satisfies both
   requirements for an outside contributor.
6. A maintainer merges the approved pull request. Contributors do not need merge access.

## Governance-lite

Use the **governance-lite** tier only for a low-risk, documentation-only correction:

- spelling, grammar, formatting, or broken-link fixes;
- clarifying text that does not change a product, security, or performance claim; or
- a documentation example correction that does not change executable behavior or an
  acceptance criterion.

A governance-lite pull request needs the focused validation described above and one
maintainer approval. It does **not** need a courtroom disposition, evidence from all
eight specialist roles, or an architecture decision record.

## Governed changes

All other changes use the governed tier and follow the evidence, review, and delivery
requirements in [AGENTS.md](AGENTS.md). The following are always governed and cannot use
governance-lite:

- the operating kernel or runtime behavior, including `src/hive_mind_os/`;
- policy, authority, security controls, budgets, or acceptance criteria;
- the courtroom, source docket, provenance, evidence, or benchmark records;
- schemas, public contracts, architecture decisions, dependencies, releases, and CI or
  repository automation; and
- `AGENTS.md`, `docs/architecture/`, `evidence/`, and `.github/`.

These exclusions are intentional: the lighter path makes a typo fix practical without
weakening the burden of proof for the kernel, policy, courtroom, or schemas.

## Practical expectations

- Keep pull requests small and describe the user-visible result.
- Do not commit credentials, private data, generated build artifacts, or changes unrelated
  to the pull request.
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md) and report vulnerabilities through the
  [security policy](SECURITY.md), not a public issue.
