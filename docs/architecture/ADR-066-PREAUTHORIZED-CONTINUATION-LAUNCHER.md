# ADR-066: Preauthorized continuation launcher

## Status

Implemented as a local, non-promoting continuation mechanism.

## Context

An attended owner can explicitly authorize routine, reversible continuation, yet a
later agent session may incorrectly treat that decision as absent and ask for the
same permission again. The prior PowerShell recovery helper was also tied to one
historic singleton branch and `ARCH-100`, so it could not safely resume current work.

The desired behavior is durable autonomous continuation without converting a general
instruction into unrestricted external authority.

## Decision

- `scripts/Invoke-PreauthorizedContinuation.ps1` is the only canonical launcher for
  this handoff. With `-Apply`, it calls the current repository's deterministic
  `autopilot orchestrate --apply` command using a fixed continuation request and an
  argument array, never a caller-supplied shell command.
- The launcher first resolves the repository and confirms its canonical control-plane
  CLI. It does not reuse a fixed branch, node, snapshot, credential, or old release.
- The dispatcher independently re-observes live state. It can publish a release only
  when its existing reconciliation, eligibility, lease, scope, and safe-action rules
  permit it. A stale or blocked run returns its normal typed refusal.
- `AGENTS.md` directs future agents to invoke this launcher immediately after an
  explicit owner continuation/automation directive. They must continue from durable
  blockers rather than ask the owner to restate an in-scope permission.
- The launcher has no secret handling, shell interpolation, raw GitHub write,
  protected-ref, merge, deploy, spending, policy-mutation, or root-minting path.

## Retained limits

This is durable execution continuity, not durable unlimited consent. A new material
scope still needs its own authority. In particular, the launcher cannot satisfy
`ROOT-3000`: an owner-operated external verifier, custody, rotation, revocation,
deployment, rollback, and independent witness evidence remain required before any
external-root or promotion claim.

## Acceptance evidence

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_preauthorized_continuation -v
python -m unittest discover -s tests -v
```

The focused suite pins the launcher command, fixed continuation request, argument
array, `-Apply` behavior, absence of credential/ExecutionPolicy/merge/deploy shortcuts,
and the durable agent instruction.

## Rollback

Revert the launcher, its test, this ADR, and the `AGENTS.md` continuation section as one
atomic candidate. Existing authority and external-root gates remain fail-closed.
