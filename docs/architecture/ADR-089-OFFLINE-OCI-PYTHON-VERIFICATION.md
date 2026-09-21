# ADR-089: Offline OCI Python verification for trusted single-tenant targets

## Status

Candidate, optional and off by default. Independent security Curator/Judge verdict:
**ADAPT** for trusted local verification on the tested Windows Docker Desktop host,
subject to mandatory final integrated CI. The two earlier remands remain in the
evidence record below. The Judge's requested timing and mount-path documentation
corrections are incorporated. This is not production acceptance, external custody,
hostile-code isolation, or N18 closure.

## Original source and requirements

Source: `docs/plan/whole-os-tournament-2026-09-13/NODES-LEARNING.md`, node **N18 —
Enforce the tenant and host execution boundary** (dependencies N03, N04; independent
reviewer: Curator specializing in sandbox escape tests). The parts this slice addresses:

- Step 2: first backend is an OCI Linux container runner with fixed argv and a pinned
  image; missing backends return UNAVAILABLE and never substitute `LocalProcessSandbox`.
- Step 3: mount only the selected snapshot; no host home, Hive checkout, Docker/control
  socket, oracle store, or other tenant artifacts.
- Step 4: deny network; start without provider, forge, platform, or export credentials.
- Step 5: process-tree, wall-time, output, disk, CPU, and memory bounds.
- Step 8: persist allocation and teardown identities before effects; recover interrupted
  runs by inspecting the same allocation and retain an outcome receipt, with no duplicate
  execution.
- "Keep the old process backend available for explicitly trusted work, with truthful
  capabilities."

Not addressed (remain open N18 obligations): tenant-dedicated worker VM, the
`IsolationAttestation` schema and probe suite, dependency cache/broker, artifact
copy-out, N03/N04 bindings, and the independent sandbox-escape review.

## Decision

Add `src/hive_mind_os/docker_verification.py` with two pieces, plus minimal seams in
`verification_adapters.py`:

1. `ImagePythonUnittestAdapter(image)` seals
   `/usr/local/bin/python -B -m unittest <selected tests> -v` and `--version`. The image
   is an exact `name@sha256:<64 hex>` reference supplied by trusted constructor code.
   Mutable tags, extra options, and anything from target JSON are rejected. The image is
   part of `adapter_version`, `SealedCommand.image_identity`, and the sealed digest.
   Legacy commands keep their previous digest byte for byte.
2. `DockerPythonSandbox` implements the existing `SandboxAdapter` seam. It resolves the
   docker executable once, hashes it, re-checks those bytes before every invocation, and
   only builds list argv (no shell). It accepts only the two approved Python argv shapes
   and refuses any other command or environment.

`verify_repository` gains an optional trusted `registry` (used for sealing *and* version
reporting) and binds each sandbox's execution receipt digest into the outer receipt before
the outer digest is computed. `SandboxCapabilities` gains a trailing `image_identity`
(default `None`). A sealed image command with a mismatched sandbox image returns BLOCKED;
a sandbox that cannot run returns a typed `SandboxUnavailable`, which becomes a BLOCKED
receipt. There is no fallback to the host process sandbox. `VerificationBudget` now also
rejects NaN and infinity (the only change to the trusted-local API).

## Container profile

`docker create` with: `--pull never`, `--network none`, `--read-only`, `--cap-drop ALL`,
`--security-opt no-new-privileges`, `--user 65534:65534`, `--memory`/`--memory-swap`
(equal, no swap), `--cpus`, `--pids-limit`, `--ulimit cpu`, `--log-driver none`, a
`rw,noexec,nosuid,nodev,mode=1777,size=<n>` tmpfs at `/tmp`, exactly one read-only bind of
the evidence-owned workspace at `/workspace`, an explicit `--entrypoint`, and only these
`--env` values: `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `TMPDIR=/tmp`. Host
variables are never forwarded.

**Docker client configuration.** Every docker invocation (create, inspect, start, kill,
rm, image inspect, and every recovery call) is `docker --config <owned dir> [--host <ep>]
…`. The directory is `docker-config/` beside the evidence, created exclusively with one
inert file (`config.json` = `{}`), no links or other entries; it is re-validated before
*every* call, and its path and content digest are bound into the intent, the create argv
and the receipt. The operator's own Docker configuration (proxies, credential helpers,
contexts) is never read, copied or inherited, which is what prevents the CLI from injecting
proxy credentials into the container environment. Because contexts live in that
configuration, daemon selection is explicit: constructor `docker_host` accepts only a local
`npipe:////./pipe/<name>` or `unix:///<path>` endpoint (no tcp/ssh, so no certificates or
credentials) and is bound the same way; omitting it uses the client's built-in default
endpoint. No `DOCKER_*` or proxy variable is forwarded to the client; only
`SystemRoot`, `USERPROFILE`, `HOME`, `APPDATA` and `LOCALAPPDATA` may be (names recorded,
values not). **Dependency for root:** a Docker Desktop run that formerly relied on the
`desktop-linux` context must now pass the trusted endpoint explicitly (for example
`docker_host="npipe:////./pipe/dockerDesktopLinuxEngine"`, to be confirmed against the real
engine); the sandbox will not infer it from user configuration.

**Exact container environment.** Before any container exists, `docker image inspect` of the
pinned image (which must carry the pinned digest as its ID or repo digest) supplies its
baked environment, journaled as `image_verified`. The expected environment is that
mapping overlaid with the three fixed values (these win, as Docker does). After create, the
container's `Config.Env` must **equal** the expected mapping: unexpected, missing, changed,
duplicate or malformed entries fail closed before start. Reports retain names and SHA-256
digests of unexpected or changed entries only, never their values.

Before starting, the applied configuration is re-read with `docker inspect` and compared
to the profile; any difference means the container is removed unstarted. The comparison
is exact for network mode, read-only root, `CapDrop == ["ALL"]` and no `CapAdd`,
`SecurityOpt == ["no-new-privileges"]`, user, `Memory` and `MemorySwap`, pids, `NanoCpus`,
the single cpu ulimit, log driver `none`, the tmpfs option *set* (so `exec`/`suid`/`dev`
or a different size fail), exactly one mount that is a read-only bind at `/workspace`
whose `Source` matches the workspace, no binds/devices/`VolumesFrom`, private namespaces,
entrypoint/cmd/environment/workdir, and no stdin/tty. The bind `Source` is compared with a
narrow, documented translation (`expected_mount_source`): the exact native workspace
path is accepted, as is its exact Docker Desktop translation (`C:\Users\a` to
`/run/desktop/mnt/host/c/Users/a`). The real Windows engine returned the native path
in the remand probe; no fuzzy path aliases are accepted. UNC and `\\?\` workspaces
are refused rather than guessed.
All applied values are retained in the journal and in the receipt (`applied_configuration`).
The tmpfs value format is the daemon's stored option string; if a daemon normalises it
differently the check fails closed and must be re-observed, not relaxed.

The tmpfs is bounded by `min(disk_bytes, memory_bytes)` and counts against container
memory. Tests that write relative to the workspace fail truthfully because it is read-only.

## Allocation lifecycle and recovery

Each call (`version`, `tests`) owns `sandbox-<phase>.journal.jsonl` and
`.receipt.json`, created exclusively under the caller's evidence directory (which must be
inside the sandbox's `evidence_root`). The journal is append-only and hash-chained:
`allocation_intent` (unique name + label token + docker digest + client config digest +
daemon endpoint) is durable before any docker effect; then `image_verified`,
`create_result`, `configuration_checked`, `start_attach`, `attach_result`, optional `stop`,
`final_state`, `cleanup`, `outcome`.

- **One execution deadline** starts when `run` starts and covers validation, create,
  inspect and attach; each control call is bounded by the time remaining, the attach gets
  what is left (never the original timeout again), and no container is started after
  expiry. Deadline expiry triggers client termination; it is not a hard total-return
  deadline. Host-process reaping can then use two waits of up to 15 seconds each,
  followed by up to two 5-second reader joins. Those bounded host waits precede the
  container cleanup clock. Stop/inspect/remove then share **one separate ~20 s container
  cleanup allowance** (not per call). Execution and container-cleanup durations are
  recorded in the receipt (`timing`). If the allowance is
  exhausted, cleanup is reported unverified. `verify_repository` subtracts only the
  reported cleanup seconds from elapsed time, and an image-sealed run that still exceeds
  the wall budget is `FAILED` with `wall_budget_exceeded`; `cleanup_grace_seconds` is
  recorded. NaN/infinite timeouts or budgets are refused.
- **No failed create is ever settled by wording or absence.** A create counts as resolved
  only when the daemon returned a container ID, when the call was provably *never
  attempted* (a pre-effect check failed, journaled `not_attempted`), or when an *owned*
  container was found and removed (`create_resolved`). **Every other attempted create is
  unresolved**, including a clean exit 1 with "Cannot connect to the Docker daemon" (which
  can be a Moby read timeout) or "Error response from daemon: gateway timeout" (which can be
  a proxy failing after the request was accepted): an immediate absent inspect records
  `cleanup_verified: false`, `create_unresolved: true`, and `recover` never returns
  `already_settled`. Each later `recover` makes one bounded inspection (no loop) and reaps
  a late container without executing it. Repeated absence still cannot prove a late create
  will not arrive, so routine failures such as a stopped daemon also stay unresolved until
  an owned container is removed or the operator applies the manual procedure below.
- **Absence needs Docker's exact diagnostic.** `inspect` reports a container absent only for
  exit 1, empty or `[]` stdout and a single stderr line that is exactly
  `Error: No such container: <ref>`, `Error: No such object: <ref>` or
  `Error response from daemon: No such container: <ref>` with the very identifier that was
  asked for. A missing socket or pipe ("…: no such file or directory"), proxy or daemon
  errors, extra lines, a different identifier or different wording are transport problems:
  the call is unavailable, cleanup is unverified, nothing is settled, and `recover` journals
  `recovery_unavailable` so a later call with a working connection reaps the allocation.
  The real diagnostic text must be confirmed against Docker; if it differs the code fails
  closed rather than guessing.
- Output is bounded while streaming; timeout or cap kills only the owned container. Exit
  code comes from `inspect` and is never trusted for a container that did not start or
  whose attached stream ended abnormally. `run_bounded` monitors the client *process* and
  its readers against one monotonic deadline, so closing the pipes does not end the wait,
  and closes each host pipe handle only after its reader thread has finished. A reader
  still blocked because a descendant inherited the pipe is left to its daemon thread
  (never closed under it). The bounded reader joins can extend return time beyond the
  execution deadline; a stuck reader is not awaited indefinitely. Host termination and
  reader-join overhead remains included in execution accounting, so it cannot create a
  late `PASSED` result. This slice does not promise a hard 20-second total teardown bound.
- Every kill/remove is preceded by an ownership check (name, label token, image digest,
  recorded ID). A mismatch raises `SandboxOwnershipError` and touches nothing. No `--rm`,
  no `prune`, no broad cleanup, no shell.
- **Docker binary integrity.** The digest is re-checked before every docker invocation; a
  changed file is refused before execution. `recover` also requires the journal's recorded
  docker digest, client config digest and daemon endpoint to equal the current ones, so a
  swapped binary, altered config, or a different daemon (whose "absent" would be a false
  settlement) is never used against an old receipt. A legitimate Docker upgrade therefore
  needs the manual procedure below.
- **Torn journals.** The verified prefix is trusted; only a damaged *final* record is
  treated as torn, anything earlier is a broken chain and refused. The original bytes are
  never rewritten. Recovery from an intact prefix that contains the intent writes a
  separate exclusively created `sandbox-<phase>.recovery-<sha16>.journal.jsonl` whose first
  record anchors the full original byte hash, the prefix length and head digest, and the
  torn tail hash; a later call for the same bytes continues that journal. Ownership
  checks, no execution and the unresolved-create rules are unchanged. A journal with no
  intact intent is refused with a typed error (an intent is durable before `create`, so
  none can have been issued).

### Manual procedure when recovery reports unresolved or refuses

Preserve every journal, recovery journal and receipt unmodified. Using a docker binary
whose SHA-256 equals the journal's `docker_digest`, the journal's `docker_config` directory
(`--config`) and `docker_host` endpoint, list read-only:
`docker ps -a --filter name=<name>` and `--filter label=io.hive-mind-os.verification-allocation=<token>`
(both come from the `allocation_intent` record). Only a container whose ID, name, label
token and image digest all match may be removed, by ID. If nothing is found the allocation
stays unresolved; there is no code path that marks it resolved, and any operator decision
to close it must be recorded outside the journal.

## Alternatives considered

- **Docker SDK / HTTP socket:** new dependency and a broader control surface; rejected.
- **`docker run --rm`:** simplest, but erases inspect evidence and cannot journal intent
  before the effect; rejected.
- **Writable workspace bind or copy-in/out:** larger attack surface and escape/disk
  accounting problems; rejected. The read-only root and workspace plus bounded tmpfs is
  the disk budget.
- **Reuse `PythonUnittestAdapter`:** would run a Windows `sys.executable` path inside
  Linux and conceal what ran; rejected.
- **Treat a second absent inspect as proof of no create:** rejected; no number of
  observations bounds a remote daemon's completion of a request.
- **Truncate or rewrite a torn journal:** rejected; it would hide evidence.
- Podman/gVisor/Firecracker: possible future backends behind the same seam; not evaluated.

## Threats and residual limitations

Considered: secret inheritance, host mounts, Docker socket exposure, network egress,
mutable-image substitution, argv/path injection (including `--mount` option injection via
paths), symlink/junction aliasing, output flooding, fork/CPU/memory exhaustion, timeout
orphans, unknown or late creates, foreign container removal, journal tampering or tearing,
overwritten evidence, deadline bypass through NaN/infinity or closed pipes, configuration
drift, and a swapped docker binary.

Limitations, stated plainly:

- **Not hostile-code isolation.** The Docker Desktop engine and its Linux VM are shared
  with the operator and other workloads, not an independently attested tenant-dedicated
  worker. `hostile_code_isolation` stays `False`; the default requirement still blocks.
  A container escape or engine compromise is out of scope.
- The docker client, daemon endpoint and image store are trusted host components. The
  endpoint is now an explicit constructor value rather than user configuration, but a
  wrong endpoint chosen by trusted code cannot be detected here. Hashing the binary and
  re-validating the config directory before each call leaves a small time-of-check/
  time-of-use window between the check and the exec. If the real docker client writes files
  into the owned config directory, the next call fails closed and the behaviour must be
  re-observed, not relaxed.
- The exact-environment check trusts `docker image inspect` of the pinned digest and the
  container inspect output from the same daemon; it detects client-side injection and drift,
  not a lying daemon.
- The unknown-create window is closed only by running `recover`; a late container that
  is created but never started cannot execute code, yet it can persist until reaped.
- Journal hash chaining detects edits by a non-holder, not a rewrite by someone who can
  rewrite the whole file; there is no external anchor or custody attestation.
- `recover` must be invoked when no other process still owns the allocation; the
  `isolation-backend:<host>` lock from N18 is the caller's responsibility.
- Sandbox instances are not thread-safe. Unit tests use a modelled daemon and prove no
  real isolation property.
- The wall budget excludes only the reported (≤ ~20 s per phase) cleanup grace.

## Migration and rollback

Migration is opt-in and off by default: existing callers get the same registry, sandbox,
receipt shape, and digests. A caller must construct the adapter and the sandbox with the
same digest-pinned image, pass the registry to `verify_repository`, and explicitly accept
`SandboxRequirements(hostile_code_isolation=False)`. Rollback is to stop passing the
registry/sandbox, or select the previous adapter (`python-unittest` on
`LocalProcessSandbox`, or the prior image digest). Journals, receipts, and any retained
containers are kept; nothing is deleted on rollback.

## Judge remand and evidence record

Facts as reported by root (not independently verified by the Builder): the first
unit run passed 36 OCI tests (1 skipped) and 12 legacy verification tests (2 skipped);
a real probe ran the private Coupon Hive suite (18 tests) through this adapter in the
pinned image and passed, with the version and test allocations removed. That positive
result is retained as evidence about the earlier candidate; its source hash is an old
candidate, so real probes must be rerun after these repairs. The independent Judge
(`/root/readiness_judge`) **remanded** the code for these reproduced defects, all
addressed in this revision and covered by new regression tests, none yet independently
re-verified: (1) a timed-out create followed by an absent inspect was marked clean and a
late container was orphaned while `recover` returned `already_settled`; (2) `run_bounded`
returned early when the client closed its pipes; (3) the configuration check accepted a
wrong bind source, `MemorySwap=-1`, no ulimit, a weak tmpfs and
`no-new-privileges=false`; (4) each control call had its own 60 s and the attach received
the full timeout again; (5) the docker digest was sealed only at construction; (6) a torn
final journal record made recovery fail without a preserved-evidence path; (7) ten
pyright errors in these files.

**Second remand (retained as dissent against the first repair).** After the first repair
root observed a real attempt-4 pass (all 18 Coupon tests, both containers cleaned), and
kept that positive, but the Judge reproduced three blockers that the positive does not
override, plus a root-observed `ResourceWarning`:

1. *Unsafe refusal classification.* The first repair treated a clean exit 1 with "Cannot
   connect to the Docker daemon" or "Error response from daemon: …" as an authoritative
   refusal and settled the allocation. The Judge showed a Moby read timeout or a proxy
   gateway timeout after the request was accepted leaves a late container while the receipt
   said cleaned and `recover` made zero docker calls. **That classification was wrong and
   is removed**; the original behaviour is recorded here as the defect, not as precedent.
   Every failed attempted create is now unresolved (see lifecycle above).
2. *Socket-missing read as absence.* `inspect` accepted any stderr containing "no such",
   so "dial unix /var/run/docker.sock: … no such file or directory" was reported as
   "container absent" and settled a live allocation. Absence now needs the exact
   identifier-bound Docker diagnostic.
3. *User Docker config and unsealed environment.* The CLI reads proxies from the user's
   config and injects `HTTP_PROXY` credentials into the container `Env`; the check accepted
   any superset. Every call now uses an owned inert `--config` directory with an explicit
   daemon endpoint, and the container environment must equal the image-plus-fixed merge.
4. *Unclosed pipes.* `run_bounded` left `process.stdout`/`stderr` to the garbage collector
  (`ResourceWarning`). Handles are now closed after their readers finish. The execution
   deadline still triggers termination; bounded host-reaping and reader-join overhead
   follows as described above.

Root's changes since the first result are preserved: the exact native-Windows *or*
translated mount `Source`, the native-path test, import formatting and the typed callback.
Dissent and the Judge's approval decision remain the Judge's to record; this document does
not self-approve.

## Acceptance and verdict

Final evidence dated 2026-09-21 is retained under the operator's
`production-closeout-20260920` evidence bundle. Earlier candidate results remain
point-in-time observations; the following results concern the repaired implementation:

| Evidence | Actual result |
| --- | --- |
| Root focused unittest discovery, `test_docker_verification.py` | 78 tests passed, one Windows symlink privilege skip |
| Root legacy discovery, `test_verification_adapters.py` | 12 tests passed, two platform capability skips |
| Root Ruff and Pyright | Passed with no reported issues |
| Root real application probe, attempt 5 | 18 tests passed; both allocations cleaned; 4.589 seconds |
| Independent Judge real Docker cases | Kernel/filesystem/environment/network controls, observed cgroup limits, truthful assertion failure, timeout, and output cap passed; all ten owned allocations independently observed absent |
| Independent Judge historical negative probes | Both delayed-create diagnostic variants, lost-socket recovery, proxy injection, and unexpected loader environment passed |

Independent `/root/readiness_judge` verdict: **ADAPT**, with the scope and conditions
in Status above. Retained report `oci-final-judge-review.md` has SHA-256
`3b2ea8e5cb387e7417c14e0f4e81d348204110b5e47b7a58e6efb096b9460dbd`.
Reviewed source SHA-256 bindings:

- `docker_verification.py`: `57d09dd54f4d4598dba4d5e587fd669b5281c00f010977f8d9bdeb352f7ea667`.
- `verification_adapters.py`: `2c9472591aab0e7cb9da391e02172b98c8d60c08e2fdb4f2e645719898e1bd56`.
- `test_docker_verification.py`: `daa989d03e6a1cb803c143ab99b750330806e773a12f964465f56564ca124e16`.

The real image was `python@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9`;
the observed local endpoint was `npipe:////./pipe/dockerDesktopLinuxEngine`.
Measured cgroup settings are not fork-bomb or OOM stress qualification. Real
crash/recovery, sandbox escape, independent tenant-host attestation and other N18
obligations remain open; skipped or unperformed probes are never passes. The
complete integrated unittest gate is pending at this record. This ADR does not
modify attestation helpers or issue host grants.
