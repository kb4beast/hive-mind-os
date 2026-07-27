# P03 — Sandboxed Command Execution with Receipts

Status: tracked in `00_OVERVIEW.md` | Depends on: P01 | Unlocks: P04, P05

## 1. Objective

Implement a deny-by-default, receipted command execution layer — the single path through
which any agent runs any external command — with workspace confinement, command and
environment allowlists, wall-clock timeouts, output caps, and a contract-valid
`tool-intent`/`tool-receipt` pair for every execution, verifiable by the existing
`FileReceiptValidator`.

## 2. Rationale

The conglomerated architecture requires that "agent intentions become typed syscalls" and
that no agent holds ambient shell authority. The repository already ships the contracts for
this (`schemas/tool-intent.schema.json`, `schemas/tool-receipt.schema.json`,
`contracts.tool_intent_digest`, `receipts.FileReceiptValidator`) but no executor that
honors them. This phase builds that executor at the process level — the container/VM tiers
remain later work — so P04 (Git) and P05 (vertical slice) can run real commands with real
evidence. This touches kernel enforcement semantics, so it ships with an ADR.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/receipts.py` (entire file: portable paths, `ReceiptReference`,
   `FileReceiptValidator`, `sha256_digest`)
3. `src/hive_mind_os/contracts.py` (`load_schema`, `validate_contract`,
   `tool_intent_digest`)
4. `src/hive_mind_os/schemas/tool-intent.schema.json` and
   `src/hive_mind_os/schemas/tool-receipt.schema.json` (exact required fields)
5. `src/hive_mind_os/policy.py` (`PolicyEngine.decide`, `Action.RUN_COMMANDS`)
6. `src/hive_mind_os/autonomy.py` (`EpisodeAllowance`)
7. `tests/test_receipts.py` (how receipts are validated today)
8. `docs/architecture/ADR-003-EXECUTABLE-RECEIPT-VALIDATION.md`

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_receipts.py tests/test_contracts.py   # pass
python - <<'EOF'
from hive_mind_os.contracts import load_schema
load_schema("tool-intent"); load_schema("tool-receipt"); print("ok")
EOF
```

## 5. Scope

In scope:

- `SandboxSpec` + `SandboxRunner` (process tier) in `src/hive_mind_os/sandbox.py`.
- Policy + budget checks before execution; receipts after; both fail closed.
- Content-addressed receipt files under a trusted root compatible with
  `FileReceiptValidator`.
- ADR documenting the enforcement gateway decision and its residual limits.

Non-goals:

- No containers, VMs, or WASM tiers. No network proxy or egress allowlists — this phase
  denies network *by construction where possible* (scrubbed env, no shell) and documents
  that hard network isolation arrives with the container tier. No secret broker (P07 uses
  env-scoped tokens with redaction). No Windows job objects — Windows enforcement is
  timeout + confinement checks, documented as best-effort.

## 6. Design constraints

- **Single gateway.** All command execution anywhere in `src/hive_mind_os/` goes through
  `SandboxRunner.run()`. Existing code that shells out (check `current_state_audit.py`)
  is out of scope to migrate now, but new phases must use the runner; note this in the ADR.
- **Deny by default.** `SandboxSpec` declares: `root` (workspace directory), `writable`
  (relative portable paths under root), `argv_allowlist` (allowed executable basenames,
  e.g. `("python", "git")`), `env_allowlist` (names copied from the parent env; everything
  else scrubbed), `timeout_s`, `max_output_bytes`, `cpu_seconds`/`memory_bytes`
  (enforced via `resource.setrlimit` in a `preexec_fn` on POSIX; documented no-op on
  Windows where `timeout_s` is the enforcement).
- **No shell.** `subprocess.run` with `argv` list, `shell=False`, `cwd=root`,
  explicit `env`. The executable must resolve (via `shutil.which`) to a real file and its
  basename (case-insensitive, `.exe` tolerated on Windows) must be in the allowlist.
- **Confinement checks.** Every path argument the caller marks as a path (see intent
  shape below) must satisfy `receipts.portable_path_parts` and resolve strictly inside
  `root` after `Path.resolve()`; symlinks that escape root are rejected on platforms
  where they can be created.
- **Typed intent in, typed receipt out.** `SandboxRunner.run(intent: dict) -> dict`
  where `intent` validates against the `tool-intent` schema (the runner fills/validates
  the canonical digest via `tool_intent_digest`) and the return validates against
  `tool-receipt`. The receipt binds: the intent digest, argv, exit code, duration,
  stdout/stderr SHA-256 digests and byte counts, a `truncated` boolean per stream (caps
  must be *explicit*, never silent), the sandbox spec digest, and the runner identity.
- **Receipt persistence.** Stdout/stderr bytes and the receipt JSON are written
  content-addressed under `trusted_root` (constructor argument) so
  `FileReceiptValidator` can verify them; the write itself is atomic
  (temp file + `os.replace`).
- **Fail closed.** Policy denial (`PolicyEngine.decide(role, Action.RUN_COMMANDS, risk)`),
  budget exhaustion (`EpisodeAllowance`), allowlist miss, confinement violation, or
  schema-invalid intent each raise a typed error *before* the process starts; timeout
  kills the whole process group (POSIX `start_new_session=True` + `os.killpg`; Windows
  `taskkill /T` fallback) and still produces a receipt with outcome `timeout`.

## 7. Deliverables

New files:

- `src/hive_mind_os/sandbox.py` — `SandboxSpec`, `SandboxRunner`, typed errors
  (`SandboxDenied`, `SandboxTimeout`, `ConfinementViolation`), `spec_digest()`.
- `tests/test_sandbox.py`.
- `docs/architecture/ADR-007-PROCESS-SANDBOX-GATEWAY.md` — decision, threat model delta
  (what process-tier enforcement does and does not stop; Windows best-effort posture;
  network isolation deferred to container tier), rollback.

Modified files:

- none required. (If `tool-intent`/`tool-receipt` schemas lack a field the runner needs,
  STOP: schema changes are constitutional — record the gap in `BLOCKERS.md` and design
  the receipt within existing fields, or write the ADR to extend the schema with
  regression tests.)

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P03-sandbox-runner`.
2. Read both schemas and sketch the exact intent/receipt documents for a trivial
   `python -c "print('hi')"` run; validate the sketches with `validate_contract` in a
   scratch script before writing the runner.
3. Implement `SandboxSpec` (frozen dataclass) with validation in `__post_init__` and a
   canonical `spec_digest()`.
4. Implement `SandboxRunner.run()` in this order: validate intent → policy check → budget
   consume → allowlist + confinement checks → execute with limits → cap/collect output →
   write artifacts + receipt atomically → validate receipt against schema → return it.
5. Write tests (section 9), including the POSIX-only ones guarded with
   `pytest.mark.skipif(sys.platform == "win32", ...)` and keeping every non-guarded test
   passing on both platforms.
6. Write ADR-007.
7. Gates, audit `evidence/audits/P03-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_sandbox.py` (use `tmp_path` for roots; `sys.executable` for python):

1. Happy path: allowed command runs; receipt validates against `tool-receipt`; stdout
   bytes round-trip through `FileReceiptValidator`.
2. Intent digest binding: mutating any intent field after digest computation is rejected.
3. Non-allowlisted executable → `SandboxDenied`, no process spawned, no receipt artifact.
4. Path escape via `..` → `ConfinementViolation` (test with a path argument
   `../outside.txt`).
5. Symlink escape (POSIX-only) → `ConfinementViolation`.
6. Env scrubbing: a sentinel env var set in the parent is absent inside the child unless
   allowlisted (child prints `os.environ` keys).
7. Timeout: a sleeping child is killed within tolerance; receipt outcome is `timeout`;
   child process is not left running (poll pid).
8. Output cap: a child printing > `max_output_bytes` yields truncated stream, correct
   digest of the truncated bytes, and `truncated: true` in the receipt.
9. Policy denial: a role/risk combination the `PolicyEngine` denies → `SandboxDenied`
   before spawn.
10. Budget: exhausted `EpisodeAllowance` → denial before spawn.
11. Atomicity: simulate a crash between artifact write and receipt write (monkeypatch) →
    no receipt claims artifacts that are absent/mismatched (validator fails closed).
12. Determinism: same command twice → identical intent digests, receipts differing only
    in permitted volatile fields (duration, timestamps).

## 10. Exit criteria

```bash
python -m pytest -q tests/test_sandbox.py         # all pass
python -m pytest -q                               # full suite passes
python -m ruff check src tests && pyright         # clean
test -f docs/architecture/ADR-007-PROCESS-SANDBOX-GATEWAY.md
python - <<'EOF'
# a receipt produced by the runner is accepted by the existing validator
import tempfile, sys
from pathlib import Path
sys.path.insert(0, "src")
from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.contracts import tool_intent_digest
from hive_mind_os.receipts import FileReceiptValidator
from hive_mind_os.sandbox import SandboxRunner, SandboxSpec
with tempfile.TemporaryDirectory() as td:
    base = Path(td); root = base / "workspace"; root.mkdir()
    intent = {
        "schema_version": 1, "action_id": "ACT-smoke", "mission_id": "mission-smoke",
        "state_ref": "MISSION_STATE:mission-smoke:1", "actor_id": "builder-smoke",
        "kind": "command", "description": "sandbox smoke",
        "action_digest": "sha256:" + "0" * 64,
        "policy_decision_ref": "POLICY-smoke", "lease_id": "LEASE-smoke",
        "idempotency_key": "smoke", "rollback_ref": None,
        "command": {"argv": [sys.executable, "-c", "print('ok')"], "path_args": []},
        "status": "proposed",
    }
    intent["action_digest"] = tool_intent_digest(intent)
    runner = SandboxRunner(
        SandboxSpec(root, argv_allowlist=(Path(sys.executable).name,)),
        base / "evidence", EpisodeAllowance(1, 1.0),
    )
    runner.run(intent); assert runner.last_reference is not None
    result = FileReceiptValidator(base / "evidence").validate(
        runner.last_reference, mission_id=intent["mission_id"],
        state_ref=intent["state_ref"], actor_id=intent["actor_id"],
        action_id=intent["action_id"], action_kind="command",
        action_digest=intent["action_digest"],
    )
    assert result.valid and result.succeeded
EOF
```

## 11. Evidence

- `evidence/audits/P03-post.json` committed.
- One example intent + receipt pair committed under `tests/fixtures/sandbox/` as golden
  files (with volatile fields normalized) for use by later phases' tests.

## 12. Rollback

Revert the branch; ADR-007 is superseded, not deleted. No other module imports
`sandbox.py` until P04.

## 13. Handoff

Later phases may assume: `SandboxRunner` is the only sanctioned way to execute commands;
every execution yields a schema-valid, validator-verifiable receipt; policy and budget are
enforced pre-spawn; Windows enforcement is timeout+confinement (documented), POSIX adds
rlimits.

## 14. Forbidden shortcuts

- No `shell=True`, ever. No PATH-based trust without `shutil.which` resolution.
- No silent truncation, no receipt-less failure paths (even denials append a ledger event
  if a ledger is provided).
- Do not loosen `tool-intent`/`tool-receipt` schema validation to "make receipts easier".
- Do not claim network isolation — the ADR must state plainly it is not provided at this
  tier.

---
## Completion record

- Date (UTC): 2026-07-27T17:16:17Z
- Executor (model/agent identity): Codex primary Builder/Integrator; independent Curator,
  Judge, and Orchestrator review is required on the complete pull-request candidate.
- Branch and audited implementation commit: `phase/P03-sandbox-runner`;
  `d6988b260cefc19a7588dec61e2c5de3e209be75` includes the reviewed timeout, concurrency,
  denial-evidence, non-object-input, and process-creation-exception repairs on the current
  P02-bearing `main`.
- Gates before the final replacement audit: 19 targeted sandbox tests ran on Windows (18
  passed, the POSIX-only symlink case skipped; 3 subtests passed); constitutional discovery
  ran 169 tests (167 passed, 2 skipped); 1,698 subtests passed; Ruff 0.16.0, Pyright
  1.1.411, and the schema catalog passed.
- Concrete runner/validator smoke: passed; ephemeral receipt digest
  `sha256:5c2ad2b87a5d8b3fd6d544467beb199132a006f9e4bda0701ca80e10af841cb0`.
- Audit artifact: pending clean replacement at `evidence/audits/P03-post.json`; the final
  evidence commit will record its digest and cannot contain its own SHA.
- Constitutional schema delta: `tool-intent.command` and `tool-receipt.execution` were
  added under proposed ADR-007 with catalog, golden-fixture, mutation, and validator
  regressions. Historical non-command documents remain compatible; untyped command intents
  now fail closed.
- Preserved limitations: this is a process tier, not hard filesystem or network isolation;
  Windows resource enforcement is best effort; local receipts are neither externally
  authenticated nor append-only; existing legacy subprocess callers remain out of scope.
- Preserved dissent: the first consolidated review rejected candidate `68f0613` after
  reproducing an early-parent-exit descendant timeout bypass, concurrent allowance
  overbooking, and missing denial evidence for digest/confinement/NUL failures. The repaired
  candidate closed those cases. Curator re-review then reproduced raw `SubprocessError` and
  non-object-intent `AttributeError` escapes; the implementation commit above closes both.
  Final exact-candidate re-review remains a delivery gate.
- New blocker: `B-OPS-06` tracks the hard container/VM isolation tier and cannot be
  represented as resolved by this phase.
- Production readiness, release readiness, hostile-code isolation, and superiority are not
  claimed.
