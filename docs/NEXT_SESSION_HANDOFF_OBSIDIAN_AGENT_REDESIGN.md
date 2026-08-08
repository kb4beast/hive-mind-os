# Hive Mind OS — Next-Session Handoff

## Obsidian Workbench and Constitutional Agent-System Redesign

**Prepared:** 2026-07-28

**Repository:** `C:\Repos\HiveMind\hive-mind-os`

**Purpose:** This is a copy-ready prompt for the next implementation session. It
preserves the previous handoff, corrects its now-stale pull-request state, and turns
the requested Obsidian, agent, skill, prompt, discovery, and autonomous-extension
work into an evidence-driven delivery program.

---

## Start of copy-ready prompt

You are continuing work on Hive Mind OS in:

```text
C:\Repos\HiveMind\hive-mind-os
```

Your job is to harden the system without losing existing functionality. Work through
the repository's courtroom process in `AGENTS.md`. Treat this document as a mission
brief, not as evidence that any unimplemented capability already exists.

Do not merely rewrite descriptions or make prompts longer. Build a coherent,
nonduplicated, testable agent system whose roles, skills, prompts, tools, memory,
workflows, host projections, and extension lifecycle have clear boundaries and can
evolve safely.

### Governing documents

Read these before changing implementation:

1. `AGENTS.md`
2. `docs/architecture/HARDENED_VISION_CONTRACT.md`
3. `docs/architecture/CONGLOMERATED_SYSTEM.md`
4. `docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md`
5. `docs/architecture/ADR-016-GOVERNED-EXTENSION-PACKAGES.md`
6. `docs/architecture/ADR-017-INERT-SKILLS-TOOLS-AND-HOST-EVIDENCE.md`
7. `src/hive_mind_os/founding_docket.py`
8. `src/hive_mind_os/vision.py`
9. `src/hive_mind_os/additional_video_docket.py`
10. All still-open source-ingestion records, appeals, blockers, and dissent that
    affect this work.

Preserve the constitutional boundaries in those documents. Capability does not
expand authority. No agent, package, prompt, skill, host adapter, or challenger may
approve or promote itself.

---

## 1. Correct current state before doing new work

The previous handoff captured this delivery state:

```text
Branch: codex/harden-extensible-architecture
Feature commit: 5689cd616d2a99d0f4ab1c05f7aa4a63f8b946f2
PR: #27 — Harden extensible agent architecture

The change added:
- content-addressed, inert extension packages;
- individual agent, skill, tool, workflow, prompt, and host-profile resources;
- ADR-016 and ADR-017;
- stronger prompt controls, appeals, quarantine, rollback locks, and provenance;
- OODA, War Room, role-facade, and wheel-packaging hardening.

The earlier continuation plan was:
1. Verify the branch and PR head.
2. Run a fresh full test suite.
3. Run Ruff and Pyright.
4. Rebuild and install the wheel and verify all 68 package resources.
5. Obtain an independent Judge disposition under AGENTS.md, ADR-016, and ADR-017.
6. Update architecture records only with reproduced evidence.
7. Keep the PR in draft unless the evidence supports promotion.
```

That historical handoff must be retained, but its PR status is now stale.

### Authoritative correction as of 2026-07-28

- PR [#27](https://github.com/kb4beast/hive-mind-os/pull/27) is **merged**, not
  draft.
- The merge commit on remote `main` is
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`.
- The local worktree was still on
  `codex/harden-extensible-architecture` at feature commit `5689cd6` when this
  handoff was written.
- This handoff file itself was untracked on that already-merged feature branch when
  created. Preserve it before switching branches, then add it intentionally through a
  new branch and pull request.
- Begin new implementation from an updated `main`, on a new `codex/` branch.
- Do not reuse the merged feature branch for the next delivery.

### Immediate red CI blocker

The GitHub unit-test jobs for Python 3.11, 3.12, and 3.14 failed after the merge.
The workflow runs:

```text
python -m unittest discover -s tests -v
```

but these newly merged test modules import or use `pytest`:

```text
tests/test_host_capability_profiles.py
tests/test_ooda_workflow.py
tests/test_package_catalog.py
tests/test_package_extensions.py
```

CI installs the local package without declaring pytest as a test dependency, so the
observed failure is:

```text
ModuleNotFoundError: No module named 'pytest'
```

Fix this test-runner/dependency contract mismatch before the larger redesign. Court
the alternatives:

1. preserve the existing zero-extra-dependency `unittest` CI contract and convert
   the four tests; or
2. explicitly declare and pin the test dependency, update the documented test
   contract, and use pytest as the intended CI runner.

Do not hide the problem by depending on an undeclared ambient pytest installation.
Make this a small, isolated repair with its own verification and pull request. Require
that repair PR to be green before agent or Obsidian implementation begins.

Also open a process obligation for how PR #27 reached `main` while all three unit-test
matrix jobs were red. Inspect required-check and branch-protection configuration. If
the repair is within repository authority, harden and test it. If it requires GitHub
administration not currently granted, preserve a concrete external action request;
do not pretend the repository change alone prevents another red merge.

### Required baseline commands and receipts

First inspect, fetch, and reproduce. Do not assume this document is newer than the
repository or GitHub:

```powershell
git status --short --branch
git fetch origin
git log --oneline --decorate -5 origin/main
gh pr view 27 --repo kb4beast/hive-mind-os
gh pr checks 27 --repo kb4beast/hive-mind-os
```

After preserving any user-owned work, start from current `origin/main` on a new
branch. Then:

1. reproduce the CI failure in the same dependency environment and with the exact
   CI command;
2. repair the runner/dependency contract;
3. run the repository's complete deterministic test contract;
4. run Ruff;
5. run Pyright against the intended source boundary;
6. build a clean wheel, install it into a clean environment, and verify all expected
   package resources and digests;
7. verify the Git worktree did not change during tests;
8. retain commands, versions, outputs, exit codes, commit SHA, environment, and
   artifact digests as receipts.

Do not use a focused passing test set as proof that the exact full suite passed.

### Truth boundary that still applies

Until separately proven:

- no Codex, Claude Code, Hermes, Obsidian, or other executable host adapter is
  supported;
- the current host profiles are declarative and unverified;
- package skills and tools are inert data and are not executable autonomous
  extensions;
- `hive-core` remains quarantined;
- challenger evaluation can create a pending appeal but cannot self-promote;
- ADR-017 still requires an independent Judge receipt;
- ADR-016 still requires genuinely separate Steward review;
- the source docket is not release-ready;
- seven admitted videos remain incompletely pinned or ingested;
- the exact intended “Armory” source and semantics remain unconfirmed;
- source, vision-video, Armory, host-support, production, release, autonomy, and
  superiority completeness must not be claimed.

At the time this handoff was researched, the audit reported 23 sources, 84 atomic
claims, 84 decisions, `release_ready = false`, and 113 audit issues. Reproduce these
numbers at the new commit rather than copying them into new evidence as timeless
facts.

---

## 2. The product vision to implement

Hive Mind OS should become an evidence-driven operating system in which independent,
specialized agents can:

- discover problems and opportunities;
- design, build, validate, integrate, maintain, and improve software;
- resume routine reversible work without a person restating context;
- suggest genuinely new ideas and test them;
- add candidate agents, skills, tools, workflows, and host projections through a
  governed extension process;
- preserve a durable, navigable memory of every idea, source, decision, run, failure,
  handoff, change, experiment, and outcome;
- expose that memory through an Obsidian-compatible brain while keeping the data open,
  local-first, provider-neutral, and usable without Obsidian;
- measure model and agent resource use at call, step, role, idea, court, mission, and
  repository scope;
- learn from outcomes, failures, dissent, and unexpected discoveries;
- operate across replaceable model and host providers;
- never confuse generated activity, novelty, or self-preservation with customer
  value.

“Autonomous” means routine, reversible, in-policy work can continue through explicit
authority, leases, budgets, evidence, checkpoints, and rollback. It does not mean
unbounded execution, silent policy mutation, self-approval, self-promotion, credential
acquisition, or replication.

The immediate design goal is a strong canonical agent system, not eight paragraphs
with different names.

---

## 3. Open separate court cases

Do not collapse this vision into one generic “improve agents” case. At minimum, docket
these atomic requirements separately:

1. Obsidian repository-as-vault workbench.
2. Deterministic Obsidian projections if the no-code workbench is insufficient.
3. Optional governed Obsidian-to-OS intake.
4. Automatic freshness and explicit synchronization semantics.
5. Removal of duplicated role, agent, skill, and prompt authority.
6. Rich canonical contracts for all eight roles.
7. Explorer multidisciplinary discovery.
8. Explorer proactive repository and external research.
9. Explorer bug and failure discovery.
10. Explorer serendipity capture.
11. Explorer cross-domain synthesis.
12. Exact and semantic idea deduplication.
13. Reusable, typed, independently testable skills.
14. Deterministic prompt composition.
15. Generated, nonauthoritative host projections.
16. Equivalent behavioral rigor for the other seven roles.
17. Safe autonomous proposal and addition of new agents or skills.
18. OODA and War Room integration with the new role system.
19. Armory semantics and source-ingestion obligation.
20. Portable operation across Codex, Claude Code, Hermes, and future hosts.
21. Open, per-repository and federated long-term memory.
22. Obsidian as a first-class brain, navigation, review, and knowledge-gardening
    surface.
23. Complete work-history coverage and replay.
24. Granular provider-normalized token and cost telemetry.
25. Purpose attribution across active champions, challengers, advocates,
    cross-examiners, judges, and neutral work.
26. Agent effectiveness and marginal-value measurement.
27. Loop, retry-storm, context-churn, and stalled-progress detection.
28. Budget circuit breakers and evidence-bound quarantine.
29. Champion/challenger evaluation that prevents leakage while allowing either side
    to fail.
30. Memory utility, contamination, staleness, privacy, and retrieval-quality
    measurement.
31. Multi-repository federation and safe self-hosting when Hive Mind OS runs on
    itself.

For every material case:

- preserve the original request and source provenance;
- extract atomic claims and counterclaims;
- assign a Clerk and Advocate;
- assign a separate Cross-Examiner;
- obtain relevant independent Expert Witness testimony;
- use a Judge distinct from the Explorer, Architect, Builder, affected champion, and
  other acting identities;
- issue `adopt`, `adapt`, `defer`, `reject`, or `quarantine`;
- retain dissent, alternatives, source gaps, and appeals;
- bind adopted work to acceptance tests, outcome metrics, ownership, rollback, code
  receipts, and versioned artifacts.

Do not invent the content of unavailable videos, repositories, or the unidentified
Armory source. Record a blocking evidence obligation instead.

---

## 4. Obsidian: easiest integration first

Treat “run with Obsidian” as three connected needs:

1. use Obsidian as the first-class human brain and memory interface for everything
   Hive Mind OS learns and does;
2. keep the brain's durable data in open, inspectable formats so the OS works without
   Obsidian and for any public or private repository; and
3. optionally connect governed human-authored requests and automation to the running
   OS.

Obsidian is not initially a Python execution host. It is the cognitive workbench:
navigation, recall, relationships, review, dashboards, and human/agent collaboration.
The underlying memory engine and append-only ledger remain the authority. Obsidian is
the rich brain interface over that memory, not a proprietary requirement or an
unreviewed execution path.

### Five-minute beginner setup — no importer or code required

The repository already contains Markdown, so do not build or install an importer
first. Before opening it:

- make sure important work is committed or otherwise backed up;
- inspect `git status`;
- inspect any existing `.obsidian/` configuration and installed plugin files;
- begin in Obsidian's Restricted Mode with community plugins disabled.

1. Install and open Obsidian.
2. Select **Manage vaults**.
3. Select **Open folder as vault**.
4. Choose:

   ```text
   C:\Repos\HiveMind\hive-mind-os
   ```

5. Use Obsidian's file browser, links, search, tags, backlinks, and graph to browse
   the repository's Markdown knowledge.

Open the repository root rather than only `docs/`. Important Markdown also exists in
the root, `evidence/`, and `gpt_sources/`.

Obsidian is the knowledge view, not the code IDE or Python runtime. It recognizes
[specific file formats](https://obsidian.md/help/file-formats); source and JSON files
will not behave like normal Obsidian notes. Use the code tools for implementation.
Start with the vault read-mostly and inspect `git status` after Obsidian edits or note
moves.

This works because an Obsidian vault is an ordinary local folder containing Markdown.
There is no duplicate copy and no import command to rerun. See the official
[data-storage](https://obsidian.md/help/data-storage),
[vault-management](https://obsidian.md/help/Files%20and%20folders/Manage%20vaults),
and [Markdown import](https://obsidian.md/help/import/markdown) documentation.
For a one-off Markdown import, drag the file into Obsidian's file explorer or copy it
into the vault folder. That still does not require the Importer plugin.

### What stays up to date “automagically”

Local file changes are automatic. When Codex, an IDE, Git, or Hive Mind OS writes a
Markdown file inside this local repository, Obsidian updates its view from the same
file. Do not add a duplicate synchronization service or file watcher for this.

Remote GitHub changes are different: Obsidian does not pull GitHub. Use `git pull`, or
fetch followed by an explicit merge, rebase, checkout, or other reviewed worktree
update. A fetch alone does not change the files Obsidian displays. Once Git writes the
changes into the local folder, Obsidian sees those local changes.

If the view becomes stale, use Obsidian's cache-rebuild option under **Settings →
Files and links**.

Obsidian application updates are separate from note freshness. Desktop updates can
apply after restart when automatic updates are enabled, while periodic installer
updates still require downloading and running a new installer. Community plugins do
not update automatically; review and initiate their updates explicitly. See the
official [update](https://obsidian.md/help/updates) and
[community-plugin](https://obsidian.md/help/community-plugins) guidance.

### `.obsidian` configuration decision

Opening the repository creates a `.obsidian/` directory. The repository did not ignore
that directory when this handoff was prepared. Inspect its files before committing
anything. Court and document one of these policies:

- keep all Obsidian configuration local;
- ignore only volatile machine/workspace state such as `workspace.json` and
  `workspaces.json`; or
- commit a deliberately curated, portable team configuration while excluding
  volatile and machine-specific files.

Do not accidentally commit a person's workspace layout, local paths, secrets, plugin
state, or caches.

### Sync choices are not interchangeable

- **Git** supplies version history and GitHub exchange. Standard Git still requires
  explicit commit, push, fetch, and pull actions.
- **Obsidian Sync** is an optional paid service for synchronizing a vault across
  devices. It does not run Hive Mind OS, replace GitHub, or by itself constitute a
  complete backup. See the official
  [Sync introduction](https://help.obsidian.md/Obsidian%20Sync/Introduction%20to%20Obsidian%20Sync).
  Its selective settings may omit source-code or other unsupported file types unless
  **Sync all other types** is enabled. Keep Git authoritative for the complete
  codebase and review the official
  [Sync settings](https://obsidian.md/help/sync/settings).
- **Obsidian Importer** is for migrating other formats and is unnecessary for this
  Markdown repository.
- **Obsidian Git** is a third-party community plugin. Do not require or install it by
  default. It can add another automated Git writer/client changing the same worktree
  and branch.
- Community plugins execute third-party code and require source, security, maintenance,
  license, authority, and update review before admission.

Do not run multiple synchronization systems against one vault without conflict,
recovery, and duplicate-update tests.

### Add the open brain, not an unnecessary Obsidian plugin

Opening the repository as a vault already satisfies local reading, navigation, and
automatic refresh. The new requirement to remember every run, idea, decision, agent,
resource, and outcome demonstrates a real gap: implement the open memory ledger and
deterministic brain projection. Do not confuse this required memory work with a need
for a proprietary Obsidian plugin.

A possible future command shape is:

```text
hive-mind brain project --repo <path> --vault <path>
hive-mind brain project --repo <path> --vault <path> --incremental
hive-mind brain watch --repo <path> --vault <path>
```

These names are design candidates, not approved interfaces.

A required safe projection should generate open Markdown views for:

- War Room and mission status;
- agent activity and handoffs;
- OODA phase and decision latency;
- ideas, duplicates, refinements, contradictions, and appeals;
- sources, claims, evidence, decisions, experiments, and dissent;
- risks, blockers, ownership, health, incidents, and recovery.

Every generated note must:

- be derived from canonical append-only state;
- be deterministic and safe to regenerate;
- carry a stable record ID, source references, run ID, timestamp, digest, and status;
- clearly say that it is generated;
- never become a competing authority;
- avoid secrets and unsafe content;
- handle rename, tombstone, deletion, interruption, restart, and partial failure;
- prevent an exported note from being re-ingested as a new idea;
- be written through a staging area and an atomic replace guarded by the expected prior
  digest, so concurrent edits fail visibly instead of being overwritten;
- live in a generated namespace that humans treat as read-only; and
- route human annotations, corrections, and proposals through a separate governed
  intake record linked to the generated object.

If a person edits a generated note while Obsidian is open, the projector must detect
the digest conflict, preserve both versions, emit a receipt, and stop that record's
projection until the conflict is resolved. Regeneration must never silently destroy a
human edit.

### Optional Obsidian-to-OS intake

Only add an `Inbox/` or import command if the user actually needs to author requests
inside Obsidian.

Any intake must be:

- separate from export;
- explicit and dry-runnable;
- schema-validated;
- provenance-recorded;
- idempotent and duplicate-aware;
- treated as untrusted human input;
- subject to policy, authority, courtroom, and source checks before action;
- unable to execute arbitrary Markdown, links, commands, code blocks, or plugin output;
- reversible, with visible rejection reasons.

Obsidian's official [URI interface](https://help.obsidian.md/Extending%2BObsidian/Obsidian%2BURI)
may be useful for controlled navigation or note creation. Investigate official CLI or
headless-sync capabilities only if a real requirement demands them. Do not call
Obsidian a supported execution host until a versioned adapter passes conformance,
security, recovery, and compatibility tests.

### Obsidian acceptance criteria

- A beginner can open the repository as a vault in under five minutes.
- Existing Markdown is readable without migration.
- A local file edit appears without manual import.
- A Git pull is correctly explained as the prerequisite for remote changes.
- No plugin is required for the default workflow.
- The `.obsidian` policy prevents accidental machine-specific commits.
- If projections are built, initial and incremental output is deterministic.
- Generated views never mutate canonical OS state.
- Restart, rename, delete/tombstone, Windows path, conflict, and stale-cache behavior
  are tested.
- If intake is built, malformed, duplicated, injected, and unauthorized notes fail
  closed with append-only receipts.
- Freshness and conflict behavior are objectively measurable.

### Obsidian source-provenance obligation

These official help pages were retrieved on 2026-07-28 for this planning handoff:

| Official page | URL |
| --- | --- |
| How Obsidian stores data | <https://obsidian.md/help/data-storage> |
| Manage vaults | <https://obsidian.md/help/Files%20and%20folders/Manage%20vaults> |
| Import Markdown files | <https://obsidian.md/help/import/markdown> |
| Accepted file formats | <https://obsidian.md/help/file-formats> |
| Update Obsidian | <https://obsidian.md/help/updates> |
| Community plugins | <https://obsidian.md/help/community-plugins> |
| Introduction to Obsidian Sync | <https://obsidian.md/help/Obsidian%20Sync/Introduction%20to%20Obsidian%20Sync> |
| Sync settings and selective syncing | <https://obsidian.md/help/sync/settings> |
| Obsidian URI | <https://obsidian.md/help/Extending%2BObsidian/Obsidian%2BURI> |

This handoff did not capture byte digests, immutable page versions, or an adjudicated
documentation-license/terms record. Before using these pages as admitted implementation
evidence, the Explorer/Clerk must preserve those items where obtainable, quote within
license and copyright limits, extract atomic claims and counterclaims, and record any
unavailable version or digest as an explicit evidence obligation.

### Build an Obsidian-compatible brain, not an Obsidian-locked brain

The goal is bigger than exporting a status dashboard. Hive Mind OS needs durable
institutional memory, and Obsidian should be the best first human interface to it:

```text
append-only event, evidence, and outcome ledger
                  |
                  v
       typed open memory-object contract
                  |
                  v
     deterministic Markdown/YAML projection
                  |
       +----------+-----------+
       |          |           |
       v          v           v
    Obsidian    any editor    OS query/retrieval API
       |
       +-> Properties, Bases, Search, Backlinks, Graph, Canvas, URI/CLI
       ^
       |
validated, untrusted Inbox proposals
```

Obsidian should feel like the OS's brain because it can recall and relate everything.
The actual durable brain is the open memory contract and ledger. This distinction is
required because Hive Mind OS is open source while the Obsidian application is
externally owned software. No paid Obsidian service, account, proprietary database, or
community plugin may be required to run the OS or recover its memory.

The default must remain local-first and useful through a CLI, ordinary filesystem,
Git, Markdown-capable editor, and machine-readable export. Obsidian adds a superior
cognitive workbench without becoming a constitutional dependency.

### Memory planes

Design memory as several related planes rather than one large transcript:

| Memory plane | What it remembers | Examples |
| --- | --- | --- |
| Working memory | The bounded state needed to continue current work | objective, OODA phase, plan, open blockers, current evidence, next action |
| Episodic memory | What happened during each run | observations, agent episodes, tool actions, errors, retries, handoffs, receipts |
| Semantic memory | Durable facts, concepts, and relationships | sources, claims, architecture concepts, domain knowledge, entity links |
| Procedural memory | How governed work is performed | skills, playbooks, runbooks, recovery procedures, evaluation protocols |
| Prospective memory | What must happen later | deferred cases, review dates, revalidation triggers, dependency wakeups |
| Decision memory | Why a choice was made | alternatives, testimony, dissent, verdict, assumptions, rollback |
| Opportunity memory | Every idea and its lifecycle | Explorer proposals, duplicates, refinements, experiments, outcomes |
| Counterfactual memory | What failed or was rejected and why | losing designs, rejected ideas, failed champions, incidents, negative results |
| Social/organizational memory | Who acted and who is accountable | roles, identities, independence, ownership, delegation, review |
| Evaluation memory | How quality and value were measured | cohorts, holdouts, metrics, budgets, champion/challenger outcomes |
| Resource memory | What execution consumed | tokens, cost, time, cache, tools, compute, retries, waste classifications |
| Governance memory | What was allowed, denied, or quarantined | leases, policy decisions, authority, quarantine, appeals, rehabilitation |

Do not save private hidden chain-of-thought as memory. Preserve concise reasoning
summaries, evidence, alternatives, decisions, receipts, and provider-reported reasoning
token counts where available. Memory must explain what supported a decision without
requiring or exposing hidden model reasoning.

### Work-history coverage

“Remember all work” means every material object or transition has an append-only event
and a navigable memory record. In addition, every Explorer-generated candidate must
emit an append-only `IdeaEncounter` or `ProposalAttempt` before filtering—even when it
is duplicative, abandoned, trivial, invalid, non-material, or policy-blocked. Link each
encounter to a canonical opportunity, an earlier duplicate, or an explicit disposition
and reason. Cover at least:

- repository identity, remote, branch, commit, worktree, and target cutoff;
- OS build, configuration, policy, model, prompt, agent, skill, and tool versions;
- missions, desired outcomes, plans, budgets, OODA transitions, and checkpoints;
- every agent episode and cross-agent handoff;
- Explorer observations, bugs, ideas, cross-domain bridges, duplicates, refinements,
  contradictions, appeals, and serendipitous findings;
- sources, versions, digests, licenses, atomic claims, counterclaims, and evidence
  obligations;
- courtroom participants, testimony, conflicts, dissent, verdicts, and appeals;
- architecture options, ADRs, threats, migrations, and rollback plans;
- tool intents, policy decisions, capability leases, executions, results, and receipts;
- file changes, tests, builds, packages, branches, commits, pull requests, reviews, and
  releases;
- incidents, loops, quarantines, recoveries, and root-cause analyses;
- hypotheses, experiments, benchmarks, champions, challengers, and promotion history;
- token, cost, latency, context, memory, tool, and effectiveness observations;
- user feedback, adoption, business/customer outcomes, and later reversals;
- unresolved questions, known unknowns, blind spots, stale assumptions, and next
  actions.

Coverage must be testable. Emit a memory-coverage report for each mission showing which
required record types exist, which are not applicable, and which are missing. A summary
note cannot substitute for required receipts.

### Portable memory-object envelope

Give every object a stable opaque ID and a versioned machine schema. Its Markdown
projection should use small atomic YAML properties such as:

```yaml
---
schema_version: hive-memory/v1
record_id: IDEA-01J...
record_type: opportunity
tenant_id: TENANT-01J...
project_lineage_id: PROJECT-01J...
repo_instance_id: REPO-01J...
fork_parent_id: REPO-01H...
subject_commit: abcdef1234
controller_build_id: sha256:...
run_id: RUN-01J...
parent_run_id: RUN-01J...
agent_id: explorer-v2
role: explorer
created_at: 2026-07-28T18:00:00Z
observed_at: 2026-07-28T17:59:00Z
status: proposed
disposition: pending
authority: read-only
sensitivity: public
source_ids:
  - SRC-123
related_ids:
  - IDEA-456
supersedes: []
content_digest: sha256:...
generator_version: hive-brain-projection/v1
projection_cursor: "event:000012345"
is_generated: true
is_quarantined: false
is_self_hosted: false
---
```

The exact schema and storage require adjudication. Obsidian Properties support useful
atomic strings, links, lists, numbers, checkboxes, dates, and timestamps, but not
arbitrarily nested machine state. Keep rich nested data and append-only transitions in
the canonical ledger; project only safe query fields and readable content into notes.

Never use mutable note titles or paths as identity. A rename must not break the
record's stable ID, provenance, or relationships.

### Candidate portable memory pack

Court the exact directory names. A candidate visible, portable structure is:

```text
hive-mind/
  HOME.md
  repositories/
  missions/
  runs/
  agents/
  ideas/
  sources/
  claims/
  courts/
  decisions/
  architecture/
  changes/
  tests/
  experiments/
  incidents/
  quarantines/
  handoffs/
  learnings/
  metrics/
  dashboards/
  canvases/
  bases/
  archive/
```

An `inbox/` directory is conditional, untracked by default, and present only when the
governed intake workflow is adopted. It is not a place for secrets; sensitive intake
belongs in the protected store outside the vault. Only validated and sanitized
admitted outcomes may enter the public Git-reviewable pack.

Do not automatically choose a hidden `.hive-mind/` folder for Obsidian-facing memory:
Obsidian Sync excludes hidden folders other than its configuration directory. A hidden
folder or `.gitignore` entry is not a privacy control or a backup. Default sensitive
canonical state outside the repository and Obsidian vault, with access control,
encryption where appropriate, retention, and tested backup/restore. Use an
allowlist-based projector for the visible memory pack:

```text
<external-state-root>/<tenant>/<repo-instance>/  # protected canonical sensitive state
hive-mind/                                      # allowlisted, sanitized public projection
```

This is a candidate boundary, not an approved layout. Compare repository churn,
sensitivity, merge conflicts, public-history value, storage size, Sync behavior, and
rollback before adoption.

### Obsidian-native brain surfaces

Use core, documented functionality first:

- **Properties:** typed, atomic note metadata for stable IDs, state, ownership,
  timestamps, confidence, cost, and links.
- **Bases:** generated database-like tables, lists, cards, filters, formulas, groups,
  and summaries over note properties. Create views for the idea pipeline, court docket,
  quarantines, agent scorecards, token budgets, stale evidence, and memory health.
  Treat `.base` files as optional query views, never enforcement.
- **Backlinks and Graph:** navigate
  `source -> claim -> idea -> case -> decision -> change -> test -> outcome`. Use
  missing links, orphans, and disconnected clusters as investigation signals, not
  proof.
- **Canvas:** generate War Room, OODA, courtroom, architecture, incident, causal, and
  champion/challenger maps. Use file-backed nodes so important items participate in
  backlinks. JSON Canvas is an open MIT-licensed format and should be preferred for
  portable spatial views.
- **Search:** saved searches for blocked claims, unresolved sources, quarantined
  proposals, untested changes, stale assumptions, and ideas without measured outcomes.
- **Daily operational journal:** chronological links to all runs, discoveries,
  decisions, failures, and handoffs for a day. The journal is a projection/index, not a
  substitute for individual records.
- **Templates:** stable human capture forms for ideas, sources, bugs, dissent,
  experiments, incidents, feedback, and appeals.
- **Aliases and unlinked mentions:** candidate signals for idea/entity deduplication.
  They may suggest a relation but cannot decide it.
- **URI and CLI:** optional navigation, search, note creation, and controlled property
  operations. Direct atomic filesystem output remains the required baseline.
- **Web Clipper:** optional open-source research inbox for Explorer. All clips remain
  untrusted until source capture and courtroom intake succeed.

Obsidian Search indexes notes and canvases, not arbitrary JSON event stores. Generate
safe summary notes or use the OS query API; do not assume raw telemetry is searchable
in the vault.

### Required brain dashboards

Provide generated HOME and Bases/Canvas views for:

- active missions and next actions;
- all Explorer ideas, grouped by new, duplicate, refinement, reinforcement,
  contradiction, complement, adopted, rejected, deferred, and quarantined;
- idea families showing evidence, advocates, challengers, decision, implementation,
  and outcome;
- source and claim coverage;
- courtroom cases, dissent, appeals, and aging;
- agent identity, version, health, capability, token budget, effectiveness, and
  quarantine;
- current champion and challengers for prompts, skills, agents, tools, and workflows;
- OODA state and loops;
- test, build, delivery, rollback, and release readiness;
- memory health, stale facts, unresolved links, orphans, dead ends, contradictions,
  and unowned records;
- token/cost/value trends and budget anomalies;
- incidents, recoveries, and recurring root causes;
- deferred work whose premise or dependency has changed.

### Memory write and read governance

Use an explicit directionality model:

- **Canonical runtime -> brain:** deterministic, idempotent projection with cursor,
  digest, and generated marker.
- **Human/Obsidian -> Inbox:** untrusted proposal only.
- **Inbox -> canonical runtime:** explicit validated import with dry run, policy,
  duplicate check, source capture, and receipt.
- **Brain -> agent context:** governed retrieval packet with query, selected IDs,
  ordering, cutoff, sensitivity decision, and digest.

Record exactly which memory IDs were presented to each agent. This makes memory
influence auditable and enables later tests of whether memory improved work or leaked a
held-out answer.

Quarantined memory is excluded from ordinary retrieval. Access must state a permitted
forensic or rehabilitation purpose and produce a receipt. Rejected and dissenting
memory remains available for authorized learning; rejection is not deletion.

### Memory maintenance and “knowledge gardening”

Add bounded Steward/Curator skills rather than a self-authorizing ninth role:

- detect stale facts, invalid links, orphan records, duplicate identities, schema
  drift, and missing outcomes;
- schedule revalidation when a source, dependency, market fact, benchmark, or
  assumption changes;
- consolidate summaries while preserving originals and derivation;
- archive cold records without deleting append-only history;
- revive rejected or deferred ideas when their blocking premise changes;
- surface contradictions instead of overwriting the losing side;
- measure retrieval quality, freshness, privacy, and cost;
- keep public projections sanitized and private evidence separated.

Use a “memory nutrition” score for important records: evidence, counter-evidence,
owner, disposition, experiment, outcome, last verification, sensitivity, and rollback.
Do not optimize this score as a vanity target; it is a missing-field diagnostic.

### Serendipitous brain capabilities to court

- **Random collision lab:** sample two or more unrelated notes and ask Explorer for a
  causal, falsifiable bridge. Record unsuccessful combinations as well as useful ones.
- **Dissent resurrection:** reopen a rejected idea when a dependency or assumption
  changes materially.
- **Blind-spot map:** compare what each role retrieved, used, and ignored. Missing
  cross-role links become research candidates.
- **Counterfactual replay:** rerun held-out episodes with and without selected memories
  to measure real memory lift.
- **Memory value attribution:** connect retrieved records to later decisions and
  outcomes while distinguishing correlation from causal evidence.
- **Memory decay without deletion:** reduce stale material's retrieval priority,
  require revalidation, or quarantine it while preserving provenance.
- **Quarantine observatory:** show cause, scope, descendants, exposure attempts,
  review date, and rehabilitation test.
- **War Room playback:** reconstruct any run as a time-sequenced Canvas containing
  OODA transitions, agents, dissent, loops, retries, budget use, and outcomes.
- **Decision time travel:** reconstruct what the OS could know at a particular commit
  and timestamp, preserving point-in-time evaluation.
- **Failure-pattern library:** link incidents across repositories by mechanism without
  leaking private code or tenant data.
- **Research-to-skill pipeline:** identify repeated successful procedures as candidate
  skills, but require the normal challenger and independent promotion path.

### Multi-repository operation

The OS must work for any repository:

1. assign separate stable identities for project/lineage, repository instance or fork,
   and tenant; reconcile ordinary clones without collapsing forks, mirrors with
   independent histories, or private tenants;
2. bind every record to lineage, repository instance, tenant, and commit identity;
3. support a safe-to-publish memory pack committed with the repository;
4. support a separate access-controlled store outside the repository/vault for
   sensitive traces, prompts, identifiers, and user data;
5. support one vault per repository as the beginner default;
6. optionally generate a portfolio vault that federates sanitized, read-only
   projections from many repositories;
7. prevent one repository or tenant from retrieving another's private memory;
8. use standard relative Markdown links in committed memory; never use mutable paths,
   Obsidian Wikilinks, block references, or cross-vault links as canonical identity.

Do not create vaults inside vaults. Obsidian warns that nested vault links may update
incorrectly. Cross-vault internal links do not provide portable federation. A portfolio
vault should materialize sanitized local records or use clearly nonauthoritative deep
links, not turn repository vaults into nested authorities.

### Safe self-hosting when Hive Mind OS runs on itself

Record both controller and subject identity:

```text
controller_os_build_id
controller_instance_id
tenant_id
project_lineage_id
repo_instance_id
subject_commit
parent_run_id
observation_epoch
self_host_depth
origin_record_id
```

Prevent recursive self-observation and feedback:

- generated brain notes are not new external evidence;
- projection events do not trigger another projection as novel work;
- telemetry about telemetry does not recursively create unbounded telemetry;
- Explorer excludes generated memory/projection directories from novelty scans by
  default;
- self-analysis requires an explicit target boundary and maximum depth;
- identical origin/digest/idempotency keys collapse repeated ingestion;
- parent/child run and hop limits prevent delegation ping-pong;
- a new observation epoch is required before the OS treats changed self-state as a new
  subject.

The OS may improve itself only through the same versioned challenger, independent
evaluation, authority, and rollback process used for another repository.

### Candidate brain commands

Court names and contracts before implementation:

```text
hive-mind brain init --repo <path>
hive-mind brain project --repo <path> --vault <path>
hive-mind brain watch --repo <path> --vault <path>
hive-mind brain import --inbox <path> --dry-run
hive-mind brain query --repo <id> --as-of <commit-or-time>
hive-mind brain replay --run <id>
hive-mind brain doctor --repo <path>
hive-mind brain federate --config <path>
```

Every command needs typed output, idempotency, interruption recovery, safe path
handling, policy, receipts, and a no-Obsidian execution path.

### Expected beginner experience while the OS runs

1. The user opens the repository folder as an Obsidian vault once.
2. Hive Mind OS records canonical events and updates the open brain projection.
3. Obsidian detects those local file updates automatically; the user does not reimport
   anything.
4. A new Explorer idea appears as its own linked note with evidence, related/duplicate
   ideas, court status, experiment, implementation, and outcome.
5. Each agent's page and scorecard update with work performed, token/cost usage,
   effectiveness, loops, and quarantine state.
6. HOME, Bases, Graph, and Canvas views show current missions and institutional
   knowledge.
7. Clicking a run reconstructs its timeline and links to exact commits, tests,
   decisions, receipts, and memory used.
8. Human ideas entered through the Inbox remain visibly pending until validated.
9. Git remains the versioned exchange mechanism for public brain files. Remote changes
   appear after a reviewed worktree update.

### Brain acceptance criteria

- Every material mission object has a stable memory record or explicit
  not-applicable disposition.
- Every Explorer-generated candidate has an `IdeaEncounter`, including filtered,
  duplicate, abandoned, invalid, non-material, and policy-blocked candidates.
- Every developed Explorer opportunity remains findable through stable ID, aliases,
  related ideas, sources, court, implementation, and outcome.
- A second exploration links duplicate evidence rather than producing a disconnected
  duplicate note.
- A clone can read the public memory pack with no account, paid service, plugin, or
  network.
- Obsidian can display and query the pack using core functionality.
- Another Markdown/YAML/JSON-capable tool can use the same underlying records.
- Generated notes are deterministic, content-addressed, marked, and safe to rebuild.
- Human edits cannot silently mutate canonical state.
- Private and public memory are separated and tenant isolation is tested.
- Memory retrieval has a sealed manifest and can be replayed.
- Quarantined records are excluded by default.
- Self-hosting does not produce projection, idea, telemetry, or delegation loops.
- Point-in-time queries cannot see future commits or later decisions.
- Restart, concurrent writers, rename, schema migration, partial projection,
  corruption, and rollback are tested.
- Memory usefulness, staleness, coverage, duplication, contamination, and retrieval
  cost are measured.

---

## 5. Diagnose the present agent/skill/prompt system

Begin with a field-level inventory and behavioral characterization. Current behavior is
spread across at least:

```text
src/hive_mind_os/roles.py
src/hive_mind_os/prompt_registry.py
src/hive_mind_os/mission.py
src/hive_mind_os/model_backend.py
src/hive_mind_os/runtime.py
src/hive_mind_os/experiment_runner.py
src/hive_mind_os/builtin_packages/hive-core/agents/*.json
src/hive_mind_os/builtin_packages/hive-core/skills/*.json
src/hive_mind_os/builtin_packages/hive-core/skills/instructions/*.json
src/hive_mind_os/builtin_packages/hive-core/prompts/*.json
prompts/*.txt
```

Known concerns to reproduce rather than assume:

- `roles.py` is live constitutional/runtime data.
- generation-zero prompts are rendered from the Python role literals.
- agent JSON repeats role mission, outputs, capabilities, and gates.
- package prompt JSON adds a separate one-sentence instruction.
- mission execution contains another hard-coded action-guidance layer.
- current package prompts and skill instructions are inert; the model backend uses
  the Python-generated generation-zero prompt.
- every agent currently selects one same-role “skill,” making skills miniature role
  summaries rather than reusable procedures.
- skill references and compatibility tests are generic.
- the current skill schema has requested-capability strings and test references, but
  lacks typed I/O, preconditions, postconditions, structured lease/permission and
  side-effect contracts, resource envelopes, idempotency, retry, compensation,
  receipts, metrics, and behavioral-evaluation contracts.
- current role parity tests prove repeated text remains equal; they do not prove role
  effectiveness.
- current prompt evaluation is substantially keyword-based.
- model context can be cut at an arbitrary character boundary, risking loss or
  corruption of blockers, dissent, provenance, and structured context.
- idea records do not yet provide a durable semantic collision, refinement, or
  cross-domain relationship system.

Measure duplication, drift risk, live-versus-inert reachability, and behavior before
changing them. Preserve current public imports, stored data, prompt digests, lifecycle
order, package resources, and runtime output as golden compatibility evidence.

---

## 6. Establish one canonical layered model

Design the exact files through an ADR and court decision, but enforce these conceptual
boundaries:

### Role constitution

The stable accountability of one of the eight constitutional roles:

- mission and customer-value objective;
- exclusive decisions and required outputs;
- authority ceiling and forbidden actions;
- independence and separation-of-duty rules;
- invariants, evidence burden, quality gates, and completion conditions.

### Agent definition

A versioned implementation of a role:

- rich role-specific playbook and reasoning strategy;
- perspectives and critique routines;
- selected compatible skills;
- typed output contracts;
- budget and stopping policy;
- memory read/write policy;
- handoff contract;
- evaluation-suite references and nonauthoritative lifecycle metadata.

Each agent should remain in an individual canonical file, but shared constitutional or
procedural material must be referenced, composed, or generated rather than copied.
Trust, quarantine, court disposition, activation, and promotion must live in an
authenticated append-only adjudication/activation overlay and atomic champion pointer.
An agent manifest must not self-attest those states.

### Skill definition

A small, reusable, bounded procedure that can be used by one or more authorized agents.
A skill is not a biography, a one-sentence role description, or a hidden authority
grant.

Each skill should live in its own versioned file or directory and declare:

- stable ID, version, digest, provenance, owner, and nonauthoritative lifecycle
  metadata;
- purpose and non-goals;
- typed inputs and outputs;
- compatible roles and required capabilities;
- preconditions and postconditions;
- deterministic versus model-assisted steps;
- allowed tools and side effects;
- authority and resource limits;
- timeout, retries, idempotency, and concurrency behavior;
- compensation and rollback;
- evidence and receipt contract;
- failure modes, threats, and prompt-injection treatment;
- unit, contract, integration, and behavioral evaluations;
- metrics, known limitations, migration, and deprecation.

Sharing a skill does not share authority. The calling agent still needs an explicit
capability lease. Authoritative trust, quarantine, activation, court disposition, and
promotion belong to the external append-only overlay; a skill cannot attest its own
admission.

### Tool definition

A capability adapter with typed request/result contracts and declared determinism,
uncertainty, and side-effect semantics. It must define policy mediation, receipts,
sandbox boundary, timeout, cancellation, idempotency, retry, and compensation. Tools
execute permitted operations; skills describe governed procedures that may use them.

### Prompt definition

A deterministic, content-addressed composition from canonical layers. Prompts are
generated delivery artifacts, not a fourth manually maintained authority.

### Host projection

A generated translation of canonical role, skill, tool, and prompt manifests for a
specific host. Codex, Claude Code, Hermes, and future hosts must not redefine core
semantics.

### Workflow and state

OODA, the full lifecycle, courtroom, War Room, handoff, memory, policy, and evidence
state remain explicit and versioned. They must not be hidden inside prose prompts.

### Expected source/projection direction

Conceptually:

```text
Constitution + canonical role definitions + reusable skills + workflow state
                              |
                              v
                  deterministic prompt compiler
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
       runtime prompt   package artifacts   host projections
```

Generated outputs must carry a composition manifest containing the digest of every
input layer. CI should regenerate them and fail on drift. Generated files should warn
against manual editing.

Preserve a trusted, minimal generated runtime facade. Importing constitutional roles
must not load or trust the quarantined/optional package catalog. Retain and extend the
ADR-017 import-isolation guarantee and its hostile tests.

Separation of duties must be machine-enforced by schemas and policy, not merely stated
in prompts. Validate conflicts among actor, scout, advocate, architect, builder,
verifier, judge, promoter, and affected champion identities.

Do not choose YAML, JSON, Python, a database, or a particular directory layout merely
because this prompt suggests a concept. Compare alternatives for typing, comments,
schema validation, packaging, migration, deterministic generation, and portability.

---

## 7. Build the Explorer as the first rich reference agent

The user's intent is an Explorer that is genuinely curious, expansive, deep, and able
to find both bugs and product opportunities. It should see what is obvious, search for
what is hidden, connect things that initially look unrelated, and notice valuable
side-findings encountered during other research.

Translate “think of anything and everything” into broad, measurable coverage with a
finite budget, not an impossible claim of exhaustive knowledge.

### Explorer constitutional boundary

The Explorer is a read-only opportunity and evidence specialist. It may investigate,
compare, question, run explicitly permitted read-only analyses, and recommend. It may
not approve its own idea, change production, mutate policy, install packages, promote
itself, or treat novelty as authorization.

### Required expert lenses

Every substantial exploration should select and record relevant lenses, including:

- customer and end user;
- business user and workflow operator;
- product owner and product strategist;
- software engineer and new contributor;
- system, data, and integration architect;
- QA engineer and adversarial tester;
- security, privacy, abuse, and safety reviewer;
- SRE, maintainer, support engineer, and incident responder;
- accessibility and inclusive-design specialist;
- researcher, standards scout, and ecosystem analyst;
- investor, market strategist, economist, and cost owner;
- legal, compliance, licensing, and governance reviewer;
- contrarian, attacker, failure investigator, and pre-mortem facilitator.

Do not apply every lens as shallow boilerplate. Select the relevant set, explain why,
and seek conflicting interpretations.

### Required discovery modes

The Explorer must deliberately alternate divergent discovery with convergent,
evidence-based ranking:

1. obvious bugs, paper cuts, missing tests, and expected improvements;
2. repository, architecture, history, issue, test, dependency, telemetry, and user
   signal investigation;
3. competitor, adjacent-tool, standards, paper, strong-public-repository, community,
   and current web research when authorized;
4. inversion, boundary, counterfactual, pre-mortem, and failure-chain analysis;
5. second-order effects and unintended incentives;
6. analogy transfer from apparently unrelated fields;
7. concept combination that forms a testable bridge hypothesis;
8. unexpected but relevant serendipitous findings;
9. negative evidence, counterexamples, and reasons an appealing idea may fail;
10. opportunity ranking by customer value rather than novelty or agent activity.

For external research, prefer primary and current sources. Preserve URI, author or
owner, retrieval time, version or commit SHA, digest, license, atomic claims,
counterclaims, and measured relevance. Never invent the content of an inaccessible
source.

### Cross-domain and serendipitous reasoning

An analogy is not evidence by itself. For any surprising connection, record:

- the two or more concepts being connected;
- the causal mechanism that might transfer;
- which assumptions must hold;
- where the analogy breaks;
- a counterexample;
- a low-cost falsifiable experiment;
- expected value if correct and cost if wrong.

Capture useful unexpected findings in a provenance-bound serendipity inbox even when
they were outside the initial query. Explain the relevance or option value. Do not let
the inbox become an unbounded list of generic suggestions.

### Explorer idea lifecycle

```text
observe
  -> question
  -> investigate
  -> synthesize
  -> search prior ideas
  -> classify novelty/relationship
  -> cross-examine
  -> propose to the docket
  -> define metric and falsifiable test
  -> stop, defer, or hand off
```

The Explorer recommends a courtroom burden; it does not issue the verdict.

### Required opportunity output

Before ranking or filtering, every generated candidate must receive a minimal
`IdeaEncounter` record containing its stable encounter ID, normalized candidate text
or safe content reference, originating run/agent/prompt, timestamp, source and memory
references, policy result, and its link to a canonical opportunity or explicit
duplicate/abandoned/invalid/non-material disposition. Filtering may reduce later
research effort; it may not erase the fact that the idea was encountered.

Every candidate promoted into a material opportunity should then contain:

- stable opportunity ID;
- normalized problem, affected user, scope, proposed mechanism, and expected outcome;
- user and business value;
- perspectives applied and disagreements between them;
- evidence and counter-evidence;
- source versions, digests, retrieval dates, and licenses;
- origin labels such as obvious, adjacent, contrarian, cross-domain, or
  serendipitous;
- causal bridge for combined concepts;
- alternatives considered;
- uncertainty, assumptions, cost, risk, reversibility, and strategic leverage;
- related prior opportunities;
- duplicate/refinement/contradiction decision and substantive delta;
- attack and failure analysis;
- proposed experiment, executable acceptance criteria, and outcome metrics;
- dependencies, owner role, suggested court case, and stopping reason;
- unexplored frontiers remaining at budget exhaustion.

### Stop conditions

Exploration is not infinite. Stop or checkpoint on declared research budget, lens
coverage, source saturation, duplicate saturation, diminishing expected value,
deadline, policy boundary, unavailable critical evidence, or uncertainty threshold.
Record why the search stopped and what remains unknown.

---

## 8. Prevent the Explorer from suggesting the same idea twice

Add an append-only `OpportunityRecord` or equivalent canonical idea ledger. The exact
name and storage design require adjudication.

Every opportunity record should retain:

- immutable stable ID;
- separate canonical problem identity and proposed-intervention identity so multiple
  legitimate solutions to one problem are grouped without being falsely merged;
- a problem fingerprint over
  `target + affected user + problem + outcome + scope`;
- a proposal fingerprint over
  `problem ID + mechanism + constraints + expected effect`;
- normalized source text and exact fingerprints;
- evidence and source digests;
- semantic retrieval key used only to find possible collisions, with the canonicalizer,
  embedding/model, index, threshold, and algorithm versions;
- the retrieved neighbor set and evidence used for every collision classification;
- status, disposition, confidence, novelty, timestamps, owner, and version;
- correction and appeal history;
- aliases and relationships such as:
  `same_as`, `refines`, `supersedes`, `conflicts_with`, `enables`,
  `complements`, `combines_with`, and `inspired_by`.

Before emitting a proposal, use a staged collision process:

1. exact canonical digest match;
2. deterministic structured-key match;
3. semantic retrieval of likely neighbors;
4. evidence-bearing comparison and classification.

Classify a candidate as:

- genuinely new;
- refinement;
- variant;
- reinforcement or new evidence;
- contradiction;
- complement;
- appeal; or
- duplicate.

A duplicate must not be silently discarded. Attach corroborating evidence, aliases,
outcome updates, or an appeal to the existing record. A refinement or contradiction
may receive a new ID only when its substantive delta is explicit.

Semantic similarity is a convenience index, not the authority. It must not erase
legitimate distinctions. Preserve false-merge appeals and rebuildable deterministic
indices.

Make registration transactional and idempotent. Simultaneous Explorer workers must not
emit duplicate canonical records because they checked before either committed. Use an
atomic compare/register/relate operation, append-only collision receipts, safe retries,
and deterministic recovery after interruption.

Do not send private repository, user, tenant, or secret-bearing content to an external
embedding provider without explicit policy, disclosure, and a capability lease. Record
data classification and tenant boundary, test isolation, and provide an offline
deterministic candidate-retrieval fallback. Semantic-index rebuilds must have pinned
versions and receipts.

Measure:

- duplicate escape rate;
- false-merge rate;
- accepted novelty rate;
- validated-idea yield;
- defect precision and recall on seeded cases;
- evidence and citation completeness;
- perspective diversity;
- cross-domain usefulness under blind review;
- research-to-adoption conversion;
- customer outcome impact;
- cost per validated opportunity.

---

## 9. Give every other agent equivalent depth

Do not copy the Explorer's wording into seven renamed files. Each role needs a distinct
constitutional duty, reasoning playbook, output schema, skill set, authority ceiling,
failure modes, and behavioral evaluation.

### Orchestrator

The Orchestrator is the outcome, portfolio, dependency, budget, and recovery owner.
It should:

- turn desired customer outcomes into bounded, testable work;
- compare candidate problems and reject low-value activity;
- map dependencies, critical paths, parallel work, resource leases, and budgets;
- schedule the courtroom and preserve separation of duties;
- define OODA cadence, checkpoints, stopping conditions, resumability, and recovery;
- manage uncertainty, risk, tradeoffs, partial failure, and escalation;
- reconcile handoffs without silently dropping blockers, dissent, or evidence;
- stop work that no longer justifies its cost.

It must not approve architecture, implementation quality, independent verification, or
its own performance.

### Architect

The Architect is the option, interface, invariant, and evolution owner. It should:

- produce multiple viable alternatives and a reasoned comparison;
- model components, data, state, trust boundaries, contracts, and failure domains;
- address security, privacy, accessibility, cost, performance, scale, operability,
  portability, and maintainability;
- specify invariants and executable acceptance contracts;
- analyze version skew, backward compatibility, migration, rollback, and recovery;
- expose assumptions, threats, abuse cases, and unresolved decisions;
- write decision records that trace adopted claims to design.

It must not implement and then approve its own design or smuggle authority into an
interface.

### Builder

The Builder is the bounded implementation and executable-evidence owner. It should:

- trace every change to an adjudicated requirement and acceptance criterion;
- implement the smallest complete, reversible solution in isolation;
- preserve compatibility and unrelated user work;
- add failure-before and pass-after evidence;
- test positive, negative, boundary, hostile, interruption, and rollback cases;
- manage dependencies and supply-chain changes explicitly;
- produce code, tests, diffs, artifact digests, commands, and receipts;
- appeal incomplete or contradictory architecture rather than silently redesigning it;
- hand off reproducible evidence to an independent Curator.

It must never weaken tests, policy, evidence, or quality gates to make a run pass, and
it must not approve its own work.

### Curator

The Curator is the independent, hostile correctness and trust owner. It should:

- derive verification independently rather than accepting Builder conclusions;
- reproduce material claims from a clean boundary;
- inspect correctness, regressions, security, privacy, provenance, licensing,
  compliance, accessibility, product acceptance, and release evidence;
- look for counterexamples, hidden coupling, false green tests, stale evidence,
  point-in-time contamination, and unsupported claims;
- verify artifacts, receipts, identities, authority, source coverage, and rollback;
- preserve dissent and give an evidence-bound release recommendation;
- distinguish not-tested, failed, blocked, deferred, and passed.

The Curator must be organizationally and evidentially separate from the Builder and
must not treat the acting agent's statements as proof.

### Integrator

The Integrator is the cross-boundary contract and compatibility owner. It should:

- version APIs, schemas, events, package contracts, adapters, and migrations;
- preserve data lineage and evidence across repositories and systems;
- handle provider, model, storage, scheduler, Git, MCP, A2A, AG-UI, channel, and host
  boundaries;
- test version skew, negotiation, retries, timeout, cancellation, idempotency,
  ordering, partial failure, compensation, and rollback;
- produce compatibility matrices and conformance receipts;
- keep provider-specific behavior out of the constitutional core;
- own Obsidian projections and intake boundaries if adopted.

It must not label a host supported merely because a profile file exists.

### Steward

The Steward is the reliability, maintainability, recovery, and evidence-health owner.
It should:

- define and observe SLOs, error budgets, health signals, and operational cost;
- detect dependency drift, security exposure, rot, stale runbooks, and ownership gaps;
- maintain observability, backup/restore, incident, migration, and recovery procedures;
- run controlled recovery, chaos, and restart drills within authority;
- preserve ledger, artifact, source, and receipt integrity;
- reduce toil and measured long-term risk through reversible maintenance;
- detect when projections, indices, prompts, packages, or adapters drift from their
  canonical inputs.

It must not equate routine cleanup with customer value or silently expand operational
authority.

### Optimizer

The Optimizer is the experiment, causal-learning, and teaching owner. It should:

- define customer-linked metrics and baselines;
- design controlled, held-out, budget-equal experiments;
- compare multiple pinned alternatives when making superiority claims;
- guard against leakage, gaming, cherry-picking, survivorship bias, and metric
  substitution;
- attribute root causes and separate signal from noise;
- use shadow, canary, regression-budget, and rollback gates;
- create reusable teaching packets from repeated supported findings;
- retain losing experiments and negative results;
- propose a versioned challenger and independent promotion appeal.

It must never select the test, build the challenger, judge the result, and promote
itself as the same identity.

---

## 10. Replace role-shaped “skills” with a reusable skill library

Candidate small skills include:

### Discovery and evidence

- source capture, pinning, provenance, and license inspection;
- atomic claim and counterclaim extraction;
- repository mapping and point-in-time history inspection;
- defect reproduction and test minimization;
- user-signal and user-journey synthesis;
- competitor, ecosystem, standards, paper, and strong-repository research;
- opportunity scoring and uncertainty calibration;
- cross-domain analogy and bridge-hypothesis testing;
- serendipity capture;
- idea deduplication, relationship classification, and lineage.

### Design and build

- option comparison and ADR production;
- invariant and interface design;
- threat, privacy, abuse-case, and failure-mode modeling;
- schema and protocol design;
- migration, compatibility, and rollback design;
- bounded patch planning;
- isolated workspace editing;
- deterministic test execution and receipt capture.

### Verification and integration

- adversarial test design;
- independent claim reproduction;
- security, license, provenance, and source-coverage inspection;
- contract, version-skew, packaging, and host conformance;
- receipt and artifact validation;
- release and rollback verification.

### Operations and learning

- SLO and observability design;
- incident analysis and recovery drills;
- dependency and evidence-health analysis;
- benchmark and held-out evaluation design;
- causal analysis and root-cause attribution;
- challenger comparison;
- teaching-packet creation.

Skills may be composed into workflows, but avoid a monolithic skill that secretly
recreates an entire role. Validate skill dependency cycles, capability union,
conflicting preconditions, budget aggregation, failure compensation, and version
compatibility.

---

## 11. Compose prompts; do not maintain copied prompt authorities

Compile each runtime prompt deterministically from:

1. constitutional rules and instruction precedence;
2. role charter, exclusive accountability, and forbidden actions;
3. mission objective, constraints, authority, budget, and stop conditions;
4. current OODA/lifecycle/court state and handoff;
5. selected skill procedures and their versions;
6. tools that are actually available and leased;
7. minimal provenance-bearing context and memory manifest;
8. typed output schema and evidence obligations;
9. role-specific critique and failure checklist;
10. escalation, checkpoint, completion, and recovery rules.

Keep prompts as thin as possible. Put reusable procedures in skills, durable truth in
state, and authority in policy/leases. Do not make a prompt the only place where a
critical invariant exists.

The compiler must:

- produce deterministic bytes and a composition manifest;
- bind every layer's digest and version;
- support content-addressed champion/challenger records;
- preserve generation-zero compatibility until independently migrated;
- produce host-specific projections without changing semantics;
- reject missing, incompatible, ambiguous, quarantined, or unauthorized layers;
- make prompt injection, untrusted-source boundaries, secret handling, identity,
  evidence, and tool authority explicit.

Replace arbitrary character slicing of context with progressive disclosure and a
logged context manifest. Blockers, dissent, authority, critical receipts, source
provenance, and completion conditions must not disappear because a string exceeded a
length limit.

Do not promote prompts based on length, polish, or expected keywords. Use held-out
behavioral evaluations.

---

## 12. Behavioral evaluations, not prose parity

### Explorer reference suite

Use held-out episodes proving the Explorer can:

- find seeded obvious defects;
- find a non-obvious product opportunity;
- discover a useful permitted external pattern with correct provenance;
- capture an unexpected but relevant side-finding;
- produce a defensible cross-domain bridge and falsifiable test;
- avoid resuggesting an existing idea on a second run;
- attach new evidence to an old idea without losing history;
- distinguish duplicate, refinement, contradiction, complement, and new idea;
- rank useful findings above generic suggestions;
- search for counter-evidence;
- fail closed on an unavailable source;
- preserve unexplored frontiers and stopping reasons;
- resist prompt injection in repositories, web pages, and Obsidian notes;
- perform no write, approval, installation, or promotion action.

### Other role suites

- Orchestrator: complete dependency, budget, uncertainty, stopping, resumption, and
  recovery planning without self-approval.
- Architect: alternatives, invariants, threats, compatibility, migration, rollback,
  and objectively testable contracts.
- Builder: bounded patch correctness, failure-before/pass-after proof, hostile cases,
  no unrelated changes, rollback, and receipts.
- Curator: independent detection of seeded regressions, security faults, false
  evidence, source gaps, and license/provenance defects.
- Integrator: version skew, contract negotiation, packaging, lineage, partial failure,
  host projection, migration, and rollback.
- Steward: incident detection, restore drills, dependency risk, drift, stale runbooks,
  evidence corruption, and SLO breaches.
- Optimizer: held-out protection, causal validity, comparator quality, regression
  budgets, anti-gaming, negative-result retention, and rejection of self-promotion.

Measure behavior against the current champion with equal budgets. Retain losing
benchmarks, uncertainty, dissent, and regressions. A richer prompt is not automatically
a better agent.

Pin the model/provider version, canonical role/skill versions, prompt-compiler version,
composition digest, context manifest, tool versions, random seeds where applicable,
budget, dataset, and holdout seal. Use repeated runs where behavior is stochastic and
report uncertainty or confidence intervals. Protect held-out cases from the acting
agent and challenger author.

---

## 13. Memory and knowledge architecture

Keep canonical machine state separate from human-friendly Markdown projections.
Provide versioned, append-only records for:

- source and atomic-claim docket;
- opportunity/idea ledger and relationship graph;
- decisions, dissent, appeals, and supersession;
- mission episodes, OODA state, handoffs, and checkpoints;
- tool intents, policy decisions, leases, receipts, and artifacts;
- bugs, incidents, failed experiments, and recovery lessons;
- user feedback, outcome metrics, and adoption evidence;
- role and skill versions, prompt composition manifests, and host projections.

Indices, embeddings, Obsidian notes, HTML War Room views, caches, and search databases
are rebuildable projections. They must not become the only copy of provenance or
disposition truth.

---

## 14. Granular token, cost, loop, and agent-effectiveness telemetry

Track resource use at the smallest useful causal boundary: every model request,
agent turn, skill invocation, tool/retrieval step, idea, court side, OODA iteration,
mission, experiment, repository, and OS instance.

Use two lanes:

1. an append-only, high-cardinality `UsageEvent` ledger backed by a local transactional
   outbox or write-ahead log for exact accounting, provenance, correlation, replay,
   restart recovery, and later outcome attribution; and
2. correlated OpenTelemetry traces plus low-cardinality operational metrics for live
   observability and replaceable export.

Obsidian receives readable run notes, agent scorecards, idea-economy tables, loop
incidents, quarantine records, and token/value dashboards. It is not the canonical
accounting database.

Write the durable attempt and usage receipt before marking a request complete. Export
from the outbox idempotently and reconcile completeness against provider usage and
invoices. OpenTelemetry is a projection of the durable ledger; disabling sampling does
not make a lossy exporter an accounting system.

OpenTelemetry's GenAI conventions are still evolving. Pin the exact convention version
and preserve the provider-native usage object alongside normalized fields. Never let a
semantic-convention upgrade silently change historical meaning.

### Accounting rules

- Prefer provider-reported usage.
- If a local tokenizer can count exactly, record tokenizer and model version.
- If only an estimate is possible, mark it `estimated` with method and confidence.
- If usage cannot be measured reliably, record `unknown`; do not invent zero.
- Preserve requested, served, and billable model identities separately.
- Preserve raw provider usage through an opaque or keyed reference to separately
  protected content.
- Give each logical request, physical attempt, provider request, and usage receipt a
  separate stable ID. Preserve every billed retry/attempt. Deduplicate only repeated
  ingestion of the same receipt or duplicate final streaming report.
- Emit append-only correction and invoice-reconciliation events; never rewrite the
  original observation.
- Pin pricing catalog version, currency, region/service tier, effective time, and
  digest. Provider prices can change.
- Treat local/self-hosted models fairly: record tokenizer counts, wall time, queue
  time, CPU/GPU time, memory, and energy where available even if monetary cost is zero.

Do not sum every provider field. Cached input is often included in total input, and
reasoning/thinking tokens are often included in total output or total generation.
Store inclusive provider totals separately from normalized accounting dimensions.
Direction, cache status, modality, output kind, billing status, and prompt/context
attribution are different axes and may overlap across axes: a cached image token is
both cached and image. Categories must be mutually exclusive only within the same
declared axis, using `not_applicable` or `unknown` when needed. Define reconciliation
invariants for each axis and never sum views across axes. System, user, tool, retrieved
memory, and other context counts are attribution views unless the adapter proves they
form an independently disjoint partition. Every adapter needs conformance fixtures
proving these mappings and preventing double counting.

### Portable usage-event contract

The exact schema requires a court and additive migration. It should contain:

| Group | Required or useful fields |
| --- | --- |
| Event identity | schema version, event/idempotency ID, logical request ID, attempt ID, provider request ID, usage receipt ID, kind, sequence, occurred/recorded timestamps, previous/event digests |
| Measurement source | provider, host, local tokenizer, or reconciliation; adapter ID/version; reported/counted/estimated/reconciled; confidence |
| Repository correlation | tenant, repository ID, commit, controller build, run, trace/span/parent, session, task, OODA cycle, lifecycle stage |
| Work correlation | case ID, idea ID, experiment ID, requirement, acceptance criterion, skill, tool, source, memory-packet ID |
| Agent identity | canonical agent definition/version, instance ID, constitutional role, temporary courtroom identity, host |
| Model identity | provider, requested model, served model, billable model, version/snapshot, service tier, reasoning configuration, context limit |
| Token totals | provider-inclusive input, output, and total |
| Token dimensions | direction; cache status; modality; visible/reasoning/other output kind; billable status; per-axis totals, unknowns, and reconciliation residuals |
| Non-token use | web searches, code-execution time, image/audio units, storage, network, tool-specific charges |
| Financials | reported, estimated, and reconciled cost; currency; rate components; pricing digest; invoice variance |
| Timing | queued time, duration, time to first token/chunk, output-token latency, tool wait, retry count |
| Evaluation/purpose | evaluated subject kind/ID/version, candidate manifest and evaluation arm, preregistered treatment factor, debate stance, work purpose, attribution method, weight, confidence |
| Budget | lease, allocation, consumed before/after, reserve, soft and hard crossings |
| Progress | iteration, state before/after digests, new evidence, unique ideas, acceptance progress, repeated action, no-progress streak |
| Context/memory | non-summable attribution views for system/user/tool/retrieved-memory context unless proven disjoint; retrieved memory IDs/digest, cache use, compaction, truncation, critical-context retention |
| Result | success/failure/interruption/quarantine, finish reason, bounded error class, artifacts, evaluation refs |
| Privacy | capture mode, sensitivity, tenant, redaction, retention, external-content reference |

Example purpose allocation:

```yaml
evaluated_subject:
  kind: agent_manifest
  id: explorer-v2
  version: sha256:...
evaluation_arm: champion
treatment_factor: prompt_package
debate_stance: advocate
purpose_allocations:
  - purpose: evidence_research
    weight_ppm: 250000
    basis: dedicated_span
    confidence: 1.0
  - purpose: idea_advocacy
    weight_ppm: 750000
    basis: explicit_runtime_tag
    confidence: 1.0
```

Weights must sum to 1,000,000. Prefer one dedicated purpose per call and split mixed
work into child spans. If an honest allocation is unavailable, use `mixed_unknown`.
Never ask another model to invent exact per-token percentages from prose after the
fact.

### Distinguish two meanings of “champion”

Track separately:

1. **Evaluation arm:** whether a specifically identified and versioned evaluated
   subject or composed candidate manifest is the active champion, a challenger, a
   control, or unclassified. Record the preregistered treatment factor. Do not infer
   the arm from whichever agent or model happened to issue the request.
2. **Court stance:** whether the current work advocates an idea, cross-examines it,
   provides neutral testimony, judges it, or handles an appeal.

This prevents an active champion acting as Cross-Examiner from being mislabeled as
advocacy, and prevents a challenger skill inside a champion agent or a control model
inside either arm from being attributed to the wrong candidate.

For each denominator, report input, output, billable, cost, and combined ratios
separately:

```text
champion_candidate_token_share
challenger_candidate_token_share
idea_advocacy_token_share
idea_cross_examination_token_share
independent_judgment_token_share
unattributed_token_share
```

Never mix raw tokens across models as though they represent equal compute, cost, or
quality. Provide raw-token, billable-cost, wall-time, and outcome-normalized views.

### Late-bound outcome attribution

Usage occurs before a verdict or customer outcome. Keep usage events immutable and add
separate append-only `DecisionEvent`, `OutcomeEvent`, and `AttributionEvent` records.
Join them by idea, case, experiment, candidate, and trace.

Required outcome model is a cube:

```text
evaluation_arm × debate_stance × disposition
    -> input tokens, output tokens, billable cost, wall time, outcomes, unknown share
```

Provide separate arm-by-disposition and stance-by-disposition marginal tables, plus
the full intersection when sample size and privacy allow it. Arm and stance intersect;
never add their marginal rows together. Every table declares its denominator and
retains explicit `unknown`/`unclassified` cells.

Appeals may change the effective disposition. Preserve the historical verdict and add
the superseding decision; do not rewrite prior ratios.

### Do not call every rejected token “waste”

A rejected champion or hypothesis may have prevented a dangerous change, exposed a
false assumption, or created reusable evidence. Use late-bound `AttributionEvent`
allocations with one mutually exclusive primary resource disposition per allocated
share:

- necessary delivery;
- productive falsification;
- necessary safety/verification;
- reusable learning without immediate delivery;
- avoidable rework;
- duplicate discovery;
- no-progress loop;
- failed retry;
- cancelled without receipt;
- context replay;
- coordination/handoff; or
- unattributed/unknown.

The primary allocation weights must sum to 1,000,000 for the classified usage.
Separately attach non-exclusive reason and value tags such as `rejected_hypothesis`,
`invalid_source`, `unavailable_source`, `defect_prevented`, `evidence_reused`, and
`policy_blocked`. A token share may have several tags, so tag totals must never be
summed as though they were exclusive.

Cross-tab primary disposition by evaluation arm and later court disposition to answer
questions such as “what percentage of champion tokens on approved or rejected ideas
was independently classified as avoidable?” Preserve unknown share and confidence.

Only an independent, evidence-bearing outcome review may classify usage as avoidable
waste. Include confidence and an appeal. Do not let the acting agent protect its score
by self-labeling all work valuable.

### Core consumption and efficiency metrics

Track at agent, role, skill, prompt, model, idea, court, stage, mission, repository, and
time-window scopes:

- input, uncached input, cache-read, cache-write, visible output, reasoning output, and
  total/billable tokens;
- tokens by modality and tool-generated context;
- request count, retry count, error count, finish reason, and rate-limit events;
- cost by provider component plus invoice reconciliation variance;
- queue time, time to first token, total latency, tool wait, and active/wall time;
- context-window utilization, truncation, compaction, and recovery;
- cache-hit ratio and tokens/cost avoided;
- token burn per OODA phase and lifecycle stage;
- tokens between durable progress deltas;
- tokens per accepted evidence item, verified acceptance criterion, defect, decision,
  implementation, and measured customer outcome;
- cost and latency per successful mission;
- marginal quality/value from each additional token-budget tier;
- model-routing regret: retrospective quality/cost difference from the best eligible
  route found under controlled evidence;
- telemetry completeness, estimation share, reconciliation lag, and accounting error.

Low token use is not automatically good. An agent can game it by stopping early,
under-researching, skipping dissent, or producing unsafe work. Pair efficiency with
quality, safety, completeness, reversibility, and customer outcome.

### Role-specific effectiveness scorecards

| Role | Useful effectiveness measures |
| --- | --- |
| Orchestrator | plan accuracy, dependency misses, budget forecast error, stalled work prevented, resume success, coordination tax |
| Explorer | verified defects, evidence-backed unique ideas, duplicate tax, source quality, serendipitous conversion, adoption and value yield |
| Architect | design defect escape, option diversity, contract failures, migration/rollback success, downstream rework |
| Builder | first-pass correctness, Curator reproduction, regression and rollback rate, rework, change value per token |
| Curator | seeded-defect recall, false-positive rate, independent reproduction, escaped critical defects, verification cost |
| Integrator | conformance pass rate, version-skew failures found, partial-failure recovery, lineage completeness, adapter portability |
| Steward | SLO improvement, incident prevention, restore success, MTTR, drift detected, toil and operational-risk reduction |
| Optimizer | causal lift, calibration, holdout integrity, comparator quality, regression control, teaching-packet reuse |

Also track:

- advocate confidence versus later verdict and outcome;
- challenger material-objection yield and false/blanket-rejection rate;
- Judge calibration, appeal rate, and overturn rate;
- suspicious disposition collapse, such as champions always passing or challengers
  always losing;
- memory retrieval precision, stale-memory rejection, citation/use rate, and later
  tokens avoided;
- skill reuse and marginal value through paired controlled trials;
- quarantine precision, false positives, avoided impact, and resolution time.

These are diagnostic vectors, not one leaderboard number. Never optimize agent survival,
approval rate, objection count, code volume, idea count, or token reduction as the
mission.

### Hierarchical resource leases

Budget from the outside in:

```text
OS instance
  -> repository
    -> mission/run
      -> lifecycle stage/OODA cycle
        -> court case/idea/experiment
          -> agent/skill
            -> model/tool request
```

Every lease may bound tokens, cost, wall time, model calls, tool calls, retries,
parallelism, context pressure, and external searches. Reserve a separate checkpoint,
evidence-sealing, and rollback allowance so a hard stop can preserve truth safely.

Use soft thresholds for warning, context compression, replan, cheaper routing, or an
independent challenge. Enforce hard ceilings in the provider-neutral runtime. A
provider's advisory task budget is not a hard lease.

### Loop and stalled-progress detection

Fingerprint each iteration:

- goal and unresolved requirements;
- repository tree, patch, and test/error state;
- evidence, source, claim, and idea IDs;
- court claims and open objections;
- tool name plus normalized arguments and result/error signature;
- agent/handoff graph;
- OODA phase, decision, and next action;
- state and context-manifest digests.

Detect:

- exact state repetition;
- `A -> B -> A` or longer state oscillation;
- repeated normalized tool calls or identical errors;
- near-duplicate ideas or responses with no substantive delta;
- no new evidence, artifact, decision, or acceptance progress for a bounded number of
  turns;
- rising token/cost burn with flat progress;
- agent-to-agent delegation or court ping-pong;
- repeated compaction without successful recovery;
- context growth caused mainly by replaying prior output;
- retry storms and repeated unavailable-source requests;
- courtroom replay of the same claims without new evidence;
- self-host projection or telemetry feedback loops.

Do not let a loop mint volatile timestamps, IDs, prose, evidence wrappers, or trivial
artifacts to reset its counter. Canonicalize volatile fields away. Count progress only
when an independently valid state transition closes or materially advances a
requirement, changes the admissible evidence, produces a required artifact, or issues
an authorized decision.

Stage-aware repeated verification can be legitimate. Require an explicit
`verification_repeat` purpose, new receipt target, and finite stop condition.

Escalate progressively:

1. emit a loop/stall observation;
2. require an explicit alternative strategy and checkpoint;
3. run a deterministic diagnostic or independent challenger;
4. reduce remaining side-effect/tool authority;
5. reset or rebuild context from a sealed memory manifest;
6. switch the episode to read-only;
7. stop and quarantine the episode or implicated version.

Record tokens and useful evidence gained at each escalation.

Hard-budget breaches, secret exposure, destructive-action risk, cross-tenant access,
or other critical policy signals may bypass progressive escalation and immediately
revoke side-effect authority, seal evidence, and enter scoped quarantine.

### What telemetry may quarantine

Support scoped quarantine of:

- one request, episode, run, or mission;
- agent, prompt, skill, workflow, tool, MCP, host, or model-adapter version;
- memory packet, source, idea, court case, or evaluation cohort;
- extension package;
- usage/pricing adapter or corrupted telemetry partition.

Signals include:

- hard budget/context breach;
- missing, ambiguous, or inconsistent usage accounting;
- repeated no-progress loop or retry storm;
- prompt injection, secret exposure, or cross-tenant retrieval;
- broken event hash chain or telemetry tampering;
- requested/served/billable model ambiguity;
- champion/challenger budget imbalance outside the preregistered design;
- evaluation contamination or holdout access;
- cross-role identity conflict;
- cost, token, latency, or context anomaly outside a versioned envelope.

A hard lease breach may stop work automatically. Permanent component quarantine needs
the normal evidence and independent court. Token use alone must not declare an agent
bad, expand authority, promote a replacement, or erase its evidence.

Every quarantine needs scope, reason, triggering receipts, blast radius, descendants,
review/expiry condition, safe rehabilitation test, appeal, and rollback. Expiry only
opens an independent review; it never restores execution automatically. Rehabilitation
requires an authenticated independent disposition, passing tests, transitive
descendant checks, and atomic activation with rollback.

### Fair champion/challenger learning without cheating

Use four independent gates:

1. **Absolute fitness gate:** the champion must continue to meet minimum value,
   safety, and correctness floors plus resource ceilings. It can fail or be
   quarantined even if no challenger is better.
2. **Relative comparison gate:** a challenger needs preregistered superiority on a
   primary value/quality endpoint, or a preregistered material cost/latency reduction,
   while meeting non-inferiority margins on safety, correctness, and other guardrails.
   Mere non-inferiority everywhere is not enough to cause churn.
3. **Uncertainty gate:** inconclusive evidence means no promotion claim; gather more
   evidence within a declared sequential-testing plan.
4. **Post-promotion gate:** shadow/canary outcomes can demote the new champion. Preserve
   the prior champion and a safe generation-zero/no-champion fallback.

This avoids both incumbent immortality and reckless challenger promotion.

Required anti-cheating controls:

- partition by repository, time, task family, idea/case lineage, and source provenance,
  not random individual spans alone;
- maintain training, development, sealed held-out, shadow/canary, and future temporal
  cohorts;
- hide target/future commits, gold patches, labels, Judge decisions, and challenger
  private evidence until the run is sealed;
- log every evaluation-data and memory-packet access;
- preregister metrics, weights, budgets, stop rules, thresholds, acceptable
  regressions, comparison direction, treatment factor, minimum sample size or power,
  multiplicity correction, and sequential/optional-stopping method;
- define equivalent or stake-adjusted budgets before arm assignment, including the
  objective rule that justifies any difference;
- give champion and challenger equivalent admissible evidence;
- randomize order and blind candidate/model/author identity from independent judges
  when practical;
- compare paired runs where exactly the preregistered treatment factor may differ and
  all other model, prompt compiler, context, tool, seed, environment, repository
  cutoff, and budget factors remain fixed;
- repeat stochastic episodes and report confidence intervals and practical effect
  sizes;
- protect holdouts from the acting agent, challenger author, prompt optimizer, and
  promotion identity;
- count and limit repeated holdout access; rotate or retire overexposed cohorts;
- use point-in-time tasks and fresh/future cases to detect contamination;
- teach from adjudicated principles and evidence after sealing, not raw hidden answers
  or private chain-of-thought;
- preserve failures, dissent, rejected ideas, and appeals;
- audit for suspicious metric gaming, underthinking, excessive objection, or outcome
  collapse.

Do not impose an artificial champion failure quota. Make failure possible through an
honest absolute gate and independent evidence. A 100% champion pass rate or 100%
challenger loss rate is a trigger for bias investigation, not proof of excellence.

### Causal learning and memory effectiveness

Agents should learn only from outcomes that have matured and been independently linked
to the work. Use controlled trials where safe:

- memory retrieval on versus off;
- full versus compressed context;
- one skill/prompt/model route versus another;
- different token budget tiers;
- cached versus uncached context;
- Explorer lens or cross-domain technique ablations.

Track the memory packet shown to each run. Measure:

- retrieval precision and missing-critical-memory rate;
- stale, contradictory, quarantined, or irrelevant memory rate;
- tokens spent retrieving and replaying memory;
- downstream tokens, defects, or rework avoided;
- decision/outcome lift;
- false confidence caused by prior memory;
- evidence diversity and dissent exposure;
- post-compaction critical-fact retention.

Do not infer causality from simple correlation. Record whether attribution is direct,
controlled, quasi-experimental, expert-judged, or merely associated.

### Metrics, traces, cardinality, and privacy

Never put unbounded IDs or content into metric labels: no run, trace, session, idea,
case, repository path, URL, user, prompt, tool arguments, or file name. Keep those in
events/spans. Metrics use controlled dimensions such as provider, model family, role,
lifecycle stage, evaluation arm, debate stance, disposition, result, and bounded
error class.

Token/cost accounting events must not be sampled and must first enter the local
transactional outbox/WAL. Successful diagnostic traces may be sampled, but retain
failures, quarantines, appeals, security events, superiority evaluations, high-cost
outliers, and loop incidents. Test crash, backpressure, exporter outage, duplicate
delivery, and restart recovery; reconcile durable attempts and receipts against
provider reports and invoices.

Default prompt, response, memory, tool-argument, and tool-result capture to none,
digest, redacted content, or separately access-controlled reference. Outbound telemetry
is disabled by default. Test secret scrubbing, tenant isolation, retention, deletion
policy, and encrypted transport/storage where adopted. Keep sensitive content outside
the permanent hash chain in encrypted, access-controlled storage; use opaque or keyed
identifiers, deletion tombstones, and cryptographic erasure where required. Never hash
raw secrets, user text, or other low-entropy sensitive values directly into permanent
provenance.

Provide replaceable local and remote adapters:

- append-only JSONL or equivalent portable event export;
- SQLite or another local transactional store;
- OpenTelemetry/OTLP;
- low-cardinality Prometheus-compatible metrics;
- optional self-hosted or third-party backends after separate review;
- deterministic Markdown, Bases, and Canvas projections for Obsidian.

No SaaS backend is required. The open-source default must be fully useful locally.

For the pinned OpenTelemetry GenAI convention, export billable token counts through
`gen_ai.client.token.usage` when the provider supplies both used and billable counts.
Keep inclusive provider totals and other accounting views only in the durable ledger
or appropriately named custom instruments. Add an adapter fixture that proves this
mapping for every supported provider/convention version.

### Required Obsidian telemetry views

- agent token/cost/effectiveness scorecard over time;
- input/output/cache/reasoning and context utilization;
- model/provider/service-tier comparison;
- evaluation-arm × debate-stance × disposition token/outcome cube and safe marginals;
- idea economics from discovery through verified customer outcome;
- rejected-but-useful versus avoidable-waste classification;
- loop, retry, compaction, and context-churn incidents;
- budget leases, threshold crossings, and forecast error;
- quarantine triggers, exposure, appeal, and rehabilitation;
- memory retrieval cost and measured lift;
- telemetry gaps, estimates, double-count prevention, and invoice variance;
- fairness audit showing cohort, budget, identity, holdout access, and disposition
  balance.

### Telemetry acceptance criteria

- Every model request has a usage event or an explicit unknown-usage failure record.
- Provider totals and per-axis normalized dimensions reconcile without cross-axis
  double counting.
- Every billed retry/attempt is retained, while duplicate ingestion, replay, and
  streaming-finalization receipts cannot duplicate cost.
- Percentages identify denominator, attribution method, unknown share, and confidence.
- Evaluation arm and debate stance remain separate.
- Historical usage is not rewritten when verdicts or appeals change.
- Rejected work is not automatically mislabeled waste.
- Every agent has role-appropriate effectiveness and customer-value measures.
- Hard limits stop safely with checkpoint/rollback reserve.
- Loop tests cover repetition, oscillation, retry storms, context churn, delegation
  ping-pong, and self-host feedback.
- Quarantine is scoped, receipted, appealable, reversible, and cannot self-promote a
  replacement or reactivate merely because time elapsed.
- The champion can fail an absolute gate; the challenger can win a fair paired test.
- No candidate can access sealed holdouts, future commits, or forbidden memory.
- Telemetry overhead, cardinality, privacy, retention, and tenant isolation are tested.
- The complete accounting and brain operate locally without an outbound service.
- Obsidian views reconcile to the canonical ledger at an exact projection cursor.

### Brain, telemetry, and evaluation research sources

The following primary or official sources were retrieved on 2026-07-28 and produced
useful candidate patterns. They are research inputs, not automatic adoptions:

| Topic | Primary/official source |
| --- | --- |
| OpenTelemetry GenAI conventions, pinned retrieval commit `799e014b68f0e786dc44d9117c30758c5f864510` | <https://github.com/open-telemetry/semantic-conventions-genai/tree/799e014b68f0e786dc44d9117c30758c5f864510> |
| GenAI token, duration, workflow, agent, and tool metrics | <https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-metrics.md> |
| GenAI model spans and sensitive-content guidance | <https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-spans.md> |
| GenAI agent spans | <https://github.com/open-telemetry/semantic-conventions-genai/blob/799e014b68f0e786dc44d9117c30758c5f864510/docs/gen-ai/gen-ai-agent-spans.md> |
| Prometheus metric/label cardinality | <https://prometheus.io/docs/practices/naming/> |
| Prometheus instrumentation guidance | <https://prometheus.io/docs/practices/instrumentation/> |
| Codex observability and telemetry | <https://developers.openai.com/codex/config-advanced#observability-and-telemetry> |
| Claude Code usage monitoring | <https://code.claude.com/docs/en/monitoring-usage> |
| Claude provider usage report | <https://platform.claude.com/docs/en/api/admin/usage_report/retrieve_messages> |
| Claude task budgets | <https://platform.claude.com/docs/en/build-with-claude/task-budgets> |
| Gemini usage metadata | <https://ai.google.dev/api/generate-content> |
| MLflow classic model absolute/baseline metric thresholds | <https://mlflow.org/docs/latest/api_reference/python_api/mlflow.models.html#mlflow.models.MetricThreshold> |
| MLflow GenAI evaluation and monitoring | <https://mlflow.org/docs/latest/genai/eval-monitor/> |
| LM Evaluation Harness repeats and decontamination, pinned retrieval commit `f4d4b3de3ee6741a7151a9fe74945ee515262f4c` | <https://github.com/EleutherAI/lm-evaluation-harness/blob/f4d4b3de3ee6741a7151a9fe74945ee515262f4c/docs/task_guide.md> |
| LiveBench contamination-resistant evaluation paper | <https://arxiv.org/abs/2406.19314> |
| AgentTelemetry fault/loop observability paper | <https://openreview.net/pdf?id=owdmAYFk6k> |
| W3C PROV-O provenance model | <https://www.w3.org/TR/prov-o/> |
| W3C JSON-LD 1.1 | <https://www.w3.org/TR/json-ld11/> |
| JSON Canvas open format | <https://jsoncanvas.org/spec/1.0/> |
| Obsidian Properties | <https://obsidian.md/help/properties> |
| Obsidian Bases | <https://obsidian.md/help/bases> |
| Obsidian Bases syntax | <https://obsidian.md/help/bases/syntax> |
| Obsidian Graph | <https://obsidian.md/help/plugins/graph> |
| Obsidian Canvas | <https://obsidian.md/help/plugins/canvas> |
| Obsidian CLI | <https://obsidian.md/help/cli> |
| Obsidian license overview | <https://obsidian.md/license> |

Before court admission, verify the pinned commits again, retain content digests,
retrieval receipts, and licenses, extract atomic claims/counterclaims, and record
unavailable immutable versions or byte digests as explicit obligations. Pin or archive
the mutable documentation pages as well. The OpenTelemetry GenAI convention remains
Development at the pinned commit, so its adapter contract must name that version
explicitly.

---

## 15. OODA, War Room, and Armory

### OODA

Use OODA as an explicit resumable control loop:

- **Observe:** collect versioned repository, user, runtime, external, memory,
  token/resource, and prior-outcome evidence.
- **Orient:** apply relevant expert lenses, policy, history, uncertainty, risks, and
  prior opportunities; detect stale memory, loops, and budget pressure.
- **Decide:** select a bounded, adjudicated hypothesis with budget, owner, acceptance
  criteria, purpose attribution, stop condition, and rollback.
- **Act:** execute only through leased capability, policy, receipts, and independent
  validation while emitting granular usage and progress events.

Persist each transition. Prevent skipped phases, stale orientation, unbounded cycling,
self-approval, and repeated ideas. Show OODA state, memory inputs, progress delta,
token/cost burn, loop signals, and latency in the War Room.

### War Room

The War Room is a projection and coordination interface, not the authority. It should
make visible:

- desired outcome and current mission state;
- active roles and independence;
- OODA phase;
- evidence and source coverage;
- court cases, verdicts, dissent, and appeals;
- plans, dependencies, budgets, leases, and deadlines;
- proposed and executed actions;
- receipts, tests, risks, blockers, and rollback;
- ideas, duplicate relationships, experiments, and outcome measures;
- memory records used, ignored, stale, contradicted, or quarantined;
- per-agent token, cost, context, latency, progress, and effectiveness;
- champion/challenger fairness, outcome attribution, loops, and quarantine;
- a replay cursor for reconstructing the exact sequence;
- stale data and last-update digest.

Obsidian is the primary human-friendly War Room and institutional-memory surface. Its
views must reconcile to the open canonical ledger and remain usable through other
tools.

### Armory

Do not invent what “Armory” means. First identify and pin the exact source the user had
in mind, including URI, version or commit, retrieval time, digest, license, atomic
claims, counterclaims, and source availability.

Until adjudicated, treat “Armory” only as a provisional architectural metaphor for a
governed catalog of versioned agents, skills, tools, workflows, prompts, host adapters,
tests, provenance, compatibility, trust state, and rollback. Do not silently copy an
external implementation or claim parity.

---

## 16. Portable operation across Codex, Claude Code, Hermes, and future hosts

Answer the original portability question through architecture and conformance:

```text
Can the same governed mission, role, skill, evidence, and policy contracts be projected
into a host without changing their meaning or weakening their controls?
```

Keep replaceable:

- model/provider;
- tool transport;
- storage and memory;
- scheduler;
- Git and repository service;
- research/browser;
- courtroom and evaluator;
- sandbox;
- UI and War Room;
- host-specific prompt and configuration format.

For each host adapter or projection, declare and test:

- supported versions and discovery mechanism;
- prompt/system-instruction mapping;
- tool and permission model;
- agent/subagent model;
- context and memory limits;
- skill/plugin format;
- event, cancellation, retry, and timeout semantics;
- native token/usage fields, tokenizer behavior, provider accounting semantics,
  telemetry export, and budget enforcement;
- working-directory and filesystem behavior;
- secrets and identity behavior;
- receipt and provenance capture;
- unsupported capabilities and degradation behavior;
- installation, update, migration, rollback, and uninstall;
- conformance results against the canonical contracts.

The core must fail closed when a host cannot represent a required authority,
independence, evidence, or rollback invariant. A JSON profile alone is not host
support. Obsidian begins as a workbench/projection, not as an execution adapter.

---

## 17. Safe autonomous addition of a new agent or skill

Make extensibility easy without allowing self-authorized capability growth.

Distinguish:

- a new agent implementation or specialist, which normally binds to one of the eight
  existing constitutional roles and inherits that role's authority ceiling; from
- a proposed ninth constitutional role, which changes lifecycle completion semantics
  and cannot be added by an ordinary extension package.

A new constitutional role requires its own constitutional ADR and court, Role/lifecycle
and schema migration, compatibility and completion tests, independent review, and
explicitly authorized promotion. Discovery of a useful specialist is not authority to
expand the constitutional role enum.

A candidate extension lifecycle should be:

```text
discover need
  -> search existing catalog and idea ledger
  -> capture source/provenance/license
  -> open atomic court case
  -> define typed contract and authority request
  -> scaffold an inert, versioned challenger
  -> validate schema, digest, dependencies, and compatibility
  -> run isolated unit/contract/security/behavioral evaluations
  -> obtain independent Curator and Judge receipts
  -> install in quarantine
  -> shadow/canary under explicit lease
  -> compare outcomes and regressions
  -> independently promote, defer, reject, or roll back
```

Required properties:

- duplicate detection before creation;
- individual canonical files with generated projections;
- no arbitrary code execution during discovery or installation;
- compatible-license and source-completeness checks;
- dependency and capability closure;
- declared memory read/write, retention, sensitivity, and retrieval boundaries;
- declared token/cost/time/tool budgets and usage-accounting compatibility;
- loop, progress, effectiveness, and quarantine signals;
- signed or otherwise authenticated approval when that infrastructure exists;
- atomic install and rollback;
- immutable previous champion;
- no extension may alter the constitution, policy, evidence burden, evaluator, or its
  own promotion path;
- all failures and losing challengers remain available for learning and appeal.

The OS may propose and build a new agent or skill within authority. A separate identity
must validate and promote it. An extension that cannot produce trustworthy memory,
usage, outcome, and rollback receipts remains inert or quarantined.

---

## 18. Recommended delivery sequence

### Phase 0 — Restore a trustworthy baseline

1. Update from `main` and reproduce the GitHub CI failures.
2. Court and fix the unittest/pytest contract mismatch in a small isolated delivery.
3. Open a separate obligation for required-check/branch-protection failure.
4. Make the isolated repair PR green before beginning the redesign implementation.
5. Run the exact full test, lint, type, and wheel/resource verification.
6. Complete the pending independent Steward, Curator, and Judge receipts.
7. Keep unsupported and incomplete claims blocked.

### Phase 1 — Court and characterize the redesign

1. Open separate Obsidian-brain, memory, usage-telemetry/fair-learning, and
   agent-system court records.
2. Preserve the user's request as atomic claims.
3. Pin and docket the official/primary research sources in this handoff.
4. Audit every duplicated or live role/agent/skill/prompt field.
5. Inventory every current memory, event, token/usage, model-call, and host-telemetry
   path, including gaps and provider semantics.
6. Capture generation-zero behavior, public APIs, stored state, digests, and package
   resources as golden compatibility fixtures.
7. Write architecture, threat, privacy, migration, rollback, observability, and
   evaluation ADRs.

### Phase 2 — Additive memory and telemetry foundation

1. Design additive v2 role, agent, skill, prompt-composition, typed-output, and
   opportunity-record contracts plus repository identity, memory record, usage event,
   decision/outcome attribution, budget lease, loop signal, and quarantine records.
2. Keep v1 and current runtime behavior available.
3. Add deterministic generation and drift tests.
4. Implement the append-only idea ledger and staged, concurrent duplicate
   classification.
5. Add provider-native attempt/usage receipts, orthogonal normalized token dimensions,
   per-axis reconciliation invariants, and adapter conformance fixtures.
6. Add a local transactional outbox/WAL, low-cardinality metrics, correlated traces,
   privacy defaults, crash recovery, and invoice completeness reconciliation without
   requiring an outbound service.

### Phase 3 — Open brain and Obsidian cognitive layer

1. Implement a portable per-repository memory pack and deterministic projection with a
   CLI/editor-only path.
2. Separate safe public memory from private/sensitive runtime records.
3. Add HOME, idea, evidence, court, run, agent, and telemetry notes using stable IDs
   and properties.
4. Generate core Obsidian Bases and JSON Canvas views for ideas, War Room, agent
   scorecards, token/value accounting, loops, and quarantine.
5. Test repository-as-vault automatic refresh.
6. Test multi-repository federation, tenant isolation, and self-host recursion guards.
7. Add governed Inbox intake only if separately required.
8. Do not require a community plugin, paid Sync, or Obsidian itself to access the
   memory.

### Phase 4 — Explorer vertical slice in shadow mode

1. Build reusable discovery skills.
2. Build Explorer v2 from the canonical layers.
3. Add progressive, receipted memory/context selection.
4. Run duplicate, bug, serendipity, cross-domain, provenance, injection, authority,
   stopping, loop, token-attribution, and memory-contamination tests.
5. Track every idea from observation through relationship, court, experiment, and
   outcome in the brain.
6. Compare with generation zero under equal evidence and budgets.
7. Do not activate it until independent adjudication.

### Phase 5 — Remaining roles and skill library

1. Give each of the other seven roles its own deep playbook and typed outputs.
2. Reuse skills where appropriate without merging authority.
3. Add role-specific behavioral, resource, loop, and effectiveness suites.
4. Migrate one reversible champion at a time.

### Phase 6 — Fair learning, loop control, and quarantine

1. Add hierarchical token/cost/time/tool leases with checkpoint reserves.
2. Add progress fingerprints, loop/stall detectors, and staged circuit breakers.
3. Add scoped, receipted, appealable quarantine and rehabilitation.
4. Add absolute champion fitness, relative challenger, uncertainty, and
   post-promotion gates.
5. Seal holdouts, future commits, memory packets, identities, budgets, and access
   logs.
6. Test that champions can fail, challengers can win, inconclusive evidence cannot
   promote, and learning packets cannot leak held-out answers.

### Phase 7 — Host projections and conformance

1. Generate Codex, Claude Code, Hermes, and future host artifacts from canonical data.
2. Normalize each host/provider's usage, model identity, budget, session, tool, and
   telemetry semantics without double counting.
3. Build real adapters only where required.
4. Run host conformance and degradation tests.
5. Keep every unverified host marked unsupported.

### Phase 8 — Independent delivery court

1. Run full regression and behavioral benchmarks from the exact candidate commit.
2. Reconcile usage events, projections, and any available provider invoice data.
3. Rebuild and clean-install the wheel.
4. Verify package resources, manifests, digests, memory migrations, telemetry
   mappings, privacy, and rollback.
5. Obtain separate Curator, Steward, Expert, and Judge receipts.
6. Open a draft PR.
7. Promote claims or implementation only to the level supported by the evidence.

Prefer multiple reviewable pull requests over one unreviewable rewrite.

---

## 19. Required acceptance criteria

The program is not complete until evidence shows:

- no existing supported public behavior, lifecycle stage, resource, provenance record,
  safety control, or rollback path was silently lost;
- the exact full CI contract is green in clean declared environments;
- duplicated authoritative prose and data are reduced and measured;
- each concept has one canonical authority and deterministic projections;
- drift tests fail when generated artifacts diverge;
- all eight roles have distinct, deep, independently testable behavior;
- skills are reusable bounded procedures with typed I/O and authority declarations;
- prompts are composed from versioned layers and evaluated behaviorally;
- context selection cannot silently remove critical blockers, dissent, authority, or
  provenance;
- Explorer finds both obvious defects and non-obvious opportunities;
- Explorer performs source-bound research, cross-domain synthesis, counterargument,
  serendipity capture, and honest stopping;
- exact duplicate ideas are deterministically prevented even under concurrent
  discovery, and repeated evidence attaches to the existing record;
- semantic duplicate escape and false-merge rates are bounded, measured, and
  appealable rather than falsely claimed to be zero;
- duplicates become corroboration, refinement, contradiction, or appeal records
  rather than disappearing;
- idea false merges have an appeal path;
- every Explorer candidate is traceable from origin and sources to its canonical
  relationship or explicit disposition, and every developed opportunity continues
  through court, implementation, experiment, and measured outcome where applicable;
- every filtered, duplicated, abandoned, invalid, non-material, or policy-blocked
  Explorer candidate has a durable encounter record and explicit relationship or
  disposition;
- every material mission action, decision, handoff, failure, and learning has a stable
  memory record or explicit not-applicable disposition;
- the open memory pack works through CLI and ordinary Markdown/YAML-capable tools
  without Obsidian, an account, paid service, or community plugin;
- Obsidian provides first-class brain, memory, query, relationship, War Room, replay,
  and knowledge-gardening views over the same open records;
- public and private memory, repositories, and tenants remain isolated;
- multi-repository federation and OS-on-itself execution cannot create ingestion,
  projection, telemetry, idea, or delegation loops;
- every model call has a granular usage record or explicit unknown-accounting failure;
- input, output, cache, reasoning, modality, tool, cost, latency, model, timestamp,
  agent, idea, case, purpose, budget, and progress fields are normalized without
  double counting;
- champion/challenger percentages separate evaluation arm from debate stance,
  declare denominators and unknown share, and survive later appeals without rewriting
  history;
- rejected work is separated into productive falsification, safety, reusable learning,
  and independently supported avoidable waste;
- every role has effectiveness, quality, safety, customer-value, and resource
  scorecards rather than one gameable rank;
- hard resource leases stop safely, loop/stall signals escalate proportionally, and
  quarantine is scoped, receipted, appealable, and reversible;
- champions can fail absolute fitness gates, challengers can win fair comparisons, and
  inconclusive evidence cannot promote either side;
- sealed holdouts, target/future commits, private reasoning, hidden answers, and
  forbidden memory cannot leak into candidate learning;
- local telemetry works without outbound collection, and high-cardinality or sensitive
  content is excluded from metric labels;
- autonomous extension creation is inert, quarantined, evaluated, independently
  promoted, and reversible;
- OODA state is durable and resumable;
- War Room and Obsidian views are cognitive projections over the open canonical brain,
  not competing truth stores;
- the no-code Obsidian workflow works and its automatic local refresh is documented;
- no Obsidian plugin or importer is added without a proven need;
- remote Git synchronization is not misrepresented as automatic Obsidian behavior;
- `.obsidian` files follow an explicit safe policy;
- every supported host passes versioned conformance tests;
- full tests, Ruff, Pyright, wheel installation, resource verification, threat tests,
  migrations, rollback, ADRs, and independent judgments have exact receipts;
- unavailable sources and unsupported claims remain explicit blockers.

### Compatibility proof

Before replacing any generation-zero path:

- snapshot exact current outputs and digests;
- provide additive schema migration;
- demonstrate deterministic regeneration;
- test rollback to the prior champion;
- preserve old prompts and evaluation history;
- compare candidate and champion on held-out tasks;
- obtain independent approval.

“No functionality lost” requires executable parity and regression evidence, not
confidence or prose review.

---

## 20. Explicit non-goals and prohibited shortcuts

Do not:

- rewrite all files before repairing red CI;
- equate a longer prompt with a stronger agent;
- use role descriptions as skills;
- maintain the same mission in Python, agent JSON, skill JSON, prompt JSON, and text
  by hand;
- activate inert package code merely because it validates structurally;
- install an Obsidian plugin when opening the folder already works;
- require Obsidian, Obsidian Sync, a paid account, or a hosted telemetry service to use
  or recover the OS;
- make Obsidian's cache, Bases, Graph, Canvas, Markdown projection, embeddings, or a
  vector index the only canonical truth;
- store secrets, private hidden chain-of-thought, raw prompts, user data, or private
  repository content in a public memory pack;
- treat a generated brain note as new external evidence;
- let OS-on-itself runs recursively ingest their own projections or telemetry;
- silently drop a repeated idea;
- claim exhaustive exploration;
- let semantic similarity erase contradictions or refinements;
- sum inclusive cache/reasoning totals and exclusive usage buckets together;
- fabricate token counts or exact purpose percentages when providers or runtime spans
  cannot support them;
- optimize agents for low token count, survival, approval, objection, or quarantine
  avoidance;
- label all rejected work as waste;
- quarantine or demote a component permanently based only on token volume;
- expose live scoreboards, future commits, holdout answers, or Judge decisions to an
  agent that can optimize against them;
- retain a failing champion merely because no challenger passed;
- promote a challenger merely because the champion failed;
- let an Explorer write code or approve its discovery;
- let an agent create, judge, and promote its own extension;
- hide provider-specific semantics in the core;
- invent unavailable source content or Armory semantics;
- weaken tests, policy, evidence, or release gates;
- mark Codex, Claude Code, Hermes, or Obsidian supported based only on manifests;
- claim production readiness, full autonomy, source completeness, or superiority
  without the required evidence.

---

## 21. Expected deliverables

Deliver reviewable artifacts, in the appropriate phase, including:

1. a small CI contract repair with exact receipts;
2. a required-check/branch-protection finding, with an in-scope hardening change or an
   explicit administrator action request;
3. separate court records for the Obsidian/open-brain, memory, telemetry/fair-learning,
   and agent-system redesigns;
4. a duplication/reachability inventory and golden behavior fixtures;
5. ADRs covering canonical definitions, prompt composition, skill contracts, open
   memory, usage accounting, privacy, fair evaluation, threat model, migration,
   rollback, and host portability;
6. additive repository, memory, opportunity, usage, outcome-attribution, budget,
   loop, quarantine, role, skill, prompt, and output schemas;
7. an append-only work-history and opportunity ledger with exact and semantic
   deduplication;
8. a portable public memory pack plus separated private state and deterministic
   projection;
9. Obsidian HOME, Properties, Bases, Graph/link, Canvas/War Room, replay, agent, idea,
   court, and telemetry surfaces using core features;
10. a beginner Obsidian guide and explicit `.obsidian`, privacy, Sync, and plugin
    policy;
11. provider-native attempt/usage receipts, orthogonal token normalization,
    per-axis and invoice reconciliation, a transactional local outbox/WAL, and
    OpenTelemetry-compatible adapters;
12. agent/role/idea/court token-value dashboards and outcome-attribution matrices;
13. hierarchical leases, loop/stall circuit breakers, scoped quarantine, and fair
    champion/challenger evaluation;
14. Explorer v2 plus reusable discovery skills, durable idea memory, and held-out
    evaluations;
15. equally robust implementations, memory behavior, resource scorecards, and
    evaluations for the other seven roles;
16. progressive context/memory manifests and behavioral prompt evaluation;
17. multi-repository federation and self-host recursion controls;
18. optional governed Obsidian Inbox intake only if justified;
19. host projection, usage-normalization, and conformance matrix;
20. full test, lint, type, wheel, resource, security, privacy, telemetry, migration,
    rollback, and
    independent review receipts;
21. a new draft PR whose description clearly separates proven functionality from
    deferred or quarantined claims.

At every checkpoint, leave a durable handoff containing exact commit, branch, state,
receipts, blockers, dissent, and next action. Do not require the next person or agent
to reconstruct the mission from chat history.

## End of copy-ready prompt
