# ADR-045: Fail-Closed Hard-Isolation Admission Gateway

- **Status:** Adapted bounded local admission-gateway implementation after independent Curator and Judge review
- **Date:** 2026-08-03
- **Case:** `CASE-P17-HARD-ISOLATION-ADMISSION`
- **Prior decisions:** ADR-007, ADR-040, ADR-042, ADR-043, ADR-044
- **Scope:** sealed hard-isolation profile, adapter/capability boundary, host-observation
  receipt contract, and unavailable-runtime refusal. It does not install, configure, or
  claim a production container or VM runtime.

## Context

`SandboxRunner` is a valuable process-tier command gateway, but it executes under the
host user and cannot impose filesystem mounts, network mediation, an independent
credential identity, or a non-bypassable descendant boundary. Its own ADR-007 expressly
leaves hostile-code isolation to P17. P17 requires human authorization before an
isolation runtime or privileged helper is installed or used; no such authority exists for
this worktree.

Calling a local executable named `docker`, a process group, a local SHA-256 digest, or a
container image string “hard isolation” would be false evidence. The implementable,
reversible slice is therefore an admission boundary that refuses hostile work unless an
externally signed, fresh, key-lifecycle-verified capability statement authorizes an exact
sealed adapter/profile/runtime. A bare adapter self-report is rejected.

## Court record

- **Advocate (Builder):** introduce a small replaceable gateway now, so an authorized
  Hyper-V container, ephemeral VM, or OCI adapter has one strict policy and receipt
  boundary instead of every caller inventing fallback semantics.
- **Cross-examiner (independent architecture review):** the current sandbox has ambient
  host filesystem and network reach, same-user receipt exposure, environment-held
  credentials, and legacy bypass callers. A Windows Job Object alone is insufficient;
  it needs a VM/container filesystem, network, and distinct-identity boundary.
- **Expert testimony:** P17 and ADR-007 require default-deny network, mount isolation,
  bounded resources, no ambient credentials, pinned guest execution, and host-owned
  receipts. Runtime installation/use requires authority outside this request.
- **Curator disposition:** `adapt` after independently reproducing 25 focused tests and
  four subtests; it verified external capability admission, deterministic sealed plans,
  durable reservation/quarantine/replay rejection, immutable mount topology, egress
  rejection/proxy sealing, receipt protections, and file-count limits. The verdict applies
  only to the bounded local admission gateway.
- **Judge disposition:** `adapt` after independently reproducing 24 focused tests,
  reviewing the subsequent forged-ID regression, and confirming exact argv binding,
  deterministic/global receipt IDs, signer separation, durable custody provenance, proxy
  sealing, post-dispatch quarantine, disjoint immutable mounts, and file-count limits. The
  verdict applies only to an admission-gateway contract.
- **Dissent / blocking evidence:** no authorized runtime, pinned guest image, controller
  operating identity, egress proxy, or independent external receipt authentication is
  configured. Secret-looking argv is rejected, but arbitrary strings cannot prove complete
  raw-credential absence; the external capability statement authenticates an authority
  assertion rather than host/execution-instance trust. `B-OPS-06` and `B-OPS-08` remain open.

## Decision

1. Define strict `hard-isolation-profile`, `hard-isolation-execution-plan`,
   `hard-isolation-capability-attestation`, and `hard-isolation-receipt` contracts plus a
   replaceable `HardIsolationAdapter`. A profile binds an approved runtime kind and exact
   runtime/image/guest-executable/source-snapshot SHA-256 locators; disjoint read-only
   source and writable overlay mounts (with guest executable under immutable source),
   host-home/evidence/socket/device exclusion, no-new-privileges,
   default-deny or DNS-pinned egress-proxy mode, and CPU/memory/process/disk/output/wall
   file-count/inode, output, and wall limits. The locators are integrity pins, not runtime,
   source, or provider identity.
2. The profile contains only a controller identity and a separate credential-broker
   identity; it never contains a credential or an environment-variable name. A production
   adapter must give the guest neither raw model, Git, nor delivery credentials. It must
   instead invoke a typed, lease-bound host-side broker under the broker identity.
3. `HardIsolationGateway` validates the sealed profile, normal typed command intent, and
   structurally credential-free execution plan with screened argv before dispatch. The plan binds the exact intent digest,
   mission/state/actor/lease, profile, pinned guest executable path, and actual guest argv;
   secret-looking argv values are rejected and a credential need can be represented only as
   a bounded broker operation ID. It accepts an adapter only when an `ExternalCapabilityAuthorizer`
   verifies its signed capability statement through a pinned custody root/keyset lifecycle.
   Capability ID/nonce collision provenance is preserved on disk. No absence, mismatch,
   self-report, unverified claim, or failed conformance may fall back to `SandboxRunner`.
4. A host controller observation must bind the execution plan plus
   intent/profile/runtime/image/executable/source snapshot, controller and actor identities,
   outcome, exit code, required mount/network/resource/cleanup observations, and a bounded
   digest-only guest output artifact. A mandatory `HardIsolationReceiptCollector` reserves
   the execution before adapter dispatch, quarantines an interrupted attempt, and publishes
   an exact-byte receipt with no replacement race before success returns. This is local
   durable provenance, not external controller-receipt authentication or proof of a guest
   self-report.
5. The shipped default capability is explicitly unavailable. It does not probe for a
   local runtime executable or claim that such a probe establishes a hostile-code
   boundary. A later authorized platform adapter must prove its own conformance before it
   can be selected.

## Threat model and residuals

| Threat | Admission/control | Residual and non-claim |
|---|---|---|
| Adapter self-asserts conformance | Exact `passed` capability requires external Ed25519/keyset verification plus ID/nonce provenance; default authorizer refuses | No production external authority is configured in this worktree |
| Hostile work receives an unconfigured process-tier fallback | Exact verified adapter capability is required; default adapter refuses | Existing direct subprocess paths still exist and are not globally migrated |
| Image/runtime/executable substitution | Exact sealed digest locators are cross-bound in controller receipt | SHA-256 locators are not authentication; secure retrieval and runtime attestation remain separate |
| Guest reads host evidence, home, sockets, devices, or secrets | Profile requires readonly root/source, separate overlay, excluded host mounts, and separate broker/controller identities | No real adapter has yet enforced mounts or OS identities |
| Unauthorized egress, DNS tunnel, loopback, private/link-local IP, or metadata service | Default network grants are empty; public DNS grants require a pin and proxy mode; IP and metadata destinations reject | No egress proxy/runtime is installed, so no execution claim is made |
| Process escape or resource exhaustion | Sealed resource limits are required | Job Objects/cgroups/VM enforcement is a future adapter obligation |
| Guest forges receipt/output | Controller receipt retains only host-observed bindings and output digest | Same-host local storage is not external append-only custody |
| Broker confused-deputy or raw secret exposure | Contract excludes credentials; future broker must be typed and lease-bound | A production broker and independent OS identity are absent |

## Platform and adapter obligations

An authorized adapter must identify a supported platform and produce independently
reproducible adversarial evidence. Windows requires a Hyper-V-isolated container or an
ephemeral VM (a Job Object may supplement, never replace, that boundary). Linux OCI needs
read-only mounts, a bounded overlay, no host socket/home/evidence mount, namespace and
cgroup enforcement, default-deny network through an egress proxy, and pinned runtime
image. The first conformance suite must include host/evidence/home reads and writes,
symlink/reparse/ADS escapes, IPv4/IPv6/DNS/metadata egress, environment/PID discovery,
broker abuse, executable substitution, session escape, fork/process bomb, resource
exhaustion, receipt replay/tamper, and unavailable runtime cleanup.

## Migration and rollback

- The change is additive. Historical P03 receipts remain `process-tier`; they are never
  reclassified as hard-isolated. Existing trusted local command paths continue to use P03
  only when their caller explicitly classifies them trusted.
- A future sealed mission that classifies work hostile must bind the hard profile. If the
  exact adapter/runtime conformance is unavailable, execution stops before guest launch.
- Rollback disables selection of the hard adapter and preserves all profile, capability,
  failure, and controller-receipt provenance. It must refuse hostile execution; it may
  not silently recast it as trusted process-tier work.
- This decision changes no branch protection, rulesets, push, merge, provider authority,
  or repository governance.

## Acceptance and deferred obligations

`tests/test_hard_isolation.py` covers strict profile/plan/receipt contracts, deny-by-default
network including loopback/mapped/link-local/metadata rejection, distinct controller/broker
identities, unavailable runtime and bare self-assertion refusal, real signed
capability/keyset verification plus nonce collision, sealed no-secret guest argv, mandatory
pre-dispatch reservation/no-replay, substituted image/output-budget rejection, and host-side
exact-byte receipt replay. `tests/test_contracts.py` validates schema catalog strictness.

Independent Curator and Judge must reproduce the tests and preserve the explicit absence
of a real runtime before this ADR can move from proposed. A future platform implementation
needs a separately authorized runtime, credential broker, conformance corpus, deployment
runbook, external custody integration, and a new court decision. This ADR does not close
`B-OPS-06`, `B-OPS-08`, provider authentication, source authentication, or raw credential
isolation.
