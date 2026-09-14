# N00 independent Curator review

Reviewed at: 2026-09-14T02:36:04Z  
Curator identity: `/root/n00_curator`  
Candidate inventory: `WOS-N00-20260914-01`  
Verdict: **ADAPT — do not seal N00 until the required corrections below are made and their hashes are revalidated.**

## Independence and scope

I did not author `source-inventory.json`, `successor-node-map.json`, `SOURCE_RECONCILIATION.md`, or `n00-validation.json`, and I did not edit them. I inspected the committed handoff and candidate independently and wrote only this review. Independence is limited because this review ran in the same shared worktree and process campaign as the Explorer candidate, not on a separately attested host or checkout. I can reproduce the current Git objects and candidate bytes, but not independently observe the worktree at the candidate's historical `2026-09-14T02:24:40Z` observation time.

## Reproduced evidence

The following candidate hashes are current and match `n00-validation.json`:

| Candidate | SHA-256 |
|---|---|
| `source-inventory.json` | `f39da4516fffcebafb200c8a76f07220cd078ad963e31ffabab81bf8f8c1c081` |
| `successor-node-map.json` | `aeb3d9dd35c28bf431a187b8aa60e51c9ea6531fb265b40f59056b12b0b6cc4b` |
| `SOURCE_RECONCILIATION.md` | `33caff42971c6343128ed7ededd48724a62cb037d37fa833b6dc9a4310b264eb` |

I executed these read-only commands (PowerShell unless noted):

```powershell
git rev-parse HEAD
git rev-parse "HEAD^{tree}"
git show -s --format='%H%n%P%n%T%n%D%n%s' HEAD
git merge-base --is-ancestor d980a9cfe39f68b3de86ea0530234b3ab4e91390 3dc87ad0749ee468ed7ceab779d92c9446248b7e
git diff --name-status d980a9cfe39f68b3de86ea0530234b3ab4e91390..3dc87ad0749ee468ed7ceab779d92c9446248b7e
git ls-remote origin refs/heads/main
git rev-list --left-right --count main...origin/main
git status --porcelain=v1 --untracked-files=all
```

Results: HEAD is `3dc87ad0749ee468ed7ceab779d92c9446248b7e`, its parent is exactly `d980a9cfe39f68b3de86ea0530234b3ab4e91390`, and its tree is `e319165996f0e8a29b758c58a026d5ebb651e561`. The ancestry check returned 0. The handoff delta is exactly the 17 added files reported by the candidate. A live `ls-remote` resolved `refs/heads/main` to `d980a9cfe39f68b3de86ea0530234b3ab4e91390`. Local `main` is `44224532dc25b94a95c3184054ec81762a258259`, an ancestor 30 commits behind `origin/main`. The tracked tree is unchanged; the candidate artifacts are untracked as expected while N00 is under review.

I recomputed the handoff manifest with this loop:

```powershell
$root=(Resolve-Path 'docs/plan/whole-os-tournament-2026-09-13').Path
$m=Get-Content -Raw "$root/MANIFEST.json" | ConvertFrom-Json
foreach($e in $m.files) {
  $f=Join-Path $root $e.path
  (Get-Item -LiteralPath $f).Length
  (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant()
}
```

All 15 entries matched both byte count and SHA-256. The manifest file itself is 2,973 bytes with SHA-256 `ffd07199c043d8825aaaf53588b0be31ad96238da07d9648a6b9a9a88636e5f5`, matching `HANDOFF-01`.

I reproduced every `local-source-manifest.json` entry with `git rev-parse "d980a9c...:<path>"` and `Get-FileHash -Algorithm SHA256 <path>`. All 53 paths exist and all 53 Git blob IDs and checkout SHA-256 values match. The local manifest is explicitly selected-path coverage, not an exhaustive repository inventory.

I parsed `requirements.json`, `dag-index.json`, `source-inventory.json`, and `successor-node-map.json` with `ConvertFrom-Json` and counted/sorted their IDs. Results:

- Handoff requirements: 18 records, 18 unique IDs, exactly R01–R18.
- Successor inventory requirements: 18 records, 18 unique IDs, the same ID set.
- Handoff DAG: 34 records, 34 unique IDs, exactly N00–N33, no missing dependency targets, and no dependency cycle found by depth-first traversal.
- Every N00–N33 ID is referenced by at least one handoff requirement.
- Successor map: 34 records, 34 unique IDs, the same ID set as the handoff DAG.
- Successor source inventory: 27 records and 27 unique IDs; obligation list: 8 records and 8 unique IDs.
- The pinned founding docket contains exactly 57 distinct claim IDs, CLM-001–CLM-057, each occurring once as a claim declaration. It also declares 15 distinct founding source IDs, SRC-001–SRC-015.

For the path classification, I extracted unique inline-code file locators from all four `NODES-*.md` files, retained repository-rooted paths beginning with `src/`, `tests/`, `docs/`, `USER_GUIDE/`, `.autopilot/`, `prompts/`, or `AGENTS.md`, and excluded directory-only locators ending in `/`. That reproduces 146 file locators. In the present candidate worktree, 53 resolve and 93 are absent; every absent locator occurs in a line labelled NEW, future, or proposed. At the committed handoff tree, before N00 created `SOURCE_RECONCILIATION.md`, the corresponding count is 52 existing and 94 absent. This explains the candidate's post-output 53/93 count and does not establish implementation of later nodes.

Spot checks also support the broad capability classification: `TaskReuseIndex` and `TestResultCache` have definitions but no production call site found outside their own modules; `RoundCapsule`/`NodeDelta`, provider routing seams, scheduler/continuity, delivery, PIT, and trusted-local sandbox primitives exist; no Roblox/Rojo product adapter exists under `src/` or `tests/`; and the sandbox explicitly disclaims hard network isolation. The successor map truthfully leaves N01–N26/N28–N29 unstarted and N27/N30–N33 blocked or dependent. `gh auth status` showed one active GitHub account, but that is not a repository-specific delivery grant. No Rojo or Roblox Studio executable resolved from the current host PATH. The candidate does not falsely mark external source archives, Roblox runtime/subject, delivery authority, benchmark evidence, or credentials as completed.

## Cross-examination findings

### F1 — available EX09–EX16 provenance was dropped (material)

`SOURCE_RECONCILIATION.md` says EX01–EX18 retain their handoff versions and digests. `source-inventory.json` does not retain the available version/body-digest fields for EX09–EX16, and weakens the recorded license identification for EX09–EX15. The handoff has the following available facts:

| Source | Version | Body SHA-256 | Recorded license identification |
|---|---|---|---|
| EX09 | `a30a8ecd0f757a23c7d5be5f91e8a4d55d87b8fc` | `721bdbe7d276625be77b2c9646bbdc217f357827bece51b76412fe54cb76d1af` | MPL-2.0 repository/README metadata; exact license archival remains open |
| EX10 | `cf66523ab47a08c149693f079265c0b093d21e34` | `d77ca5946946359537930fc62aee8816647173f0cfecab0c4b107396e10c6016` | CC-BY-4.0 documentation identification; applicable notices/archive remain open |
| EX11 | same pinned Roblox commit | `f758a1d4bb0046c7dbd4355d7f1b743cbeac38d05e1a7657195e6135e10c5dc5` | same qualification |
| EX12 | same pinned Roblox commit | `7804d7eb5db513661d916dad3b5d4e789e2504b1be663d49532162267fe3eb64` | same qualification |
| EX13 | same pinned Roblox commit | `b2062f7212c8aeed92788d0aa0622de468b49a0ac8d144985510e1940d68367e` | same qualification |
| EX14 | same pinned Roblox commit | `38d4ef5a6de2cbf7e14db7356d3758ad692d9cd39bbca578f99b146f2a608748` | same qualification |
| EX15 | same pinned Roblox commit | `d00a22aecdc0e9c937f96ba25e39a7cfc1cbd8612079aa68433e47112b0ac3fd` | same qualification |
| EX16 | mutable catalog observed 2026-09-14 UTC | `bdcf0c5e10ba9e093632db0ea41e306d7e7a58b031d784e853d8fdc70ae65816` | documentation license not established |

EX17/EX18 correctly remain without invented versions or digests. Raw-body and exact-license archival remains open for all EX records; adding the available receipts must not relabel ingestion complete.

### F2 — the explicit ADR-074–078 governing-source set is incomplete (material)

N00 requires reading ADR-074 through ADR-078 and preserving each governing source distinctly. The inherited `local-source-manifest.json` includes ADR-074 and ADR-076–078 but omits ADR-075. The successor inventory also has no distinct source records for any of these five ADRs. ADR-075 exists at the pinned baseline with blob `2acfa99990c57bf640f61546ded38eaf7eedf655` and checkout SHA-256 `18b4bbac41a1c4b262541578ed427ea4b69e68feb33b3aacd6640f0aeb7bb6c0`.

Do not alter the immutable handoff manifest. Add successor source records for ADR-074–078, including ADR-075's missing baseline custody, with their exact blob references. The other four blobs reproduce as `db3b569c...`, `feda9c742...`, `31f86c0c...`, and `e13d2f3ea...` respectively.

### F3 — founding source IDs are not retained in the successor inventory (material)

The candidate retains the CLM-001–CLM-057 range but does not retain the docket's registered SRC-001–SRC-015 source IDs. A single `GOV-DOCKET-01` record proves the docket blob is pinned; it does not satisfy the stronger acceptance statement that every registered source remains explicitly traceable exactly once. Add a `founding_sources` custody section (or individual nonduplicative source references) binding SRC-001–SRC-015 to the pinned docket blob and preserving their existing ingestion/availability state. Do not infer unavailable source contents from the docket titles.

### F4 — all 18 requirement locators are ambiguous/unresolved as repository paths

Each requirement uses `requirements.json#RNN`. Interpreted repository-relative, `requirements.json` does not exist; the actual file is `docs/plan/whole-os-tournament-2026-09-13/requirements.json`. Replace each locator with the full safe repository path (or define and validate an explicit locator base). The current source-locator check does not test requirement locators.

### F5 — source-symbol classification is too coarse to satisfy the stated N00 procedure

The grouped N01–N33 table is directionally accurate, and the 146-path count is reproducible, but neither the inventory nor `n00-validation.json` preserves the locator list or the per-symbol test/caller evidence required by N00 step 4. Add a deterministic locator/symbol classification artifact or an appendix that records, at minimum, node, locator/symbol, classification, evidence path, and test/caller (or an explicit unknown/none-found result). This must distinguish committed-baseline existence from the N00 candidate output.

### F6 — two smaller evidence wording/reproducibility corrections

- Replace “unrelated local `main`” with “stale local `main`, an ancestor 30 commits behind `origin/main`.” The current wording does not affect target selection but is factually imprecise.
- `n00-validation.json` records PASS booleans and names future negative controls but contains no command/method receipt. Preserve the deterministic command or checker version used, and make the next validation check requirement locators, the complete ADR set, EX provenance completeness, and founding source retention. The negative controls remain future checker requirements; they were not executed by the present JSON artifact.

## Required disposition

The manifest bytes, Git identity/ancestry, ID uniqueness, DAG coverage, broad path classification, and truthful external blockers are accepted. Source custody and traceability are not yet complete, and the reconciliation currently overclaims EX provenance retention. Correct F1–F5, apply the wording/reproducibility repair in F6, regenerate all candidate hashes, and obtain a fresh independent exact-candidate inspection. Until then N00 remains **ADAPT / not sealed**, and N01/N02 must not treat this inventory version as accepted input.
