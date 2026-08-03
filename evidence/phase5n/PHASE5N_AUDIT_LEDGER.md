# Phase 5N audit ledger

## Entry 1 — source preservation

- Clerk: Phase5N-Ancestry-Clerk
- Source repository: `https://github.com/kb4beast/hive-mind-os`
- Subject: `ebe5884e30f62834ca649b72495e0178280ec3b3`
- Retrieval time: `2026-08-03T00:34:00Z`
- License: MIT
- Pull requests: #49, #52, #53, #54, #55, #56, #57, and #58, each preserved with URL,
  merge commit, and merge tree in the machine-readable index.

## Entry 2 — adversarial review

- Advocate: Phase5N-Ancestry-Advocate
- Cross-Examiner: Phase5N-Ancestry-CrossExaminer
- Expert Witness: Phase5N-Git-Packaging-Witness
- Finding: working-tree hashes alone cannot establish introduction ancestry, PR integration, or
  package equality. Git metadata alone cannot prove wheel bytes. The adapted design binds both and
  rejects shallow history, ancestry substitution, digest drift, and installed-package drift.

## Entry 3 — local receipt

- Builder: Phase5N-Ancestry-Builder
- Curator: Phase5N-Ancestry-Curator
- Index:
  `sha256:2b029c1f7c39b3b248b5b9e3e6a6a91ca46b93be01583e6a4c3760f427df2f9f`
- Tests: six Phase 5N tests plus thirteen Phase 5M regression tests passed.
- Static/type: Ruff passed; Pyright 1.1.411 reported zero findings.
- Wheel: eight roles and 16 files matched Git subject; local wheel digest
  `sha256:c780fd01c5b2c3d67b8148000006f38de88cdbb693ae697b18856a22c8724f41`.
- Limit: `P5H-DEBT-01` remains active pending exact-head hosted evidence.

## Entry 4 — hosted closure receipt

- Subject: `a78fcdd3418565565aa82ae127957632e5ac08d8`
- Push run: `30775103987`, fully successful
- Pull-request run: `30775114316`, fully successful
- Verified: all Python matrices, Ruff, Pyright, build/SBOM, CodeQL, secrets, dependency review,
  Phase 5A–K installed contracts, Git ancestry index, isolated-wheel byte equality, artifact upload,
  and push attestation.
- Judge: Phase5N-Ancestry-Judge
- Disposition: close only `P5H-DEBT-01`; retain six internal and eleven external-input debts.
- Reconciliation:
  `sha256:dc6ee7ca0986d0cefe9df98a61bdcd8eea8a7985b3b725b27e0b7c564bfb04e4`
