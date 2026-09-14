# Whole-OS tournament source packet

## Local baseline and owner evidence

`LOCAL-01` is the inspected Hive Mind OS baseline at commit `d980a9cfe39f68b3de86ea0530234b3ab4e91390`, tree `47f873cf5924b97cfafafe1b9dfb0a450acb2e92`. [local-source-manifest.json](local-source-manifest.json) binds 53 selected local source/test/doc paths to original Git blobs and SHA-256 hashes of the observed checkout bytes. Original local sources remain in that pinned Git history; line-ending differences are recorded rather than treated as source changes. The repository's MIT license does not replace licenses of embedded external materials.

The owner-supplied original is preserved in [USER_REQUEST.md](USER_REQUEST.md), independently interpreted into 18 atomic requirements in [requirements.json](requirements.json). Its provenance is this conversation and its task scope is documentation only. Baseline findings and material claim dispositions are in [RUNBOOK.md](RUNBOOK.md) and [REVIEW.md](REVIEW.md).

EX17/EX18 were fetched by root using the official OpenAI documentation connector before the observed UTC time `2026-09-14T00:55:20Z`. No exact per-fetch timestamp or raw-body digest was retained. This bounded observation does not close their raw archival obligation.

This file records a targeted primary-source survey for the documentation-only tournament handoff dated 2026-09-13 in America/Chicago. Retrieval occurred on **2026-09-14 UTC**. It is an evidence index and expert testimony, not an implementation receipt, executed benchmark, exhaustive Internet survey, or independent judicial verdict.

The research identity was `/root/external_evidence`. It used the web tool to inspect primary pages and public GitHub HTTP endpoints to resolve repository versions and compute byte digests. The author of this packet is the source scout and technical witness; recommendations below require the separately identified court disposition described in [RUNBOOK.md](RUNBOOK.md). A recommendation to `adopt` or `adapt` supports considering an abstract design pattern, not a claim that its implementation has passed acceptance tests.

## Retrieval and preservation status

- Repository metadata was retrieved at **2026-09-14T00:52:38Z–00:53:49Z**. Commit SHAs and SPDX labels below were returned by public GitHub repository/commit endpoints. SPDX metadata is source identification, not a legal opinion or a compatibility verdict.
- The listed SHA-256 values were computed over the bytes actually fetched by .NET `HttpClient.GetByteArrayAsync`. Immutable README and Roblox markdown receipts were collected at **2026-09-14T00:55:02Z–00:55:04Z**. Mutable HTML receipts were collected at **2026-09-14T00:55:04Z–00:55:05Z**. A retrieval date describes observation time, not necessarily publication time.
- **Raw bodies were fetched into memory but were not retained as local source archives.** The initial research delegation prohibited file changes. Writing this source index afterward does not retroactively preserve those bodies. Full raw-body archival ingestion remains **OPEN** for every entry. Versioned URIs and hashes support later retrieval and comparison; they are not a substitute for preserving the bytes and provenance.
- The GitHub license pages were not separately archived and hashed. Roblox's root `LICENSE` was additionally read and identifies Creative Commons Attribution 4.0 International. Source ingestion must retain each applicable license and notices, inspect exceptions and third-party material, and record a compatibility disposition before code reuse.
- Mutable HTML contains navigation/site content and can change between requests. A new response that differs from a recorded hash is a new source version: append a receipt and preserve the old receipt. Do not overwrite the recorded digest or pretend the new response is the old one.
- No comparator agent, training job, Roblox build, Studio test, production game, benchmark, deployment, or publication was run for this survey. **Measured application results: not collected**, for every entry.
- EX17 and EX18 were fetched by the root author, not this research identity. Their content is summarized in [RUNBOOK.md](RUNBOOK.md); this packet does not invent a byte digest or a second independent retrieval for them.

## Source and atomic claim records

### EX01 — mini-swe-agent: minimal execution scaffold

- Primary URI: <https://github.com/SWE-agent/mini-swe-agent>.
- Immutable source: <https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/04d809ceab9df28f9adaed044884180159172930/README.md>.
- Version: commit `04d809ceab9df28f9adaed044884180159172930`, committed **2026-09-03T05:05:59Z**.
- License identification: **MIT**, repository metadata; exact license-file preservation remains open.
- Retrieved body: **11,106 bytes**, **2026-09-14T00:55:02.5120642Z**.
- SHA-256: `9982d90b7566f2f3fa5e9811b475d5e8e2a84e2df80cf3f1e4be6e820b129835`.
- EX01-C01: the agent uses a shell action interface without requiring a large custom tool vocabulary.
- EX01-C02: execution history is a linear message trajectory suitable for inspection and training data.
- EX01-C03: independent subprocess actions simplify substitution of local and sandbox execution environments.
- EX01-C04: agent, model, environment and runner are distinct components.
- Counterclaims: upstream benchmark scores do not establish Hive Mind performance, cross-repository isolation, Roblox ability or production readiness. A shell-only agent still needs environment boundaries and effect authority. Growing linear history can consume context; the source does not prove this is the cheapest long-running strategy for this workload.
- Witness recommendation: **adapt** the small builder loop and use a pinned minimal-agent comparator. Measure accepted outcomes, total cost and elapsed time under matching budgets before making efficiency claims.

### EX02 — SWE-agent: configurable interface comparator

- Primary URI: <https://github.com/SWE-agent/SWE-agent>.
- Immutable source: <https://raw.githubusercontent.com/SWE-agent/SWE-agent/3ea751c087f32b16e039a2233dd6eefecef325d5/README.md>.
- Version: commit `3ea751c087f32b16e039a2233dd6eefecef325d5`, committed **2026-07-16T15:21:18Z**.
- License identification: **MIT**, repository metadata; license archival remains open.
- Retrieved body: **8,158 bytes**, **2026-09-14T00:55:02.7159663Z**.
- SHA-256: `dcd880557720efbab0f5c0e68f2bc742309efecfce83244c9e670ec1f1adf76f`.
- EX02-C01: configurable agent/tool interfaces and history processing provide a different scaffold from the minimal shell loop.
- EX02-C02: the current README says upstream development effort has shifted to mini-swe-agent and recommends mini going forward.
- Counterclaims: upstream's relative-performance statements were not reproduced here. Extra interface machinery can help some models while adding configuration and maintenance work. Legacy status is a reason to pin and assess support, not proof that every design idea is obsolete.
- Witness recommendation: **adapt** as a richer-interface comparator; **defer** selecting it as the default foundation without local evidence.

### EX03 — OpenHands Software Agent SDK: interchangeable execution backends

- Primary URI: <https://github.com/OpenHands/software-agent-sdk>.
- Immutable source: <https://raw.githubusercontent.com/OpenHands/software-agent-sdk/15a9b8609c12635abacefa1f91beacedd7798296/README.md>.
- Version: commit `15a9b8609c12635abacefa1f91beacedd7798296`, committed **2026-09-13T19:36:55Z**.
- License identification: **MIT**, repository metadata; license archival remains open.
- Retrieved body: **10,835 bytes**, **2026-09-14T00:55:02.8073100Z**.
- SHA-256: `95094c9745c7cc58136d4eaa1688fb6038aafefec2be05344293f6df7e55dbf8`.
- EX03-C01: the SDK separates agents, tools, conversations, workspaces, events and an Agent Server.
- EX03-C02: workspaces may run locally or in ephemeral environments such as Docker or Kubernetes.
- EX03-C03: the SDK exposes Python, TypeScript and REST interfaces.
- EX03-C04: current repository ownership places coding execution in `software-agent-sdk`; `OpenHands/OpenHands` is the Agent Canvas/control center, and `OpenHands/automation` owns scheduling and dispatch.
- Counterclaims: running on a local workspace does not itself isolate a tenant or protect unrelated host files. An SDK and a desktop control center are different comparators; treating the Canvas repository as the coding engine would confound the tournament. Framework breadth does not establish production-ready generated code.
- Witness recommendation: **adapt** the execution interface separation and evaluate the pinned SDK as an optional backend/comparator. Preserve the host's own authority and privacy boundary outside the chosen agent.

### EX04 — Temporal: durable work and idempotent effects

- Primary article: <https://temporal.io/blog/idempotency-and-durable-execution>.
- Authors: Keith Tenzer and Joshua Smith. Displayed publication date: **2024-02-27**; this is the current retrieved article, which may have been updated since publication.
- Article license: **not established**; do not infer that the website inherits the server repository's license.
- Retrieved article: **186,658 bytes**, **2026-09-14T00:55:04.5298757Z**.
- SHA-256: `9247719e394253a7f8d4468d1d8023e3259f64ce7253bdf3868c182f9585d424`.
- Related implementation URI: <https://github.com/temporalio/temporal/tree/9ab3a9f770da20df7d94bcc0030f28eec7b0b947>. Commit `9ab3a9f770da20df7d94bcc0030f28eec7b0b947`, **2026-09-11T17:18:20Z**, **MIT** metadata. The complete server code was not ingested or evaluated.
- EX04-C01: workflow event history supports recovery and resumption.
- EX04-C02: external activities may execute at least once, so an attempted effect can be retried after uncertain completion.
- EX04-C03: stable idempotency keys and uniqueness constraints can prevent duplicate effects.
- EX04-C04: a check-before-create sequence can race and is not sufficient on its own to guarantee uniqueness.
- Counterclaims: durable orchestration does not automatically make an external API exactly-once. Temporal introduces operational infrastructure. The illustrative implementation in the article is not a tested Hive Mind adapter.
- Witness recommendation: **adopt the pattern** of durable task state, stable operation identity and ambiguous-response reconciliation for branch, commit and PR operations. **Defer** selecting Temporal itself until it has been compared with extending the current kernel.

### EX05 — LangGraph: distinguish run state from durable learning

- Primary URI: <https://docs.langchain.com/oss/python/langgraph/persistence>. The earlier `durable-execution` URL redirected to this page during retrieval.
- Documentation version: mutable page observed at retrieval; page license **not established**.
- Retrieved body: **840,369 bytes**, **2026-09-14T00:55:04.9994606Z**.
- SHA-256: `b624c2a32bdeebabcea454069821dc2897ce5db61b40cdc192900c299f02e825`.
- Related implementation URI: <https://github.com/langchain-ai/langgraph/tree/e539ac122f4126f6dd850581c1494948cf620e31>. Commit `e539ac122f4126f6dd850581c1494948cf620e31`, **2026-09-09T07:22:43Z**, **MIT** metadata. The library was not installed or evaluated.
- EX05-C01: checkpointers persist one task's graph state.
- EX05-C02: stores persist application-defined data across tasks.
- EX05-C03: in-memory checkpoints disappear when the process restarts.
- EX05-C04: accumulated checkpoints can increase storage costs and latency.
- Counterclaims: a task namespace is not proof of access control, encryption or process isolation. Persistence APIs do not automatically implement the user's cross-app learning policy. Advice to prune checkpoints cannot be applied to required append-only provenance without a separate preserved evidence archive.
- Witness recommendation: **adapt** distinct run-state and learning-state interfaces, with durable storage and explicit ownership. Compare an adapter rather than replacing the entire kernel on documentation evidence.

### EX06 — SWE-bench: reproducible repair evaluation

- Primary repository: <https://github.com/SWE-bench/SWE-bench>.
- Immutable source: <https://raw.githubusercontent.com/SWE-bench/SWE-bench/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/README.md>.
- Official benchmark definitions: <https://www.swebench.com/>; observed during this research, no separate HTML byte digest obtained.
- Version: commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`, committed **2026-09-02T01:50:34Z**.
- License identification: **MIT for the harness repository**. Individual datasets, included tasks and originating repositories require their own rights review.
- Retrieved README: **13,302 bytes**, **2026-09-14T00:55:03.2426766Z**.
- SHA-256: `06841624d7b5130dfe3cc6714642e9a8fd2a608c95c66ae0180e409f12b73aaa`.
- EX06-C01: repository issue-repair tasks can be evaluated in reproducible execution environments.
- EX06-C02: the official site describes Verified as a 500-instance human-filtered subset.
- EX06-C03: the official bash-only view evaluates models in the same mini-swe-agent environment.
- Counterclaims: issue repair is not complete-product creation, autonomous opportunity discovery or Roblox gameplay evaluation. Public benchmark tasks may already appear in model pretraining. No scores from the public leaderboard were reproduced or adopted as Hive Mind measurements.
- Witness recommendation: **adapt** the matching-task/environment principle and executable receipts. Use additional held-out product and autonomy scenarios; report the source, task, model and contamination limitations of each cohort.

### EX07 — SWE-smith: execution-filtered training tasks

- Primary repository: <https://github.com/SWE-bench/SWE-smith>.
- Immutable source: <https://raw.githubusercontent.com/SWE-bench/SWE-smith/9b74ac08118a85c39c356802f7961893af73e07f/README.md>.
- Documentation entry: <https://swesmith.com/>; no separate page byte digest obtained.
- Version: commit `9b74ac08118a85c39c356802f7961893af73e07f`, committed **2026-03-21T23:39:59Z**.
- License identification: **MIT**, repository metadata and README; target-repository/dataset rights are separate.
- Retrieved README: **5,217 bytes**, **2026-09-14T00:55:03.0289917Z**.
- SHA-256: `058ccfb4465b3d067ac53eae9db43d55dfdaf180fcae438880901e3b192584b7`.
- EX07-C01: repository execution environments can support generated software-engineering tasks.
- EX07-C02: the documented task-generation flow keeps candidate mutations that break one or more unit tests.
- EX07-C03: generated tasks and agent trajectories support later training experiments.
- EX07-C04: upstream requires Docker, reports development/testing on Ubuntu 22.04.4 LTS, and states it does not plan Windows/macOS support.
- Counterclaims: breaking a test does not establish that a generated task is valuable or its oracle is correct. Directly treating Roblox Studio as a Linux repair environment is unsupported. Upstream learning results do not predict local improvements.
- Witness recommendation: **adapt** execution-filtered curricula behind a project-specific runner. Keep task validity, dataset rights and independent grading separate from task generation. **Defer** model-weight training until versioned retrieval/lesson experiments establish useful data and an evaluation baseline.

### EX08 — Voyager: feedback and a growing skill library

- Primary repository: <https://github.com/MineDojo/Voyager>.
- Immutable source: <https://raw.githubusercontent.com/MineDojo/Voyager/55e45a880755d0c8c66ca7fb5fe7962ac8974f89/README.md>.
- Version: commit `55e45a880755d0c8c66ca7fb5fe7962ac8974f89`, committed **2023-07-27T07:35:42Z**.
- License identification: **MIT**, repository metadata and README; license archival remains open.
- Retrieved body: **6,737 bytes**, **2026-09-14T00:55:02.9212734Z**.
- SHA-256: `36fd5653c731f5b20189013f8552e77fefc182093f664288d6ce836e3efc111a`.
- EX08-C01: an automatic curriculum selects further exploration tasks.
- EX08-C02: a growing executable skill library stores and retrieves behaviors.
- EX08-C03: the refinement loop incorporates environment feedback, execution errors and self-verification.
- EX08-C04: the described approach learns through stored skills and model queries without requiring parameter fine-tuning.
- Counterclaims: this is Minecraft research, not evidence of Roblox production-game creation or broad secure software engineering. Self-verification is not independent verification. The README itself notes that task decomposition may be flawed. An external app's executable skills must not flow into Hive Mind merely because this research pattern stores executable code.
- Witness recommendation: **adapt abstract patterns** for outcome-driven curricula and versioned retrieval. For external projects, apply the user's more specific restriction: export only approved-shape draft abstract lessons, without automatically importing app code into Hive Mind.

### EX09 — Rojo: Roblox projects in a source-control workflow

- Primary repository: <https://github.com/rojo-rbx/rojo>.
- Immutable source: <https://raw.githubusercontent.com/rojo-rbx/rojo/a30a8ecd0f757a23c7d5be5f91e8a4d55d87b8fc/README.md>.
- Version: commit `a30a8ecd0f757a23c7d5be5f91e8a4d55d87b8fc`, committed **2026-07-06T06:15:34Z**.
- License identification: **MPL-2.0**, repository metadata and README. Do not treat tool licensing as a license for generated games or imported assets.
- Retrieved body: **2,236 bytes**, **2026-09-14T00:55:03.1403397Z**.
- SHA-256: `721bdbe7d276625be77b2c9646bbdc217f357827bece51b76412fe54cb76d1af`.
- EX09-C01: Rojo supports working with scripts/models on the filesystem and versioning projects with Git.
- EX09-C02: the README describes command-line project packaging and supported Studio/filesystem synchronization.
- EX09-C03: the README acknowledges limitations in fully automatic conversion of arbitrary existing games into Rojo projects.
- Counterclaims: packaging success is not gameplay correctness. A game repository may omit assets, Studio configuration or services necessary to recreate a live game. Tool version and actual file-format support must be probed before choosing commands.
- Witness recommendation: **adapt** Rojo through an external CLI adapter when the target project is compatible. Preserve a typed unsupported-format or missing-assets result instead of fabricating a working game.

## Official Roblox sources and E-RBX aliases

EX10–EX15 are six distinct official source documents. All six were found under `Roblox/creator-docs` commit **`cf66523ab47a08c149693f079265c0b093d21e34`**, committed **2026-09-12T10:10:29Z**. Repository metadata and its root `LICENSE` identify **CC-BY-4.0** for the documentation. This does not establish rights to other games, code, meshes, textures, audio, trademarks or third-party assets. Asset-specific exceptions and notices remain part of source intake.

The `E-RBX` family referenced in [NODES-LEARNING.md](NODES-LEARNING.md) resolves as follows. These aliases identify evidence sources, not completed capability checks.

| Alias | Source | Purpose |
|---|---|---|
| `E-RBX-SECURITY` / `E-RBX-01` | EX10 | Client/server authority, validation and abuse resistance |
| `E-RBX-TESTING` / `E-RBX-02` | EX11 | Studio runtime, multiplayer, device and network testing |
| `E-RBX-DATA` / `E-RBX-03` | EX12 | Persistence and test-data isolation |
| `E-RBX-ASSETS` / `E-RBX-04` | EX13 | Third-party asset security intake |
| `E-RBX-PUBLISH` / `E-RBX-05` | EX14 | Publication states and platform prerequisites |
| `E-RBX-PERFORMANCE` / `E-RBX-06` | EX15 | Physical-device and performance evidence |

EX09 supplies the separate Rojo tooling source. It is not an official Roblox platform document and must not be silently relabeled as one.

### EX10 — Roblox: secure the client/server boundary

- Primary URI: <https://create.roblox.com/docs/scripting/security/client-server-boundary>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/scripting/security/client-server-boundary.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `1f7e25cad876d88bbadf9d42dbd7e8fba498b394`.
- Retrieved body: **24,143 bytes**, **2026-09-14T00:55:03.4664220Z**.
- SHA-256: `d77ca5946946359537930fc62aee8816647173f0cfecab0c4b107396e10c6016`.
- EX10-C01: validate client input, permission and context on the server before consequential effects.
- EX10-C02: client-triggered server actions need appropriate server-side rate limits.
- EX10-C03: remotes and other client-triggerable instances require validation; arbitrary state mutation and unsafe dynamic loading can be dangerous.
- Counterclaims: illustrative examples are not complete security proofs for a game's economy, trading, inventory or combat rules. Client-side checks alone cannot establish server-side enforcement.
- Witness recommendation: **adopt acceptance categories** for malformed input, non-finite values, unauthorized actions, replay/spam, range/context checks and economy integrity, scoped to features the game actually has.

### EX11 — Roblox: Studio testing and supported automation surfaces

- Primary URI: <https://create.roblox.com/docs/studio/testing-modes>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/studio/testing-modes.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `8a5c8e224e80a7a48b5de69e1a143abcd8abb874`.
- Retrieved body: **20,600 bytes**, **2026-09-14T00:55:03.7043287Z**.
- SHA-256: `f758a1d4bb0046c7dbd4355d7f1b743cbeac38d05e1a7657195e6135e10c5dc5`.
- EX11-C01: Studio supports separate client/server simulations and multiplayer testing.
- EX11-C02: device/controller and network simulation support checks beyond a single desktop playthrough.
- EX11-C03: current documentation describes Studio-only programmatic services: `StudioTestService`, `StudioDeviceSimulatorService` and `VirtualInput`.
- EX11-C04: the retrieved page describes `StudioTestService` starting a server with up to eight simulated clients.
- Counterclaims: documentation availability does not establish that the installed Studio version, selected worker, account or plugin can use a service. Studio-only services do not become general headless Linux capabilities. Static Luau checks cannot stand in for executed Studio tests.
- Witness recommendation: **adapt** a capability-probed runtime adapter and record actual worker/Studio versions and supported invocation methods. Preserve unavailable-runtime evidence as a blocker for runtime-readiness claims.

### EX12 — Roblox: data stores and isolated test data

- Primary URI: <https://create.roblox.com/docs/cloud-services/data-stores>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/cloud-services/data-stores/index.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `af3decbdaa9e9cee6eae2571d635a7498c5cf0f4`.
- Retrieved body: **16,029 bytes**, **2026-09-14T00:55:03.3675172Z**.
- SHA-256: `7804d7eb5db513661d916dad3b5d4e789e2504b1be663d49532162267fe3eb64`.
- EX12-C01: persistent data is shared across a game's places and servers.
- EX12-C02: game-side data-store access is server-side.
- EX12-C03: Studio access can reach the same production stores; the documentation recommends a separate test version to avoid overwriting production data.
- Counterclaims: a fake data store can test application logic but cannot prove live persistence, throttling, concurrency or recovery behavior. A private test place inside the same universe is not automatically a separate data boundary.
- Witness recommendation: **adopt** explicit test-universe/store identity and separate persistence failure, migration and recovery acceptance criteria when the game persists player data.

### EX13 — Roblox: third-party asset vulnerabilities

- Primary URI: <https://create.roblox.com/docs/scripting/security/third-party-vulnerabilities>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/scripting/security/third-party-vulnerabilities.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `0cbca54632dbaf32a985a5f67fa7ff2b37f23567`.
- Retrieved body: **3,083 bytes**, **2026-09-14T00:55:03.5867409Z**.
- SHA-256: `b2062f7212c8aeed92788d0aa0622de468b49a0ac8d144985510e1940d68367e`.
- EX13-C01: Creator Store assets can contain malicious scripts/backdoors with server-side impact.
- Counterclaims: public availability, popularity and a clean filename do not establish security or reuse rights. Script scanning is evidence, not a guarantee that every malicious behavior is detectable.
- Witness recommendation: **adopt** explicit asset provenance, applicable rights, script inspection and controlled intake. Keep unavailable asset contents as ingestion obligations.

### EX14 — Roblox: publication is a separate operational state

- Primary URI: <https://create.roblox.com/docs/production/publishing/publish-games-and-places>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/production/publishing/publish-games-and-places.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `642c1f8d711f337ddf421b7c0e970b7024f5c452`.
- Retrieved body: **17,664 bytes**, **2026-09-14T00:55:03.9427180Z**.
- SHA-256: `38d4ef5a6de2cbf7e14db7356d3758ad692d9cd39bbca578f99b146f2a608748`.
- EX14-C01: publishing creates or updates a cloud place; it is a distinct operation from producing repository code.
- EX14-C02: audience settings distinguish private, limited and public availability.
- EX14-C03: platform account/eligibility requirements affect publication; new games are private by default.
- Counterclaims: platform rules are mutable and must be re-observed at release. Code readiness does not grant account eligibility, credentials, spending permission or public-release authority. This packet does not turn a future publication into an authorized action.
- Witness recommendation: **adopt** distinct repository-ready, runtime-validated, staging-published and public-release evidence states. Resolve actual platform prerequisites at the publication boundary.

### EX15 — Roblox: measure on the intended devices

- Primary URI: <https://create.roblox.com/docs/performance-optimization/design>.
- Immutable source: <https://raw.githubusercontent.com/Roblox/creator-docs/cf66523ab47a08c149693f079265c0b093d21e34/content/en-us/performance-optimization/design.md>.
- Version/license: the shared Roblox commit above; **CC-BY-4.0** documentation identification.
- Git blob: `9aa12dfd5dc6d24d18dee97f5921dc26eea12c25`.
- Retrieved body: **6,375 bytes**, **2026-09-14T00:55:04.0422264Z**.
- SHA-256: `d00a22aecdc0e9c937f96ba25e39a7cfc1cbd8612079aa68433e47112b0ac3fd`.
- EX15-C01: choose a baseline physical device and measure frame rate and memory during development.
- EX15-C02: Studio's device emulator is useful for aspect ratio and controls but is not accurate for physical-device memory measurement.
- EX15-C03: event-driven logic and reuse of assets can reduce repeated work and resource costs.
- Counterclaims: example draw-call/triangle numbers are illustrative, not universal acceptance thresholds. Desktop/Studio success does not establish low-end mobile performance. Performance and gameplay quality are different dimensions.
- Witness recommendation: **adopt** game-specific target-device budgets and measured regression receipts. Keep physical-device evidence incomplete when it was not collected.

## Model routing source records

### EX16 — Anthropic: current public model catalog

- Requested URI: <https://platform.claude.com/docs/en/about-claude/models/overview>.
- Observed canonical URI after redirect: <https://platform.claude.com/docs/en/models/overview>.
- Version: mutable official catalog observed on **2026-09-14 UTC**; documentation license **not established**.
- Retrieved body: **371,122 bytes**, **2026-09-14T00:55:05.3942505Z**.
- SHA-256: `bdcf0c5e10ba9e093632db0ea41e306d7e7a58b031d784e853d8fdc70ae65816`.
- EX16-C01: the catalog lists exact Claude API IDs `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5` and `claude-haiku-4-5-20251001`.
- EX16-C02: the table lists adaptive thinking and default `high` effort for Fable/Opus/Sonnet; effort is unsupported for Haiku.
- EX16-C03: the documentation says the Models API exposes model capabilities and token limits.
- Counterclaims: public catalog availability does not establish this account's entitlement, a deployed route's availability, API behavior under this adapter, or a model's ability to complete these nodes. Public model names may be aliases with versioning implications. OpenAI reasoning parameters cannot be forwarded blindly to Anthropic.
- Witness recommendation: **adapt** optional provider routes only after availability and capability checks. The routes in RUNBOOK are initial hypotheses, not tournament winners or proof of small-model sufficiency.

### EX17 — OpenAI: model selection guidance, fetched by root

- Primary URI: <https://developers.openai.com/api/docs/guides/model-selection>.
- Authority: official OpenAI documentation. Retrieval identity: `/root`.
- Source status: **fetched by root** during this handoff; content summarized in [RUNBOOK.md](RUNBOOK.md). Exact retrieval timestamp, source version, raw-body archive and byte digest were **not supplied to this packet**.
- License: **not established**. SHA-256: **not obtained**.
- EX17-C01: root's supported summary is to establish quality targets, evaluate model choices against those targets, and consider smaller models to reduce cost/latency where measured quality suffices.
- Counterclaims: general selection guidance does not establish that the host's advertised model routes are public API IDs, account-accessible, or equally capable. Specific tier assignments remain hypotheses to qualify on this workload.
- Witness recommendation: **adapt** evaluation-based routing. The source scout does not claim an independent second verification of root's summary.

### EX18 — OpenAI: building agents guidance, fetched by root

- Primary URI: <https://developers.openai.com/tracks/building-agents>.
- Authority: official OpenAI documentation. Retrieval identity: `/root`.
- Source status: **fetched by root** during this handoff; content summarized in [RUNBOOK.md](RUNBOOK.md). Exact retrieval timestamp, source version, raw-body archive and byte digest were **not supplied to this packet**.
- License: **not established**. SHA-256: **not obtained**.
- EX18-C01: the page is the official building-agents guidance used by root in the runbook's agent/model-selection discussion. This packet adds no independently extracted detailed claims beyond the linked root summary.
- Counterclaims: a provider guide does not validate the repository's implementation, prove a model's production readiness, or replace outcome evaluation. Uninspected linked pages are not ingested evidence.
- Witness recommendation: **adapt** applicable guidance only at the specificity actually documented by root. Preserve all additional source extraction and archival work as open evidence obligations.

## Expert testimony and boundaries of inference

The following are recommendations inferred from the source patterns and the owner's intent. They are not empirical findings from Hive Mind runs.

1. **Separate endpoint-example learning from blind historical evaluation.** In endpoint learning, the initial commit is input and the final snapshot may be a training reference. It cannot then count as an unseen target. In a sealed evaluation, the builder must not see final code, final README, final tests, reachable Git objects, tags, issue comments or retrieval results that reveal the target before sealing. A current README can disclose the final architecture even without source code.
2. **Endpoints do not establish the missing development history.** Multiple implementations can connect the same initial and final state. Do not invent intermediate decisions, intentions or commits. Grade observable behavior and constraints rather than textual similarity to a final diff.
3. **Do not claim public-pretraining contamination is solved by workspace isolation.** Hiding a final commit from local tools prevents a known runtime leak; it cannot erase a model's prior exposure to a public repository. Use private/newly authored held-out cohorts and disclose uncertain pretraining exposure for public cohorts. Do not describe a public holdout as certainly unseen.
4. **Start improvement with versioned lessons and evaluated retrieval.** A useful learning mechanism need not change model weights. Fine-tuning is a separate challenger with its own data rights, costs, contamination controls, regression budget and held-out promotion decision.
5. **Keep external app learning within the app.** Raw code, trajectories, secrets, embeddings, screenshots, caches and app-specific behaviors remain in that app's isolated scope. Any Hive Mind-facing export is limited to the user-authorized draft abstract lessons artifact, after structural checks and privacy screening. A language-model redaction prompt is not an isolation boundary. Canary tests should cover provider inputs, logs, error paths, artifacts, embeddings and PR text.
6. **Remove duplicated process without removing release evidence.** Give the builder a bounded work packet and freedom over local implementation order. Reuse check receipts only when relevant input, tool, environment and policy fingerprints match. Independently verify the delivery boundary, then recheck affected evidence after a repair. Eight specialist roles do not imply eight repetitions of every file check.
7. **Measure the full autonomy loop.** Observe discovery quality, validated customer outcomes, valid PR rate, interventions, successful recovery, privacy violations, regressions, total tokens/cost, elapsed-time distribution and duplicate work. More commits or faster code generation alone do not establish a better independent operating system.
8. **Production readiness needs named evidence.** Repository code, packaged artifacts, actual runtime behavior, physical-device performance, persistence recovery and public publication are different claims. Mark unavailable stages explicitly, while allowing independently useful reversible development to continue within its authority.

## Open evidence obligations

| Obligation | Current state | What closes it | Effect while open |
|---|---|---|---|
| `EO-SOURCE-ARCHIVE` | OPEN for EX01–EX18 | Preserve raw source bytes and applicable license/notices with retrieval URI/time/version/digest and append-only receipt; preserve each future version separately | This packet must not be described as complete archival source ingestion |
| `EO-ROOT-SOURCE-RECEIPTS` | EX17/EX18 root fetches recorded, exact receipts incomplete here | Root supplies exact retrieval metadata and preserved source bodies; independently verify any newly extracted atomic claims | No fabricated timestamp/hash or claim of independent witness reproduction |
| `EO-SOURCE-COMPATIBILITY` | Exact license texts, exceptions and integration decisions not fully ingested | Source-specific license/provenance review for each proposed reuse, target repository and asset | Tool/framework licenses do not authorize target-game or dataset reuse |
| `EO-ROBLOX-OWNER-INPUTS` | No owner-selected live Roblox repository, first/final SHAs or README version was supplied | Pin actual repository identity, endpoint roles, access/authority, README version and source completeness | No claim that the owner's Roblox training cohort has been assembled or evaluated |
| `EO-ROBLOX-ASSETS` | No complete owner game asset/service inventory was supplied | Preserve required asset contents/IDs, versions, rights, place configuration and external-service dependencies | No claim that source snapshots reconstruct an entire live game |
| `EO-ROBLOX-RUNTIME` | No Studio worker or platform capability was demonstrated | Probe actual supported Studio/runtime adapter, version, account and test environment, then execute required tests | Static/package checks cannot be labeled Roblox runtime verification |
| `EO-PERFORMANCE-RUNS` | No local comparator or product/performance runs occurred | Pinned comparator executions on matched tasks/models/resources with reproducible receipts and independent analysis | No winner, measured speedup, cost reduction, production pass rate or superiority claim |
| `EO-HELDOUT-CONTAMINATION` | Public-source pretraining exposure is unknown | Record cohort provenance and exposure assumptions; establish distinct private/new held-out cohorts and access isolation | Runtime sealing alone does not justify a certainly-unseen public benchmark claim |
| `EO-PROVIDER-AVAILABILITY` | Host routes/public catalog observations only | Runtime adapter capability/entitlement check and workload qualification against approved resource budgets | Routes remain proposed; unavailable models must not be silently substituted |
| `EO-COURT-DISPOSITIONS` | This file supplies scout/witness recommendations | Separately identified advocate, cross-examiner and judge preserve decisions, dissent and acceptance mappings in the handoff court record | Source author's recommendations are not self-issued independent verdicts |
| `EO-SURVEY-COVERAGE` | Targeted primary-source survey only | Expand scouting when a new material requirement or failed comparator reveals an evidence gap | No claim of exhaustive source coverage or global architectural optimality |

These obligations constrain the associated claims and dependent operations. They do not ask the owner to repeat authorization for unrelated routine reversible work, and they do not justify repeated unchanged checks.
