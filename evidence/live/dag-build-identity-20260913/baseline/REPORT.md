# Build identity expectations: executable baseline reproduction

Independent reviewer: `/root/delivery_curator`. Status: **reproduced**. Subject commit `b19b2a177e2d10ebf49b565dcdd1ad9878bbaeac`, tree `6fb9b59c4c697ae9b9bc296676783f8ce662f3c0`. This qualifies the selected local defect `PUBLIC-RUNTIME-500-EXPECTED-IDENTITY-BUILD-001`, not a node-completion or authority claim.

The CLI accepts a wrong expected request ID or subject ID and returns exit 0 while writing the canonical plan. Each mismatch reproduced independently with an absent output and with `--replace` over existing sentinel bytes: **four unintended successful writes**. The valid expected plan digest remained enforced; these probes concern additional caller identity constraints that build silently drops.

Fifteen deterministic probes completed under Python 3.14. Source was extracted with `git archive` from the immutable baseline into this external evidence directory; the builder worktree was untouched. No source edits, runtime execution, authentication, activation, dispatcher, or full test suite occurred.

| Boundary and condition | Cases | Observed result |
|---|---:|---|
| CLI build, wrong request/subject, absent/existing output | 4 | Exit 0; canonical plan created or sentinel replaced |
| CLI validate, same wrong request/subject | 2 | Exit 2; typed blocked response |
| Service validate, same wrong request/subject | 2 | ContractViolation |
| Service build, expectation keyword, absent/existing output | 4 | TypeError; output unchanged |
| Service build, omitted expectations, absent/existing output | 2 | Canonical plan created/replaced |
| CLI build, both matching expectations | 1 | Exit 0; canonical plan created |

The direct service does **not** silently accept mismatches: its baseline signature lacks both expectation keywords, so Python rejects them. The silent loss occurs in the CLI forwarding call. Adding optional keywords to the service and forwarding them to the existing validator is therefore necessary to close the public CLI defect without duplicating identity logic.

No leftover temporary output files were found. All 252 extracted source/fixture files retained their original bytes after the probes. `RESULTS.json` contains the exact commands, environment path, exit codes, complete normalized text stdout/stderr and their UTF-8 hashes, before/after output hashes, exceptions, fixture identities, and per-file byte counts/SHA-256/Git blob IDs. `MANIFEST.json` independently checks those IDs against the pinned Git tree and binds the reproduction artifacts.

Reproduction command used:

```powershell
python -B C:\h\node-completeness-audit\baseline-reproduction\reproduce.py
```

Portable rerun (requires Python 3.11+ and a local repository containing the exact pin; choose a fresh external output directory):

```powershell
python -B reproduce.py --repo C:\path\to\repository --output C:\path\to\fresh-evidence
```

The script extracts its own exact source and fixture helpers; it does not import the candidate or depend on installed product code. Fixture text is inert input, never an execution directive.

The first harness extraction attempt stopped before any product probe because it assumed nonexistent `tests/__init__.py`; `SETUP-ATTEMPT-1.txt` preserves the failure and correction. The successful run used the actual namespace package fixture files.

Bounded risk: the dropped constraint can publish or replace a local output selected by the caller even though the requested identity does not match. This does not demonstrate authentication bypass, activation, runtime authority, adversarial filesystem custody, or universal node completion. No additional material defect was established by these focused probes. Candidate verification should require each mismatched/malformed expectation to fail before any output mutation, preserve omitted/matching behavior, and retain existing publication-safety tests.
