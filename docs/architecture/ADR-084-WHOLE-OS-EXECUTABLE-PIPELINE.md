# ADR-084: Sequential executable Whole-OS pipeline

## Decision

Adopt a host-side PowerShell pipeline that invokes one non-interactive Codex worker
at a time for host bootstrap, N30, N31, N32, and N33. Each stage uses a committed
prompt and closed result schema, writes its event log and current envelope outside
the repository, and cannot release the next stage until the current stage reports a
typed terminal completion. A hidden master process may persist across operator
sessions and retries `in_progress` or `blocked` work at a bounded interval.

The launcher uses `codex exec --ask-for-approval never --sandbox danger-full-access`
inside the explicitly selected repository. It does not use Codex's dangerous bypass
flag, ignore repository instructions, place secrets in arguments, auto-merge, spend,
publish a game, or infer external authority. The agent remains governed by
`AGENTS.md`; the flag combination removes routine interactive prompts but does not
change policy or evidence requirements.

## Rationale

The merged Whole-OS service deliberately requires a process-local trusted host. The
legacy preauthorized continuation launcher remains bound to its historical August
plan, so replaying it cannot execute the September N00-N33 campaign. The new pipeline
is an explicit deployment-host bridge using the already installed Codex CLI. It
replaces repeated operator/agent exchanges with one durable sequence while retaining
honest boundaries for evaluator custody, target grants, Roblox rights/runtime, and
the actual 72-hour pilot windows.

## Recovery and rollback

Stage envelopes are written under `%LOCALAPPDATA%\HiveMindOS\whole-os-pipeline` by
default. Restarting the master skips completed stages and resumes the first incomplete
stage. A retained PID prevents duplicate background masters. Stop the recorded
process to pause; retain the stage directory and restart the same command to resume.
Rollback removes no evidence: select the prior repository release and leave pipeline
logs, result envelopes, failed attempts, and external obligations intact.

## Verification

`tests/test_whole_os_powershell_pipeline.py` checks stage order, fixed prompts, closed
schema use, hidden-process launch, absence of bypass/eval shortcuts, and PowerShell
parse validity. Each stage remains responsible for its contract-specific tests and
the repository CI gate when it changes product bytes.
