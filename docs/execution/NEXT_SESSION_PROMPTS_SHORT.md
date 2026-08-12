# Short reusable Autopilot session

The original BOOT/RECON/BASE prompts are preserved in Git history. Current operation is
host-neutral, repository-scoped, and driven by the installed orchestration policy.

Use this prompt to start, resume, inspect, or finish the current repository DAG:

```text
Use Hive Mind OS Autopilot on this repository. Infer whether I mean build, start,
continue, check, or finish; execute its durable parallel-task contract, recover
blockers, and continue until the current DAG is quiescent.
```

The active host must pass the user's actual message to `autopilot orchestrate`, execute
all returned parallel-safe primary tasks through its durable task adapter, record task
bindings, poll them, repair recoverable blockers, and release host bindings only with
terminal evidence. Repository receipts—not task prose—establish node completion.

See `USER_GUIDE/02_ONE_PROMPT_FOREVER.md` and
`docs/execution/PORTABLE_AUTOPILOT.md` for commands and recovery details.
