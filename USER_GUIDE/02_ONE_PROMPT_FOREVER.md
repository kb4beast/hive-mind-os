# One reusable Autopilot prompt

The operating rules now live in `.autopilot/orchestration-policy.json` and executable
controller code. Users do not need to paste the controller constitution into every task.

Use this prompt in a repository with an installed Autopilot:

```text
Use Hive Mind OS Autopilot on this repository. Infer whether I mean build, start,
continue, check, or finish; execute its durable parallel-task contract, recover
blockers, and continue until the current DAG is quiescent.
```

The host must run:

```bash
python .autopilot/bin/autopilot.py --repo-root . orchestrate \
  --request "THE USER'S ACTUAL MESSAGE" --apply --json
```

The active host adapter—not the repository CLI—executes the returned external effects.
On Codex, primary nodes use separate durable user-owned tasks through `create_thread`;
the parent records each thread/host identity in the append-only launch ledger, polls
through `wait_threads`, and answers/restarts blocked work through
`send_message_to_thread`. Nested subagents are sidecars for bounded research, review, or
non-blocking validation only.

The deterministic controller enforces repository state and release boundaries. The
versioned policy plus active host adapter enforce external task creation, binding,
polling, and resumption:

- build/start/continue/check/finish intent inference;
- negation and advice as read-only intent;
- snapshot → doctor → reconciliation → dispatch → claim ordering;
- dependency, file-lock, semantic-lock, and `parallel_safe` boundaries;
- resuming existing node work before creating duplicates;
- one closure target before optional audit expansion;
- blocker classification, role consultation, repair, and same-task resumption;
- polling until required primary tasks are terminal;
- repository ancestry and validated receipts as completion truth; and
- quiescence before the parent returns or starts the next required cohort.

`CHECK` is observational and does not publish a release. Terse language never grants a
protected-branch merge, deployment, credential, spending, or authority expansion.

## Use Hive Mind OS from another checkout

Install this repository, then run the target in one command:

```bash
python -m pip install --no-deps -e C:/path/to/hive-mind-os
hive-mind autopilot run "foobar" --repository C:/path/to/target \
  --target-branch release/hive-mind-autopilot
```

`run` is the recommended entry point: its required positional argument is the
objective/subject, such as `foobar`. It records the objective if the target has not
been initialized. Without an installed controller it requests a subject-bound DAG-build
contract. With an installed controller it temporarily returns `PLAN_GENERATION_REQUIRED`
with zero tasks, because the installed plan is not authenticated for the new subject. It
never executes an unreviewed target controller itself. Repeating the command with the same
persisted request is safe; a new subject requires an explicit new initialization decision.

The explicit two-command form remains available:

```bash
hive-mind autopilot init --repository C:/path/to/target \
  --objective "OUTCOME OR LEAVE THE SAFE DEFAULT" \
  --target-branch release/hive-mind-autopilot
```

Then use the same short prompt. Before the target has an installed `.autopilot` DAG,
`hive-mind autopilot inspect` emits a repository-scoped durable
`DAG-BUILD-<repository-digest>-<request-digest>` task. Its task and launch identities bind
the exact request ID and objective digest, so another objective cannot reuse the task.
That bootstrap includes independent controller review and external digest pinning. After
installation, use `autopilot inspect` to address the installed plan intentionally; the
portable wrapper delegates only to the exact reviewed controller bundle. A changed bundle
fails closed until it is reviewed and pinned again.

For a machine-readable preview without applying a release:

```bash
hive-mind autopilot inspect --repository C:/path/to/target \
  --request "check progress"
```

For an execution-authorizing start/continue/finish request:

```bash
hive-mind autopilot inspect --repository C:/path/to/target \
  --request "finish the current DAG" --apply
```
