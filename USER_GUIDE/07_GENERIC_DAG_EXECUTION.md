# Generic DAG execution

The installed `hive-mind dag` interface builds and inspects portable plans. Its
default execution profile requires an external host integration. An explicitly
selected operator-local profile can run bounded repository work using local
Codex sessions. These profiles have different authority and state formats.

## Install and inspect the interface

Use Python 3.11 or newer. From a checkout, installation into your chosen Python
environment is `python -m pip install -e .`. Then inspect the installed interface:

```powershell
hive-mind dag --help
hive-mind dag build --help
hive-mind dag execute --help
hive-mind dag resume --help
```

If the console script is not on that environment's PATH, the same installed
Python package exposes `python -m hive_mind_os.dag_cli --help` (omit `dag` for this
module entry point).

## Choose exact inputs before running a command

Obtain the plan and its expected digest from the provenance for your authorized
objective. The plan binds its request, subject, original objective, standard,
nodes, dependencies, budgets, and recovery rules. Repository subjects pin a
commit and tree. A historical plan or test fixture is not a live authorization.

Use explicit absolute paths for plan, standard, output, and state. The expected
plan digest is `sha256:` followed by 64 hexadecimal characters, calculated over
the plan's canonical representation. A raw hash of arbitrarily formatted JSON
is not a substitute. The loader rejects noncanonical plan bytes; it also checks
the exact standard binding. Merely calculating a digest from an untrusted file
does not establish that you intended to run that file.

The examples below are templates. Replace every placeholder with values from
the same reviewed input packet; they do not supply a working plan or credentials.
The output parent directory must already exist.

```powershell
$plan = 'C:\h\my-campaign-inputs\plan.json'
$standard = 'C:\h\my-campaign-inputs\standard.md'
$planDigest = '<expected canonical plan digest from the input packet>'
$requestId = '<expected request ID from the input packet>'
$subjectId = '<expected subject ID from the input packet>'
$state = 'C:\h\my-campaign-state'
$boundPlan = @('--plan', $plan, '--standard', $standard,
    '--expected-plan-digest', $planDigest, '--mode', 'repository')
$identity = @('--expected-request-id', $requestId,
    '--expected-subject-id', $subjectId)

hive-mind dag validate @boundPlan @identity
hive-mind dag rounds @boundPlan @identity
hive-mind dag graph @boundPlan @identity
```

These inspection commands do not dispatch workers or create state. `rounds`
shows the compiler's scheduling groups; `graph` returns nodes, dependency edges,
rounds, and metrics as JSON. A successful inspection describes a valid bound
plan, not completed work. `--subject` is only an operator label; use the expected
identity options to constrain validation.

For a non-repository subject, choose an explicit supported mode:
`offline-local`, `research-artifact`, or `workflow`. This enables the common
inspection contract, not a local Codex execution adapter for that subject.

## Write an inert canonical output

```powershell
hive-mind dag build @boundPlan --output 'C:\h\my-campaign-inputs\sealed.json'
```

`build` validates the supplied plan and writes its canonical bytes to the named
output. It does not generate a plan from a prompt, start workers, create runtime
state, or activate a release. Existing outputs are refused unless `--replace`
is explicitly supplied. Keep original inputs and provenance when choosing a new
output or replacing one. The preceding validation uses both expected identities;
the build example binds the same exact plan digest.

`prepare-powershell` emits JSON containing inert PowerShell text for validation,
round inspection, and status. It requires an absolute execution-client path and
`--expected-execution-client-digest` in addition to its plan inputs. It does not
execute the text or authorize work. Consult
[the public runtime contract](../docs/execution/PUBLIC_DAG_RUNTIME.md) for the
remaining host-custody requirement between hashing a client and launching it.

## Execution profiles

| Profile | What it can do | What must be supplied |
|---|---|---|
| Default `--runtime external` | The stock CLI returns `BLOCKED` with `EXTERNAL_RUNTIME_REQUIRED` for execute/resume; cancel/reconcile also require an integration. | An authenticated host adapter and independent verification of the review, host attestation, signature, and one-use nonce through the Python service. Naming an activation file is insufficient. |
| Explicit `--runtime local` | Runs supported compiled repository nodes in isolated clones, records worker sessions and local authenticated evidence, and can create local candidate commits. | The exact repository pin, objective bytes, explicit operator directive, local host custody, separate run/brain directories, and a working authenticated native Codex CLI environment. |

The local profile uses an `operator-local-v1` grant authenticated under the
operator's OS account. Distinct worker sessions do not establish independently
administered builder, verifier, judge, or promoter signing principals. Its grant
allows inspection, isolated local edits, local tests, and run evidence. This
runtime does not push, open a PR, merge, deploy, or promote. It invokes Codex
workers, so an execute command performs real work and may consume account usage.

Before local execution, retain the original objective as `request.txt` beside
the plan; its bytes must match the plan's `objective_digest`. The separate
operator-request file contains the actual nonempty UTF-8 directive authorizing
the bounded local run. Do not fill it with a fabricated authorization. A plan
must also satisfy the local node-execution compiler; passing generic inspection
alone does not guarantee that every node has a local execution policy.

Run state and brain must be outside the subject repository and separate from
each other. Choose a dedicated host directory outside the repository, state,
and brain for the local key and reservation journal. For a fresh run, state and
brain directories must not already exist. The host may create its local key;
this does not provision external signing authority. Preserve custody and all
these paths for recovery.

The following execution template assumes those prerequisites have been met:

```powershell
$localRun = @('--runtime', 'local',
    '--repository', 'C:\h\my-subject',
    '--state-directory', $state,
    '--host-directory', 'C:\h\my-campaign-host',
    '--operator-request-file', 'C:\h\my-campaign-inputs\operator-request.txt',
    '--brain-directory', 'C:\h\my-campaign-brain',
    '--workers', '1', '--node-timeout', '900',
    '--worker-mode', 'evidence-packet')

hive-mind dag execute @boundPlan @identity @localRun
```

Worker count must be within the compiled maximum; node timeout is 30–3600
seconds and remains subject to node budgets and the remaining grant lifetime.
The default `evidence-packet` mode asks workers for reports and proposed patches
and applies permitted patches through the host. The optional `direct` mode
allows writable workers to edit their assigned candidate; changing the mode
does not enlarge the grant. Keep the selected mode and other configuration
unchanged when resuming.

## Inspect progress and resume durable state

The two profiles use different records:

- **External executor:** `hive-mind dag status --state-directory $state --plan
  $plan --expected-plan-digest $planDigest` reads `dag-execution.sqlite3` without
  creating missing state. Add `--run-id` to select a run; a supplied run must
  match the plan and subject. `state_present: false` means that database is
  absent, not that an operator-local run has no progress.
- **Operator-local:** read the run's `status.json` and the brain's `INDEX.md`.
  These are derived progress views; `events/`, worker receipts and raw outputs,
  stored inputs, grant/configuration, candidate history, and host custody
  checkpoint are the durable evidence. Reading a progress file is not an
  independent authentication or acceptance check.

```powershell
Get-Content -LiteralPath (Join-Path $state 'status.json')
Get-Content -LiteralPath 'C:\h\my-campaign-brain\INDEX.md'

# Reuse the original input paths, identities, and local configuration.
hive-mind dag resume @boundPlan @identity @localRun
```

Local resume rechecks bindings, host bytes, grant validity, event history,
worker evidence, and candidate state before advancing. Already completed nodes
are retained. A stored failed node normally returns `BLOCKED`; an interrupted
started intent returns `RECOVERY_REQUIRED` because worker effects may be
uncertain. Retain evidence and inspect the actual process/workspace before
choosing a recovery. Do not delete state, rewrite receipts, or restart a second
controller to erase the blocker.

The advanced `--refresh-local-host` and `--recover-recorded-patch` options are
separate, explicit packet-mode resume operations. They are restricted to the
runtime's validated terminal read-only retry or recorded-patch recovery cases;
they cannot be combined and do not extend the original grant expiry. They are
not general retries for uncertain effects. The stock `cancel`/`reconcile`
commands do not operate on this local state format.

## Completion and rollback

Local `COMPLETED` and its `completed_nodes` count describe that particular plan's
authenticated local events. They do not prove completion of a different DAG,
independent release qualification, superiority, or promotion authorization.
Keep failures, dissent, and rejected alternatives with the run. Any delivery or
promotion needs its own applicable outcome, regression, safety, held-out,
authority, and comparator evidence; the local result records
`promotion_authorized: false`.

For rollback, retain the original repository and the run evidence. The candidate
is isolated under the run state and can be abandoned without merging it. Preserve
the grant and custody journal for auditing or recovery rather than repurposing
them for another objective. This guide changes no plan schema, historical
receipts, or runtime policy.
