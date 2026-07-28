# P12 — Source Ingestion Pipeline and Resolution of Open Evidence Obligations

Status: tracked in `00_OVERVIEW.md` | Depends on: P01 | Unlocks: unblocking machine-blocked claims

## 1. Objective

Build the executable ingestion path for external source evidence — raw-byte exhibits with
digests, exact locators, retrieval context, and license records — then use it to resolve
or formally defer every open source obligation in `docs/plan/BLOCKERS.md`: the seven
incomplete video sources, unresolved licenses and external pins, and the sibling-pack
chain-of-custody questions. Machine-blocked claims become unblocked only through captured
evidence plus courtroom re-adjudication; obligations that cannot be satisfied get explicit
`defer` verdicts with review dates instead of remaining open-ended rot.

## 2. Rationale

The docket is inventory-complete but not source-complete, and has been for the project's
entire life. The blockers cannot be closed by more audit hardening — they need an actual
capture pipeline and actual decisions. This phase treats ingestion as capture-burden work
(per the courtroom burden table): a human may supply files (transcripts, license texts);
agents validate, digest, register, and adjudicate — and are constitutionally forbidden
from inventing unavailable content. The deliverable is not just code: it is the docket
moving, additively, to a state where every source is either evidenced or explicitly
deferred by verdict.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md` and `docs/plan/BLOCKERS.md`
2. `src/hive_mind_os/source_docket.py` and `src/hive_mind_os/founding_docket.py`
   (docket structures, completeness audit)
3. `src/hive_mind_os/governed_sources.py` and `src/hive_mind_os/sibling_gpt_docket.py`
   (how the sibling pack was registered — the pattern for governed additions)
4. `src/hive_mind_os/additional_video_docket.py` and
   `docs/architecture/ADDITIONAL_VIDEO_DOCKET.md` (the seven video obligations)
5. `src/hive_mind_os/courtroom.py` (verdicts, appeals)
6. `src/hive_mind_os/schemas/source.schema.json` and `claim.schema.json`
7. `docs/architecture/ADR-004-STAGE-0-TRUTH-CONTRACTS-AND-SOURCE-GOVERNANCE.md` and
   `ADR-005-STAGE-0-FAIL-CLOSED-APPEAL.md` (source-blocker derivation rules the audit
   enforces — your changes must satisfy them, not fight them)
8. `evidence/sources/` layout (existing exhibits, e.g. `SRC-023-classic-gpt-pack/`)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_source_docket.py tests/test_governed_sources.py tests/test_courtroom.py   # pass
grep -E '^\| B-SRC' docs/plan/BLOCKERS.md | grep -c '| open |'    # >0 — there is work to do
```

## 5. Scope

In scope:

- `ingestion.py`: exhibit capture (bytes → content-addressed storage under
  `evidence/sources/<SRC-ID>/`), locator/retrieval-context records, license records,
  digest verification, and additive docket reconciliation hooks.
- CLI `hive-mind ingest` for human-supplied files (transcripts, license texts, image
  provenance statements).
- Courtroom re-adjudication path: captured evidence → claim unblocking via verdict;
  uncapturable evidence → formal `defer` verdict with review-by date.
- Working every open source row in `BLOCKERS.md` to `resolved` or `deferred`.

Non-goals:

- No automated video/transcript downloading (network fetching of third-party content has
  licensing and reliability problems; the human supplies files, the system governs
  them — record this division openly). No new audit schema. No relaxation of
  source-blocker derivation. No forging of retrieval timestamps — capture time is
  capture time, and the record distinguishes "content retrieved" from "content
  originally published".

## 6. Design constraints

- **Additive only.** Docket counts move monotonically; existing sources/claims/verdicts
  are never edited or deleted. New evidence attaches to existing SRC IDs as exhibits;
  status transitions (e.g. `pending ingestion` → `verified`) happen through the
  registered reconciliation path so the current-state audit derives blockers correctly
  (ADR-005 rules).
- **Exhibit record.** Each exhibit stores: raw bytes (content-addressed filename =
  SHA-256), original filename, media type, byte count, capture time (RFC 3339), capturer
  identity, supply method (`human-provided-file`, `agent-derived` — derived artifacts
  like extracted text must reference their parent exhibit digest), exact locator (URL +
  any timestamp/fragment), and license field (`SPDX id`, `unknown`, or
  `unresolved-pending-review` — `unknown` keeps dependent claims blocked, per existing
  rules).
- **No invention.** The pipeline validates that a supplied "transcript for SRC-005"
  cannot silently unblock claims by itself: unblocking requires (a) the exhibit, and
  (b) a courtroom verdict referencing it, issued under distinct court identities per
  `courtroom.py`. A missing verdict leaves the claim blocked with the exhibit attached.
- **Defer is a verdict, not a shrug.** For an obligation judged uncapturable now (e.g. a
  video is gone, a license owner unreachable), record a `defer` verdict with rationale
  and a `review_by` date; update `BLOCKERS.md` to `deferred (review by YYYY-MM-DD)`.
  Dependent claims stay machine-blocked — the difference is the decision is recorded and
  scheduled instead of implicit.
- **License review.** For each unresolved license: capture the license text/URL as an
  exhibit where obtainable; record the SPDX identifier; claims depending on
  incompatible/unknown licenses remain blocked (existing behavior) — the win is turning
  "unresolved" into "resolved: X" or "deferred with date".
- **Human/agent division on this phase itself.** The executor LLM builds the pipeline
  and adjudication records; where an obligation needs materials only the maintainer can
  supply (e.g. downloading a transcript with their account, confirming image authorship),
  the executor prepares the exact request list in the completion record and marks those
  rows `deferred` pending supply. Do not stall the phase on human latency.

## 7. Deliverables

New files:

- `src/hive_mind_os/ingestion.py` — `SourceExhibit`, `ExhibitStore`, `LicenseRecord`,
  `register_exhibit()`, `adjudicate_with_exhibit()` (drives courtroom),
  `defer_obligation()`.
- `tests/test_ingestion.py`.
- `evidence/sources/<SRC-ID>/…` — real captured exhibits for every obligation where
  materials are obtainable in-phase.

Modified files:

- `src/hive_mind_os/cli.py` — `hive-mind ingest --source SRC-005 --file <path>
  --locator <url> --media-type … --license …` and `hive-mind defer --source SRC-005
  --reason … --review-by YYYY-MM-DD`.
- Docket modules — only through their additive registration paths (mirror how
  `sibling_gpt_docket.py` added SRC-023; if no general additive path exists for exhibit
  attachment, add one with tests rather than editing docket constants).
- `docs/plan/BLOCKERS.md` — every open source row moved to `resolved` or
  `deferred (review by …)` with evidence pointers.
- `docs/architecture/STAGE_0_STATUS.md` — additive note that ingestion is now
  executable and which obligations moved.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P12-source-ingestion`.
2. Implement `ExhibitStore` + `SourceExhibit` with digest/locator/license validation;
   unit-test against the schema (`validate_contract("source", …)` where applicable).
3. Implement the courtroom adjudication driver (`adjudicate_with_exhibit`) using
   distinct identities per `courtroom.py`'s requirements; test unblock and
   still-blocked paths.
4. Implement `defer_obligation()` with verdict + review date.
5. CLI subcommands.
6. Work the backlog: for each open source row, either capture (if materials are
   obtainable — e.g. license texts of already-pinned public repos are typically
   obtainable) or defer with a dated verdict. Update `BLOCKERS.md` row by row with
   evidence pointers.
7. Re-run the audit; confirm blocker derivation reflects the new exhibit/verdict state
   correctly and no conservation rule is violated.
8. Gates; audit `evidence/audits/P12-post.json`; status updates; completion record
   (including the maintainer request list for human-only materials).

## 9. Required tests

`tests/test_ingestion.py`:

1. Exhibit registration: bytes stored content-addressed; record validates; digest
   mismatch on re-read fails closed.
2. Derived artifact (extracted text) must reference a parent exhibit; orphan derived
   artifacts rejected.
3. Unblocking requires exhibit + verdict: exhibit alone leaves the claim blocked;
   verdict without exhibit is rejected; both together unblock through the audit's
   derivation.
4. Court identity separation enforced on the adjudication driver (same identity for
   advocate and judge → rejected).
5. `defer_obligation` writes a verdict with review date; dependent claims remain
   blocked; `BLOCKERS.md` state is the caller's job (test the record, not the doc).
6. License `unknown` continues to block; a resolved SPDX license with exhibit lifts the
   license-derived blocker for its source (through existing derivation, not a new
   bypass).
7. Additivity: docket source/claim counts never decrease across any operation
   (property-style test over the operations exercised above).
8. Fabrication resistance: an exhibit whose claimed digest ≠ actual bytes is rejected
   and ledgered.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_ingestion.py    # pass
python -m pytest -q && python -m ruff check src tests && pyright   # clean
grep -E '^\| B-SRC' docs/plan/BLOCKERS.md | grep -c '| open |'   # 0 — every source-evidence row resolved or deferred (B-GOV/B-OPS rows may remain open with their target phase noted)
hive-mind audit --output evidence/audits/P12-post.json   # blocker set reflects new exhibits/verdicts; no conservation failure
```

## 11. Evidence

- Captured exhibits under `evidence/sources/` committed (or listed as deferred with
  dated verdicts).
- `evidence/audits/P12-post.json` committed; completion record includes the before/after
  blocked-claim counts and the maintainer request list.

## 12. Rollback

Revert the branch's code; captured exhibits and verdicts are append-only evidence — if
the pipeline is reverted, exhibits remain as recorded history (supersede, never delete).

## 13. Handoff

Later phases may assume: an executable, tested ingestion path for any future source;
every historical source obligation is either evidenced or has a dated defer verdict;
`BLOCKERS.md` contains no undated open source rows; the docket remains conservation-clean
under the audit.

## 14. Forbidden shortcuts

- Never synthesize transcript/content for an unavailable source — not even "obviously
  correct" summaries. Absence is recorded, not filled.
- No editing docket constants in place; additive registration paths only.
- No unblocking without both exhibit and verdict.
- No backdated capture times.

---
## Completion record
- Date (UTC): 2026-07-28
- Executor (model/agent identity): Codex Builder for P12
- Branch and final commit SHA: `phase/P12-source-ingestion` at
  `522adedecca16589df017f409ce733674de90ec0` (audited immutable implementation commit;
  the audit/status follow-up commit containing this record is reported in the PR)
- Gates: pytest pass (275 passed, 2 pre-existing skips, 1,718 subtests), Ruff pass,
  Pyright pass via `python -m pyright` (`pyright` console executable was unavailable)
- Audit artifact: `evidence/audits/P12-post.json` (digest:
  `sha256:b1d138cb8591c8a73340dd9e30d808492d6aca46b2a41ac803aac0b78bb05463`)
- Deviations from the phase spec: none
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none
- Machine-blocked claims before/after: 73 / 73. No source evidence was invented or
  promoted; all unavailable obligations received dated defer verdicts.
- Maintainer evidence request list:
  1. Supply complete timestamped transcripts or equivalent primary artifacts, original
     media custody, and authoritative reuse terms for `SRC-005`, `SRC-006`, and
     `SRC-016` through `SRC-020`.
  2. Supply authoritative versioned license texts or explicit reuse grants for the 17
     sources enumerated by `B-SRC-08`, together with the identity of an independent
     licensing reviewer.
  3. Identify and provide independently retrievable intended historical commit objects
     for `SRC-009`, `SRC-010`, `SRC-011`, `SRC-014`, and `SRC-015`; current remote heads
     do not prove the intended historical references.
  4. Supply the original raw bytes and custody statements for `SRC-001`, `SRC-002`,
     `SRC-013`, and `SRC-022`.
  5. Supply the `SRC-023` author/custodian attestation, explicit reuse terms, and
     independently reviewable origin and chain-of-custody evidence for `imgo.jpg`.

## CI appeal — constitutional test discovery

- GitHub's six unit-test jobs for exact candidate
  `db810cb4e79ad296e22a89d0056c3db2175ca245` failed while the other checks passed.
  The repository installs the package without development dependencies and runs
  `python -m unittest discover`; `tests/test_ingestion.py` imported unavailable
  `pytest`. Merely removing that import would have silently skipped its function-style
  tests under the constitutional runner.
- Repair commit `8287c2c075ce45221b8ad6e1f6ca6e4940ead5a6` converts the complete ingestion suite
  into discoverable `unittest.TestCase` methods while retaining pytest compatibility.
  No product code, source docket, captured exhibit, verdict, blocker disposition,
  license record, or audit schema changed.
- The repaired boundary gate passed: 277 standard-library tests with 2 skips, the 10
  ingestion tests under pytest, Ruff, and Pyright 1.1.411. Fresh audit
  `evidence/audits/P12-post-ci-repair.json` is complete with no failures, reports 275
  pytest tests passed, binds implementation commit
  `8287c2c075ce45221b8ad6e1f6ca6e4940ead5a6`, and has canonical digest
  `sha256:34ea62a2c077e58a19cadb2483c9dd2308363410214f6bd66ab0f203075f2f3e`.
- The machine-blocked claim count and maintainer evidence requests in the original
  completion record remain unchanged. This CI appeal does not claim source
  completeness, release readiness, or resolution of any licensing obligation.

## Post-review appeal — license promotion integrity

- The consolidated review of exact candidate
  `3ca672dc4fb5c1515d8a1414727701ec3fa46a22` confirmed the CI repair, but the Curator
  and Judge independently reproduced licensing fail-open paths. An `unknown` exhibit
  could be projected as MIT through an unbound override; the syntactically plausible
  non-SPDX token `banana` was accepted; and `AGPL-3.0-only` cleared the machine block
  despite the phase's fail-closed reuse requirement.
- Repair commit `6c7ebd082497ea38004a1ab669d78530eca1de6e` restricts accepted identifiers to a
  fail-closed pinned subset of SPDX License List 3.28.0, rejects unsupported tokens,
  binds any projected `license_spdx` to the admitted exhibit metadata, and promotes
  only the local reuse-policy set (`MIT`, `Apache-2.0`). `AGPL-3.0-only` is recognized
  but remains unresolved for this policy and therefore blocked. This compatibility set
  is a Hive Mind OS policy decision, not an SPDX compatibility claim.
- External reference record: SPDX `license-list-data` tag `v3.28.0`,
  `https://github.com/spdx/license-list-data/blob/v3.28.0/json/licenses.json`,
  retrieved 2026-07-28; repository license `CC0-1.0`. No external code or license text
  was copied.
- End-to-end regressions cover the unknown-to-MIT override, `banana`, and
  `AGPL-3.0-only`. The repaired boundary gate passed: 278 standard-library tests with
  2 skips, 11 ingestion tests under pytest, Ruff, and Pyright 1.1.411.
- Fresh audit `evidence/audits/P12-post-license-appeal.json` is complete with no
  failures, reports 276 pytest tests passed, binds implementation commit
  `6c7ebd082497ea38004a1ab669d78530eca1de6e`, and has canonical digest
  `sha256:0750b69136575d103bf8ec03cec263cf387071e04b5de7c204011137e167fd7f`.
- No source exhibit, docket entry, deferral verdict, blocker row, or audit schema
  changed. The 73 machine-blocked claims and all maintainer evidence requests remain.
  A fresh independent exact-candidate review remains required.
