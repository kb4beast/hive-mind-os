# Hive Mind OS — Canonical Implementation Plan

- **Plan version:** 1.0
- **Date established:** 2026-07-27
- **Status:** ACTIVE — this document owns implementation sequencing for the repository.

## 1. What this document is

This is the single authoritative roadmap for implementing Hive Mind OS, decomposed into
phases that any capable LLM coding agent can execute independently. Each phase lives in its
own self-contained file in this directory. An executor needs to read only:

1. this overview,
2. its assigned phase file, and
3. the files listed in that phase's "Required reading" section.

Nothing else is assumed. No prior conversation, no memory of other phases, no context beyond
the repository itself.

### Relationship to existing documents

The following documents remain **normative for architecture, invariants, and governance**,
but their sequencing sections are superseded by this plan:

| Document | Still normative for | Superseded section |
|---|---|---|
| `docs/architecture/HARDENED_VISION_CONTRACT.md` | Product constitution, roles, hard failure conditions | "Implementation sequence" |
| `docs/architecture/CONGLOMERATED_SYSTEM.md` | Target architecture, planes, definition of done | "Delivery sequence" |
| `docs/architecture/FOUNDATION_PLAN.md` | Product thesis, autonomy model, learning model | "Build phases", "Immediate next slices" |
| `docs/architecture/BOUNDED_EVOLUTION.md` | Evolution threat model and invariants | "Required next slices" |
| `docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md` | Mission behavior, threat model, adversarial tests | "Staged implementation plan" (order only; stage content remains valid reference material) |
| `AGENTS.md` | Non-negotiable rules for every contributor, human or LLM | — (fully in force) |

Where this plan and those documents disagree about **what to build or what is forbidden**,
those documents win and this plan must be corrected via ADR. Where they disagree about
**order**, this plan wins.

## 2. Why this sequencing

The repository's governance layer (courtroom, dockets, audit, receipts, schemas) reached
`structurally_prototyped` maturity while the capability layer (real model calls, real Git,
real sandboxed execution) remained at zero. Every contract has so far been exercised only by
the offline `DeterministicBackend`. This plan closes Stage 0 with an explicit exit (P01) and
then drives the shortest path to a real, evidence-complete delivery (P02–P05), because first
contact with real execution is the highest-information event available to the project: it
validates or falsifies the contract designs that further governance work would otherwise
build on untested.

Sequencing principles:

1. **Capability before further governance expansion.** Governance already exceeds
   capability; new governance work must be driven by counterexamples from real execution,
   not speculation.
2. **Every phase lands a working, tested, reviewable increment** — one PR-sized unit that
   passes all gates and the post-commit audit.
3. **Fail-closed is preserved at every step.** No phase weakens an existing gate, test,
   or invariant to make progress.
4. **The deterministic offline path always keeps working.** Real adapters are added beside
   it, never instead of it. CI never requires network access or secrets.

## 3. Phase index

| Phase | Title | Depends on | Status |
|---|---|---|---|
| [P01](P01_STAGE0_CLOSEOUT.md) | Stage 0 closeout and blocker backlog | — | done |
| [P02](P02_MODEL_ADAPTER.md) | Real model adapter behind `AgentBackend` | P01 | done |
| [P03](P03_SANDBOX_RUNNER.md) | Sandboxed command execution with receipts | P01 | done |
| [P04](P04_GIT_ADAPTER.md) | Local Git adapter and fixture repository | P03 | done |
| [P05](P05_VERTICAL_SLICE.md) | End-to-end vertical slice: objective → verified delivery artifact | P02, P03, P04 | done |
| [P06](P06_DURABLE_MISSIONS.md) | Durable mission state, checkpoints, resume | P05 | done |
| [P07](P07_GITHUB_DELIVERY.md) | GitHub delivery (push, draft PR, CI receipts, protection verification) | P05 (P06 recommended) | done |
| [P08](P08_CURATOR_INDEPENDENCE.md) | Structural Curator independence | P05 | done |
| [P09](P09_POINT_IN_TIME_REPLAY.md) | Physically enforced point-in-time replay | P04 | done |
| [P10](P10_LEARNING_LOOP.md) | Champion/challenger learning loop on real artifacts | P05, P09 | done |
| [P11](P11_SCHEDULER_AND_OPERATIONS.md) | Durable scheduler, role workers, mission-control projection | P06 | done |
| [P12](P12_SOURCE_INGESTION.md) | Source ingestion pipeline; resolve or formally defer open evidence obligations | P01 | done |
| [P13](P13_BENCHMARK_COURT_MVP.md) | Benchmark court MVP (one comparator, one family, no claims) | P05 | done |

### Dependency graph

```text
P01 ─┬─ P02 ──────────────┐
     ├─ P03 ─── P04 ──────┼──▶ P05 ─┬─ P06 ─┬─ P07
     │           └─ P09   │         │       └─ P11
     └─ P12               │         ├─ P08
                          │         ├─ P13
        (P05 + P09) ──────┴─────────┴─ P10
```

Reading: P02, P03→P04 feed P05. P09 needs only P04. P10 needs both P05 and P09.
P12 needs only P01 and can run any time.

After P05, five dependency tracks can proceed concurrently when their declared file
ownership does not overlap:

- **Delivery track:** P06 → P07 → P11
- **Verification track:** P08
- **Learning track:** P09 → P10
- **Governance track:** P12 (any time after P01)
- **Assurance track:** P13

Executors working in parallel must claim different phases and must not edit files owned by
another in-flight phase (each phase file lists its deliverable paths; overlap = conflict).
P10 and P11 both integrate with `src/hive_mind_os/cli.py`; develop them on separate
branches, merge P10 first, then update P11 from `main` and resolve that integration once.
P05's `done` status is limited to its local/offline phase criteria. `B-OPS-03` remains open
until a real provider-backed E2E artifact satisfies its original non-substitution burden;
that evidence obligation does not block the scoped P10/P11 implementation paths.

## 4. Executor protocol (how any LLM runs a phase)

You are an executor. Follow this loop exactly.

1. **Orient.** Read this overview, then your phase file top to bottom, then every file in
   its "Required reading" list. Do not start before finishing the reading.
2. **Verify prerequisites.** Run every command in the phase's "Prerequisite verification"
   section. If any fails, STOP and report; do not improvise fixes to other phases' work.
3. **Branch.** Create a branch named `phase/PXX-short-slug`. Never commit to `main`
   directly.
4. **Implement in order.** Follow the phase's "Implementation steps". Prefer many small
   commits with accurate messages over one large commit.
5. **Write the tests listed in the phase.** They are the minimum, not the ceiling. Every
   listed test must exist and pass. Do not delete, skip, or weaken any existing test.
6. **Run the standard gates** (section 5). All must pass.
7. **Self-review against exit criteria.** Walk the phase's "Machine-checkable exit
   criteria" one line at a time and confirm each with the exact command given.
8. **Record evidence.** Run the post-commit audit and store the artifact as the phase
   specifies.
9. **Update status.** Change your phase's row in the table above (this file) from
   `pending` to `done`, and append a completion record to the bottom of your phase file
   (template in section 7). These are the only edits you may make to plan files.
10. **Stop.** Deliver the branch (and PR where the phase says so). Do not begin another
    phase in the same branch or session unless explicitly instructed.

### Hard rules for every executor

These restate binding rules from `AGENTS.md` and the vision contract; violating any of them
makes the phase failed regardless of test results.

- Fail closed: on missing evidence, ambiguous authority, or unexpected repository state,
  stop and record the blocker; never guess forward.
- Never weaken, skip, or delete a test, gate, schema, validator, or audit check to make a
  run pass. If a gate seems wrong, record the counterexample and stop.
- Append-only: never rewrite or delete existing ADRs, dockets, audits, evidence artifacts,
  or completion records. Supersede; do not erase.
- No self-approval: an executor does not merge its own PR and does not mark its own
  phase's exit criteria "passed" without running the literal commands.
- Constitutional changes (kernel semantics, courtroom, dockets, policy engine, burdens of
  proof, schemas) require a new ADR in `docs/architecture/` numbered after the highest
  existing ADR, with regression tests.
- Runtime code is stdlib-only (`pyproject.toml` declares zero runtime dependencies). Any
  new third-party runtime dependency requires an ADR and an optional extra; dev-only tools
  (pytest, ruff, pyright) stay dev-only.
- Secrets live in environment variables only. They never appear in code, receipts, ledger
  events, logs, fixtures, or committed files. Every phase touching secrets ships a
  redaction test.
- Tests are deterministic and offline: no network, no wall-clock dependence, no reliance
  on machine-specific paths. Anything requiring network or credentials goes in a manual
  script under `scripts/` with a clear name, never in `tests/`.
- Code must work on both POSIX and Windows (development happens on Windows; CI runs
  Linux). Use `pathlib`, honor the portable-path rules in
  `src/hive_mind_os/receipts.py`, and guard POSIX-only APIs (e.g. `resource`) with
  platform checks plus a documented Windows fallback.

## 5. Standard gates

Run from the repository root. All must succeed before a phase is complete.

```bash
python -m pytest -q                      # full suite, no skips introduced by you
python -m ruff check src tests           # lint (rules E4,E7,E9,F,I per pyproject)
pyright                                  # if pyright is unavailable, record that in the completion record
```

Post-commit evidence (worktree must be clean or the audit reports incomplete):

```bash
hive-mind audit --output evidence/audits/PXX-post.json
```

Commit the audit artifact in a follow-up commit on the same branch. An audit that reports
`"complete": false` for reasons your phase introduced is a failed phase; `false` caused by
pre-existing machine-blocked sources is expected and fine — the audit output distinguishes
these.

## 6. Phase file template

Every phase file uses this structure. Executors may rely on the sections existing.

```markdown
# PXX — Title
Status: tracked in 00_OVERVIEW.md | Depends on: ... | Unlocks: ...
1. Objective            — one paragraph; the single outcome this phase delivers.
2. Rationale            — why this phase exists and why now.
3. Required reading     — exact repo paths, in reading order.
4. Prerequisite verification — commands that must succeed before starting.
5. Scope                — in-scope bullets and explicit non-goals.
6. Design constraints   — binding decisions the implementation must respect.
7. Deliverables         — file-by-file list (new and modified).
8. Implementation steps — ordered, concrete.
9. Required tests       — enumerated test cases with file names.
10. Exit criteria       — machine-checkable commands with expected results.
11. Evidence            — receipts/audit artifacts to produce and where they land.
12. Rollback            — how to revert this phase safely.
13. Handoff             — what later phases may now assume.
14. Forbidden shortcuts — phase-specific temptations that are rejected in advance.
Completion record       — appended when done (see below).
```

## 7. Completion record template

Append to the bottom of the phase file, never overwrite an earlier record:

```markdown
---
## Completion record
- Date (UTC):
- Executor (model/agent identity):
- Branch and final commit SHA:
- Gates: pytest <pass/fail + count>, ruff <pass/fail>, pyright <pass/fail/unavailable>
- Audit artifact: evidence/audits/PXX-post.json (digest: <sha256 prefix>)
- Deviations from the phase spec (empty if none, otherwise each with rationale):
- New blockers discovered (mirrored into docs/plan/BLOCKERS.md):
```

## 8. Changing this plan

Typo and link fixes are ordinary commits. Any material change — adding, removing,
resequencing, or rescoping a phase — requires an ADR in `docs/architecture/` explaining the
counterexample or evidence that motivates it, and a version bump at the top of this file.
The plan obeys the same rule it imposes: evidence before authority.
