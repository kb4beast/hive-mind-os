# P04 — Local Git Adapter and Fixture Repository

Status: tracked in `00_OVERVIEW.md` | Depends on: P03 | Unlocks: P05, P09

## 1. Objective

Implement a typed Git adapter that materializes a pinned repository snapshot, creates an
isolated branch workspace, applies edits, runs tests via the sandbox, commits with a role
identity, and exports a reversible delivery artifact (bundle + patch) — every operation
executed through `SandboxRunner` and therefore receipted — plus a deterministic local
fixture repository for end-to-end tests.

## 2. Rationale

The Builder and Curator roles are contractually obligated to work in isolated branches with
executable verification, but no Git capability exists. Building it on top of P03 means every
`git` invocation produces a contract-valid receipt for free, which is exactly the "typed
syscalls" execution-plane requirement. The fixture repository with stable SHAs makes the
whole delivery pipeline testable offline and deterministically.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/sandbox.py` (from P03) and `tests/fixtures/sandbox/` golden files
3. `src/hive_mind_os/receipts.py` (portable path rules)
4. `src/hive_mind_os/policy.py` (`Action.CREATE_BRANCH`, `Action.WRITE_WORKSPACE`,
   `Action.RUN_COMMANDS`)
5. `src/hive_mind_os/models.py` (`Role`)
6. `docs/architecture/CONGLOMERATED_SYSTEM.md` § "Execution plane" (Git worker
   requirements: cannot merge its own work; Curator gets a separate clean workspace)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_sandbox.py    # P03 landed and passes
git --version                                # git available (any modern version)
```

## 5. Scope

In scope:

- `GitWorkspace` (materialize pinned SHA, branch, edit, diff, commit, bundle/patch export,
  status) in `src/hive_mind_os/git_adapter.py`, all subprocess work via `SandboxRunner`.
- A deterministic fixture repository builder under `tests/fixtures/`.
- Rollback evidence: proof the exported bundle re-applies cleanly to a fresh clone.

Non-goals:

- No push, no remotes, no PR creation, no credentials (P07). No merges — the adapter must
  not expose a merge operation at all (constitutional: the Builder cannot merge its own
  work). No history rewriting (`rebase`, `filter-branch`, `push --force` are absent from
  the API). No submodules, LFS, or hooks (document: hooks are disabled at clone via
  `core.hooksPath` pointing to an empty directory — untrusted repo hooks must never
  execute).

## 6. Design constraints

- **System `git` binary** invoked through `SandboxRunner` with `git` in the allowlist and
  the workspace as sandbox root. No Python Git libraries (stdlib-only rule).
- **Pinned materialization.** `GitWorkspace.materialize(source_path_or_url, commit_sha)`
  clones with `--no-hardlinks` from a local path (URLs are rejected until P07 — fail
  closed), checks out the exact SHA detached, verifies `git rev-parse HEAD` equals the
  requested SHA, and disables hooks. A mutable ref (branch name, tag) as the pin is
  rejected: 40-hex SHA only.
- **Deterministic identity.** Commits use `-c user.name=<role identity>`
  `-c user.email=<role>@hive-mind.invalid` per call; never touch global or repo config
  persistently. Author/committer dates are injectable (`GIT_AUTHOR_DATE`,
  `GIT_COMMITTER_DATE` through the sandbox env allowlist) so tests produce stable SHAs.
- **Workspace hygiene.** `write_file(relative_portable_path, content_bytes)` validates
  the path with `receipts.portable_path_parts` and confinement rules; `status_clean()`
  wraps `git status --porcelain`; `diff()` returns the unified diff bytes and their
  digest.
- **Delivery artifact.** `export_delivery(out_dir)` produces: `changes.bundle`
  (`git bundle create` containing the branch), `changes.patch` (`git format-patch`
  output), and `delivery.json` (base SHA, branch name, head SHA, diff digest, file list,
  receipt references for every git operation that produced it). The artifact is the
  reversible unit: applying the bundle to a fresh clone of the base must reproduce the
  head SHA (dates fixed) or at minimum an identical tree digest — assert tree equality
  (`git rev-parse HEAD^{tree}`), which is date-independent.
- **Policy mapping.** `materialize`/`diff`/`status` require `Action.READ_REPOSITORY`;
  `write_file` requires `Action.WRITE_WORKSPACE`; `create_branch`/`commit` require
  `Action.CREATE_BRANCH`; test runs require `Action.RUN_COMMANDS`. Decisions come from a
  `PolicyEngine` passed in; denial is a typed error before any git process runs.
- **Fixture repo.** `tests/fixtures/fixture_repo.py` exposes
  `build_fixture_repo(tmp_path) -> FixtureRepo` creating a tiny Python package with:
  commit 1 = working package + passing test; commit 2 (HEAD) = introduces a clearly
  broken function plus a failing test that demonstrates it. Fixed dates, fixed author,
  `PYTHONHASHSEED=0` irrelevant content → stable SHAs across machines; the builder
  asserts the expected HEAD SHA and hard-fails on drift (this doubles as a git-behavior
  canary).

## 7. Deliverables

New files:

- `src/hive_mind_os/git_adapter.py` — `GitWorkspace`, `DeliveryArtifact` dataclass,
  typed errors (`PinViolation`, `WorkspaceDirty`, `GitOperationFailed`).
- `tests/fixtures/fixture_repo.py` — fixture builder (importable by later phases).
- `tests/test_git_adapter.py`.

Modified files: none.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P04-git-adapter`.
2. Build the fixture repo module first; lock its HEAD SHA constant.
3. Implement `GitWorkspace.materialize` + `status_clean` + hook disabling; test pinning
   (including rejection of branch names and short SHAs).
4. Implement `create_branch`, `write_file`, `diff`, `commit`; test the edit→commit path
   with stable SHAs.
5. Implement `run_tests(argv)` convenience that executes the repo's test command through
   the sandbox inside the workspace (argv supplied by caller — the adapter does not guess
   test commands).
6. Implement `export_delivery` and the fresh-clone re-application check as a library
   function `verify_delivery(artifact_dir, base_source) -> bool` (used by tests now,
   Curator in P05).
7. Gates, audit `evidence/audits/P04-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_git_adapter.py`:

1. Fixture repo builds with the expected pinned HEAD SHA (deterministic across runs).
2. `materialize` at commit 1 yields detached HEAD at exactly that SHA; hooks directory is
   inert (plant a malicious `pre-commit` in the fixture and assert it never runs).
3. `materialize` with a branch name, tag, or short SHA → `PinViolation`.
4. `materialize` with a URL → rejected (local paths only until P07).
5. Branch + `write_file` + `commit` → expected diff, expected tree digest, receipts exist
   for every git invocation and validate against `tool-receipt`.
6. `write_file` with a non-portable or escaping path → rejected.
7. `run_tests` on fixture HEAD reports the failing test (exit code propagated in
   receipt); on the fixed branch it passes.
8. `export_delivery` + `verify_delivery`: bundle applies to a fresh clone; tree digests
   match; `delivery.json` references resolve through `FileReceiptValidator`.
9. Dirty-workspace guard: uncommitted changes → `WorkspaceDirty` on `export_delivery`.
10. Policy denial (e.g. engine at `OBSERVE`) → no git process spawned.
11. API surface: the adapter exposes no merge/rebase/push operation
    (assert via `dir()`/attribute checks — a regression here is constitutional).

## 10. Exit criteria

```bash
python -m pytest -q tests/test_git_adapter.py    # all pass
python -m pytest -q                              # full suite passes
python -m ruff check src tests && pyright        # clean
python - <<'EOF'
import inspect, sys
sys.path.insert(0, "src")
from hive_mind_os import git_adapter
forbidden = [n for n in dir(git_adapter.GitWorkspace) if any(k in n.lower() for k in ("merge","rebase","push","force"))]
assert not forbidden, forbidden
print("no merge/rebase/push surface: ok")
EOF
```

## 11. Evidence

- `evidence/audits/P04-post.json` committed.
- One committed golden `delivery.json` (volatile fields normalized) under
  `tests/fixtures/git/`.

## 12. Rollback

Revert the branch. Nothing imports `git_adapter` until P05.

## 13. Handoff

Later phases may assume: pinned, hook-inert, receipted local Git operations; a
deterministic fixture repo with a known failing test at HEAD; `verify_delivery` as the
reversibility check; no merge authority exists anywhere in the adapter.

## 14. Forbidden shortcuts

- No mutable pins, no URL clones, no hook execution, no global git config mutation.
- Do not bypass `SandboxRunner` "just for fast read-only commands" — every git call is
  receipted or it did not happen.
- Do not have the adapter guess test commands; callers declare them.

---
## Completion record

- Date (UTC): 2026-07-27T18:08:59Z
- Executor: Codex primary Builder/Integrator; independent Curator, Judge, and Orchestrator
  review remains required on the complete exact-SHA pull-request candidate.
- Branch and audited implementation commit: `phase/P04-git-adapter`;
  `09e2a56114ec539cb8b42620d89b1c4d87c6ab44`.
- Prerequisite appeal: P04 reproduced the merged P03 Windows stale-parent-PID timeout and
  paused. ADR-008, its appeal audit, and PR #11 closed that exact defect before P04 resumed
  from merged `main` commit `2355fd82544a16fadc3526d1e1bfd5a21122a6a5`.
- Adapter gates: 13 targeted tests and 9 subtests passed; the full suite passed 182 tests
  with 2 platform-specific skips and 1,718 subtests; Ruff and Pyright were clean; the
  explicit API inspection found no merge, rebase, push, or force surface.
- Deterministic fixture: base/head commits
  `842376f736beea0350d18dc2b983d0414e827885` and
  `f1c725ed6033f6e484f779fb01cd7939f2ae1863`; repaired delivery head/tree
  `6c4a1f8d7036a1520260c004170c740bf41b89a5` and
  `e2fed4976f15a32feb343b06e51e634bddcae76c`.
- Evidence coverage: all Git subprocesses use `SandboxRunner`; receipts validate through
  `FileReceiptValidator`; mutable/short pins, URLs and UNC paths, host Git configuration,
  hooks, dirty export, policy denial, truncated Git output, noncanonical patches, and
  forbidden authority fail closed in executable tests.
- Reversibility: the bundle restores the exact delivery head and tree in a fresh pinned
  clone; the patch is independently checked, applied to the base, and required to produce
  the same tree and canonical bytes.
- Audit artifact: `evidence/audits/P04-post.json`, collected from the clean implementation
  commit above; digest
  `sha256:b8dde1d52a1e850b7aa5a6adf48010ccc4ace60b92d3bb85dd01fbb55869ac5a`;
  result `complete: true`, with no failures.
- Preserved limits: local repositories only; no push, remotes, credentials, pull requests,
  merges, rebases, history rewriting, submodule/LFS support, or production-readiness claim.
  Existing source-ingestion, hard-isolation, repository-protection, and authenticated
  evidence obligations remain open in their assigned later phases.

### Cross-platform golden appeal

- Exact candidate `420899e09744e77b4714efce25e9b6a9b3aa4711` passed Windows gates but
  failed every Linux unit job because `git format-patch` serialized different raw bytes:
  the Windows digest was `sha256:cc3d8d4d72ed59fe4c4bd5e37f64a442cfc3e5411375d80ddc8c4e120510a748`
  and the truncated Linux assertion log exposed the differing prefix
  `sha256:2e89b74e692bb44a0553a25951a3b1788974a2b21` without printing the full digest.
- The failure occurred only in the normalized golden comparison after the per-run artifact
  digest, bundle reconstruction, exact head/tree, patch application, canonical patch, file
  list, diff digest, and receipt checks had passed.
- Repair commit `b225538a63ac930c3b8648d891e43c059d1ec033` normalizes only the raw bundle
  and patch serialization digests in the golden. Runtime manifests retain exact SHA-256
  digests, and `verify_delivery` still requires exact bytes for that Git environment and an
  independently reconstructed tree.
- Repaired local gates: 13 targeted tests and 10 subtests; full suite 182 passed, 2 skipped,
  and 1,718 subtests; Ruff and Pyright clean.
- Additive audit: `evidence/audits/P04-ci-repair.json`, collected from the clean repair
  commit above; digest
  `sha256:a8cea1240e7f771a6b773ad2131635ceb5db9b4950341e0a50b63065219b0031`;
  result `complete: true`, with no failures.
- The failing candidate, original audit, and GitHub logs remain preserved. Exact-head
  GitHub rerun and the single consolidated independent review remain delivery gates.

### Consolidated court repair

- The consolidated court rejected exact candidate
  `2a08800b75ee7b3e50a7dfd4a4daff356247d115`. The Curator reproduced direct Git branch
  creation and local-origin push through `run_tests()` under `SANDBOX` authority, plus
  `.git/HEAD` and `.git/refs/**` mutation through `write_file()`. The Judge independently
  reproduced the test-command bypass and found that unknown manifest schema versions and
  an empty receipt index still verified. The Orchestrator's permit is preserved as dissent
  because it did not reproduce those counterexamples.
- Repair commit `c62f6d49f78dfb923d7d201308ad90a5e65f99a1` reserves Git execution
  for typed adapter methods, rejects lexical and resolved case-insensitive `.git` writes,
  embeds the content-addressed receipts and artifacts in the delivery, requires schema
  version 1 and a nonempty structurally valid receipt index, and revalidates every receipt
  binding through `FileReceiptValidator`.
- Repaired regressions prove lower `SANDBOX` authority cannot create a branch, push to the
  retained local `origin`, or mutate Git metadata; no process is spawned for direct-Git
  test requests. Unknown schema, empty receipts, and corrupted embedded receipts all make
  `verify_delivery()` return false.
- Repaired gates: 15 targeted tests and 16 subtests; full suite 184 passed, 2 skipped, and
  1,724 subtests; Ruff and Pyright clean; forbidden API inspection clean.
- Additive audit: `evidence/audits/P04-court-repair.json`, collected from the clean repair
  commit above; digest
  `sha256:f61dca095444245d33b765175fc65b02a80819580628fca059295275a0982c3d`;
  result `complete: true`, with no failures.
- Wording correction: materialization intentionally retains an isolated local `origin` for
  reversibility tests. P04 grants no external/network remote, credential, or typed push
  authority. This supersedes the earlier shorthand "no remotes" without erasing it.
- The rejected candidate, all three independent findings, prior audits, and GitHub checks
  remain preserved. One final consolidated exact-candidate review is required after the
  repaired GitHub checks pass.
