# ADR-045: Host-Neutral Autonomous Repository Brain

- **Status:** Proposed for independent Curator disposition
- **Date:** 2026-08-05
- **Case:** `CASE-AUTONOMOUS-REPOSITORY-BRAIN`
- **Origin:** Owner requirement for prompt-kicked-off, self-improving repository work

## Court record and decision

### Source intake

The Explorer inspected `https://github.com/Fayth-Investments/mission-control.git`
at commit `557fa957a69bf62415b5fcf84c0ff0df2ccf04e0` on 2026-08-05. The local checkout did
not contain an observed `LICENSE*` file. Its license is therefore **unknown** and no
Mission Control code, data, or wording was copied. The source is used only for these
abstract, independently implemented patterns: an append-only decision ledger, a
feedback loop, and delayed outcome assessment. The missing license remains an
explicit source obligation if any future change proposes code reuse.

- **Advocate:** prompt-driven repository work needs a durable brain that survives a
  session change, records decisions, and learns from later human corrections instead
  of treating an opened PR as the final outcome.
- **Cross-examiner:** an autonomous system can leak prompt/comment secrets, accept
  instruction injection from PR comments, mutate protected branches, turn a host
  login into broad remote authority, replay future commits as training context, or
  silently claim a lesson without a measured result.
- **Expert evidence:** focused tests create disposable Git repositories, prove that
  Codex and Claude Code commands are selected without API keys, reject a dirty
  kickoff, retain protected refs, deduplicate and sanitize PR feedback, and create
  one physically isolated sealed PIT episode for every later human commit.
- **Judge:** a separately identified Curator must decide the exact candidate and
  evidence after focused tests. This ADR is not that decision.

**Decision: adapt.** Hive Mind OS gains a local SQLite-backed Autonomous Brain. It
has six deliberate layers rather than one opaque memory blob:

1. **Charter:** repository pin, selected host, safe prompt digest/summary, immutable
   authority switches, protected branches, and a non-protected `hive-mind/` branch.
2. **Working memory:** a dedicated Git worktree and a checked task file, both bound
   to the charter.
3. **Event ledger:** append-only safe action receipts. It records output digests and
   changed paths, never raw model transcripts.
4. **Feedback memory:** comment identity, author, digest, safe action, and optional
   bounded reply. Raw comment text lives only during its one host turn.
5. **Outcome memory:** the eventual human-selected final commit and the exact number
   of post-run commits.
6. **Learning memory:** one sealed, ancestor-only Point-in-Time (PIT) grade per later
   commit. A lesson is a measured candidate, not an automatic policy or model change.

## Carry-forward requirement gate

The complete autonomous-repository requirement bundle is sealed at kickoff, rather
than inferred again from a later, abbreviated restatement. The append-only manifest
contains these seven atomic obligations and their enforcement/test references:

1. one user prompt starts an autonomous run for a selected repository;
2. locally signed-in Codex and Claude Code work without API keys;
3. `main`, `master`, and `staging` are never merged or written;
4. the run has a durable, append-only brain;
5. PR feedback and the human-selected final state become learning input;
6. every later human commit gets one recoverable PIT prediction and grade; and
7. while supervision is active, each new bound PR comment is implemented, answered,
   refuted, or safely blocked, with safe answers/refutations posted back to the PR.

Every later autonomous action loads and checks that exact manifest before it can run.
If even one binding is absent or altered, the run blocks rather than silently treating
a shortened follow-up prompt as a replacement for the original objective. The safe
`hive-mind autonomous requirements` view exposes the sealed bundle without retaining
raw model output or raw PR-comment bodies.

## Host and delivery boundary

`hive-mind autonomous kickoff` accepts one prompt and creates an isolated local clone
with no configured Git remote.
`turn` invokes either the locally signed-in `codex exec` or `claude --print` CLI. The
adapter removes token/API-key environment variables and uses no API key itself. Codex
runs with its read-only sandbox; Claude Code runs in its plan mode, which cannot edit
files or execute commands. Neither host is given write authority. Instead, an
implementation host returns one bounded unified Git patch as data. The trusted
controller checks and applies that relative-path patch, then creates a commit only in
the isolated non-protected run branch. It removes all inherited Git, GitHub, and SSH
configuration variables plus normal GitHub/Git credential configuration, checks local
`main`, `master`, and `staging` refs immediately before and after the turn, and supplies
a Git transaction hook as defense in depth for its controlled Git processes. A mismatch
blocks the run.
The clone must begin with exactly one `origin` remote, remove it successfully, and
prove that its remote list is empty; any other condition blocks before host launch.

There is intentionally no merge API, CLI command, or gateway. The only optional Git
write to a remote is a non-force push of the run's own `hive-mind/` branch, and that
requires an immutable `--allow-remote-push` kickoff grant. It cannot name a protected
branch. A run can open only a draft PR for that stored branch after the controlled
push; it still has no merge operation.

A separately bound PR may be polled. Each new conversation comment is treated as
untrusted data, redacted before the host sees it, and deduplicated by its remote ID.
The host must choose `implement`, `answer`, `refute`, or `blocked`; answer/refute
requires one short safe reply. Posting that reply requires the separate immutable
`--allow-pr-comments` grant. This allows reasoned conversation without giving the
system a merge capability. The adapter polls both ordinary PR conversation comments
and inline review comments, then replies in the ordinary PR conversation. It does not
silently mark review threads resolved.

`hive-mind autonomous supervise` is the bounded autonomous operating mode for that
feedback loop. Its caller supplies a finite polling lease; each poll handles any new
bound-PR feedback and observes the local repository HEAD. It resumes from the durable
ledger after interruption, rather than needing the original prompt or raw model output
again. It does not assume a webhook, a background service, or permission to fetch a
remote repository: those deployment adapters remain optional and separately governed.

## PIT learning and promotion boundary

When a human final commit is supplied, the Brain verifies it descends from the run
start and enumerates every commit in `start..final`. For each of the N commits it:

1. gives a predictor only an isolated ancestor worktree;
2. seals its predicted changed paths;
3. reveals the target only after the seal;
4. grades overlap and appends the result.

The bounded supervisor supplies that final commit from a changed local HEAD. Each
run/target pair first receives one deterministic, append-only episode reservation.
The predicted paths and learner identity are then stored in a separate durable record
before the oracle can seal. A transactional gate serializes sealing and grading; a
competing supervisor waits, rechecks, and skips an already stored grade. If interrupted
after sealing, a retry rebuilds the same recorded ancestor environment, rehydrates the
same durable seal, and finishes that episode rather than making another one. Thus N
later local commits produce N separate sealed grades, even when they are discovered
across multiple polling leases or a retry follows interruption.
If setup was interrupted before the environment record existed, the incomplete
workspace is moved into a retained quarantine area and the same episode identity is
rebuilt; no PIT evidence is deleted or replaced.

For a parent target, the oracle creates one ancestor bundle in its private staging
area and one temporary copy in the learner environment for the local fetch. Each is
removed exactly once before the learner environment is handed off. The focused PIT
test proves that the parent environment is returned without a bundle file.

The selected Codex or Claude host can serve as the read-only predictor only from a
fresh remote-free clone of the oracle's verified ancestor environment. A malformed
prediction, missing local sign-in, or any oracle failure blocks the learning run; it
does not fabricate a grade. Grades produce evidence for a versioned challenger under
the existing recursive-improvement gate. They never self-promote a prompt, policy,
or host profile.

## Threats, controls, and acceptance

| Threat | Control |
|---|---|
| Merge to main/staging | Hosts have no write authority (Codex read-only sandbox; Claude Code plan mode); the controller can apply/commit only to the stored `hive-mind/` branch, with transaction-hook and before/after ref defenses |
| Direct protected push | Host clones have no remote or inherited GitHub/Git credentials; controlled delivery pushes only the stored `hive-mind/` branch, never force, and defaults off |
| Prompt/comment injection | Comments are declared untrusted, redacted, bounded, and never replayed from memory |
| Secret or raw-output retention | Secret-like kickoff text is rejected; model output and raw comments are held only in memory; ledger keeps digests and safe summaries |
| Host/provider lock-in | `HostKind` selects Codex or Claude Code through a replaceable invocation boundary |
| Human correction lost | Every later commit receives a distinct sealed PIT episode and measured grade |
| Host sees a future PIT target | The host receives a disposable remote-free clone made only from the oracle's verified ancestor environment |
| Feedback replay/duplicate reply | Remote comment IDs are append-only deduplication keys |
| Earlier requirement omitted in a follow-up prompt | The complete kickoff requirement bundle is sealed and checked before every later autonomous action |
| Concurrent or interrupted PIT supervision | Stable run/target episode reservations, durable pre-seal predictions, retained incomplete-workspace quarantine, seal/grade recovery, a transactional grade gate, and a unique grade record prevent duplicate episodes while allowing retry |
| Autonomous policy mutation | Authority is immutable per run; learning does not change policy or prompts |

Acceptance is a focused test proving the charter contract, protected branch refusal,
both host command selections, safe feedback/reply behavior, bounded supervision,
append-only records, and exactly N PIT records for N later commits. The full CI gate
and independent Curator are later delivery requirements.

## Rollback and limits

Revert the autonomous module, schema, CLI route, policy capability, tests, and this
ADR together. Existing mission state, continuation packets, all P03–P05 receipts,
branches, and blockers are not changed. This feature does not mark P03, P04, or P05
complete; their historical evidence and their outstanding closeout conditions remain
separate. It also does not automatically open PRs, read review-thread comments,
merge any branch, or promote learned behavior without the independent existing gates.
