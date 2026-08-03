# Phase 5M — chained evidence inventories and installed-wheel verification

- **Subject base:** `8ca34497051a9b50927f3615df49506f79d0046e`
- **Target branch:** `release/version_1.1`
- **Originating debt:** `P5E-DEBT-02`, `P5F-DEBT-02`, `P5G-DEBT-02`,
  `P5H-DEBT-02`, `P5I-DEBT-02`, and `P5J-DEBT-02`
- **Status:** exact successor head validated; closure recorded additively in Phase 5M
- **Authority:** none

## Outcome

Phase 5M adds one deterministic inventory chain from the validated Phase 5D Curator artifact through
the current Phase 5K external-evidence intake. Each link records the preceding path and verified
inventory digest, reproduces its example request and envelope through the component's own
validators, checks canonical output digests, seals the relevant implementation paths, and records
explicit non-authority boundaries.

The permanent build-evidence job now builds the wheel, installs it into an isolated directory, and
uses `scripts/verify_phase5e_to_k_installed_wheel.py` to verify that the Phase 5E–5K implementation
and contract modules import from that directory. It then reproduces every contract and checks the
same fail-closed authority, execution, eligibility, release, deployment, and promotion boundaries.
The resulting JSON receipt is uploaded and attested with the existing wheel evidence.

## Acceptance criteria

1. The committed Phase 5D inventory must validate before any successor inventory is built.
2. Exactly seven ordered Phase 5E–5K records must be deterministic and digest-bound to their
   predecessor.
3. Every component request and envelope must pass its own current contract validators.
4. Every canonical output digest and phase-specific non-authority boundary must reproduce.
5. Tampering with a predecessor or current record must be detected.
6. The installed-wheel verifier must import both implementation and contract modules only from the
   isolated wheel directory.
7. Permanent CI must retain the verifier receipt and fail when it is missing or invalid.
8. Ruff, Pyright, the focused Phase 5E–5K suite, and both exact-head hosted workflows must pass.
9. `main` and PR #48 must remain unchanged.

## Local evidence

- deterministic inventory tail:
  `sha256:4efbbe2e70e2d000fedde4dbf425df8ed5e7a6986778c8d52f0d3faf254d5ef8`;
- 80 Phase 5E–5K inventory and contract tests passed;
- Ruff passed on the new scripts and tests;
- Pyright 1.1.411 reported zero findings;
- isolated wheel `hive_mind_os-0.6.0-py3-none-any.whl` built with local digest
  `sha256:19b27f7688f7e523a099e93b3c55ac1fb2157a0b4145e4691619cce2bae6b75e`;
- the isolated installed-wheel verifier reproduced all seven phases and 55 explicit boundary
  assertions.

These receipts establish local implementation behavior only. They do not close the six debts until
the exact committed head receives successful hosted push and pull-request runs.

Initial exact-head runs `30773938617` and `30773951801` are retained failures. Python 3.11 and 3.14
correctly detected that the new permanent CI step changed the workflow digest sealed by the older
Phase 5A–5C inventories. The successor regenerates the complete Phase 5A–5K chain and updates each
hard-coded A→D predecessor digest; those initial runs are not closure evidence.

Successor `da90b4430f8cb99113b58657db7539600e753395` passed exact push run `30774229678`
and pull-request run `30774230905`. The additive closure record is
`docs/plan/PHASE5M_DEBT_RECONCILIATION.md`; Phase 5L is not rewritten.

## Threats and rollback

- **Source-tree import contamination:** each imported implementation and contract path must be
  relative to the supplied installed root.
- **Digest substitution:** every inventory recomputes its own digest and binds the verified prior
  digest; tests mutate the predecessor and current bodies.
- **Schema drift:** output order and every output digest are checked after official validation.
- **Authority inflation:** phase-specific boundary assertions fail closed; the receipt continues to
  state that release, production, deployment, promotion, independence, and superiority are false.
- **Rollback:** revert the Phase 5M merge commit. The prior permanent verifier then ends at Phase 5D,
  and all six inventory debts return to active without changing historical evidence.

## Preserved blockers

`B-OPS-08` remains active on Windows. ADR-015 remains proposed. Authenticated external identities,
signatures, trust anchors, retention, provider authority, P14/P20 eligibility, release readiness,
production readiness, deployment, promotion, and superiority remain unavailable.
