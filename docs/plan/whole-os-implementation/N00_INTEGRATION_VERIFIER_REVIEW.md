# N00 integration verifier review

## Verdict

**ADAPT** for reviewed commit
`eccfc7b51363aa79afe5b087688c9f3362f270e6`.

The default verifier mode now validates the immutable N00 local-source snapshot
from Git objects instead of requiring those files to remain byte-identical in the
later checkout. It reproduced all 53 recorded blobs under pinned commit
`d980a9cfe39f68b3de86ea0530234b3ab4e91390` and its recorded tree, and it
reproduced all five ADR blobs under handoff commit
`3dc87ad0749ee468ed7ceab779d92c9446248b7e`. The optional live-checkout mode
correctly rejected current intentional source drift. One requested failure-mode
property remains open: a nonzero `git hash-object` exit can be masked in the live
path when the command also emits the expected blob text, because that invocation
does not check its exit status.

This verdict accepts the point-in-time default-mode integration but does not
accept the verifier as fully closed until the live-path Git failure is repaired
and regression-tested.

## Identity and provenance

The review used a fresh worktree at `C:\h\wos-n00-integration-review` and branch
`codex/whole-os-n00-integration-review`, created directly from the reviewed
commit. Observed identity:

- reviewed commit: `eccfc7b51363aa79afe5b087688c9f3362f270e6`
- reviewed parent: `80dd0c32db32374b2479ba2c88d4cc4d54ccde30`
- reviewed tree: `be372ed5f9b10f41acc642184f805c7c344be0bf`
- verifier SHA-256:
  `506d597d4f731f40f6192a8a1208ce7495f0cd65421d252b416df608b8c3b531`
- handoff `MANIFEST.json` SHA-256:
  `ffd07199c043d8825aaaf53588b0be31ad96238da07d9648a6b9a9a88636e5f5`
- handoff `local-source-manifest.json` SHA-256:
  `4951e6baa893cfefcd9e9f199b11236fc7347e4c690a0a0cd0e322222ea4f5c1`
- candidate `source-inventory.json` SHA-256:
  `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`

`git diff --name-only HEAD^ HEAD` named only
`docs/plan/whole-os-implementation/verify_n00.ps1`, and
`git diff --check HEAD^ HEAD` exited 0. Both the local-source commit and the
handoff commit are ancestors of the reviewed commit.

## Reproduction evidence

Commands were run from the fresh worktree with Windows PowerShell 7 as the
outer shell and Windows PowerShell (`powershell -NoProfile`) for the canonical
verifier execution.

```powershell
powershell -NoProfile -File docs/plan/whole-os-implementation/verify_n00.ps1
```

Exit 0. The emitted receipt was `PASS` with `local_source_mode` equal to
`pinned_snapshot`, 15 handoff-manifest files, 53 local-source paths, 32 successor
sources, 15 founding sources, 18 requirements, 34 nodes, and 34 symbol
classifications. `git status --porcelain=v1` was empty immediately before and
after execution.

```powershell
powershell -NoProfile -File docs/plan/whole-os-implementation/verify_n00.ps1 `
  -RequireLiveCheckoutMatch
```

Exit 1 with `live local source drift:
src/hive_mind_os/tournament_plan_factory.py`. The worktree was clean before and
after execution. Independent comparison of the pinned commit to the reviewed
checkout found three changed paths from the 53-entry local-source set:

- `src/hive_mind_os/portable_plan.py`
- `src/hive_mind_os/runtime_contracts.py`
- `src/hive_mind_os/tournament_plan_factory.py`

Thus the default mode tolerates the intended later implementation changes while
the explicit live mode rejects them.

An independent loop ran `git rev-parse <commit>:<path>` for all 53 local-source
entries and found zero missing paths or blob mismatches. It also observed:

- expected and actual pinned tree:
  `47f873cf5924b97cfafafe1b9dfb0a450acb2e92`
- ADR-074 expected/actual blob:
  `db3b569c5ce5b4119c598483b149c01f0b5d6816`
- ADR-075 expected/actual blob:
  `2acfa99990c57bf640f61546ded38eaf7eedf655`
- ADR-076 expected/actual blob:
  `feda9c742b00af58086f260e5ad494795730042f`
- ADR-077 expected/actual blob:
  `31f86c0c70d415bd3046aa1197e5c5e7ba86a9e1`
- ADR-078 expected/actual blob:
  `e13d2f3eabf16a1a9024b5cfa09e6f8a3cc06909`

## Adversarial checks

I installed an in-process PowerShell `git` function for each invocation which
delegated every unmodified request to the real `git.exe` but injected one exact
failure or substitution. This changed no repository file. Each `attack_hit`
flag was checked to ensure that the intended command, rather than another gate,
was exercised.

| Attack | Observed result |
| --- | --- |
| pinned commit missing, exit 128 | rejected: `missing pinned local-source commit` |
| pinned commit resolves to substituted tree | rejected: `wrong pinned local-source tree` |
| pinned `AGENTS.md` path missing, exit 128 | rejected: `missing pinned local source` |
| pinned `AGENTS.md` returns another valid blob | rejected: `wrong pinned local source blob` |
| handoff ADR-074 path missing, exit 128 | rejected: `missing pinned ADR source` |
| handoff ADR-074 returns ADR-075 blob | rejected: `wrong ADR blob` |
| tree lookup exits 128 but prints the expected tree | rejected on exit status |
| ADR lookup exits 128 but prints the expected blob | rejected on exit status |
| stale prior `$LASTEXITCODE = 137`, then real Git succeeds | default verifier passed; successful Git refreshed status to 0 |
| tree lookup exits 128 with no output | rejected fail-closed, but as a null `.Trim()` exception rather than the typed commit error |
| live `hash-object AGENTS.md` exits 128 but prints the expected blob | **failure masked**; execution continued until the unrelated intentional drift in `tournament_plan_factory.py` |

The last attack ended with `$LASTEXITCODE` 0 because later successful Git calls
overwrote the injected failure. It therefore demonstrates the missing immediate
status check rather than merely a confusing final status. On this checkout the
later content drift still prevents a false overall pass; on a checkout whose
live files all match, the injected failing command with valid-looking output
would pass that gate.

## Required correction

After the live-path `git hash-object` invocation, capture and validate the exit
status before accepting or comparing its output. Prefer the same ordering for
all Git calls: retain raw output, immediately retain `$LASTEXITCODE`, require a
zero status, and only then normalize/compare the output. This also turns a
no-output Git failure into the intended typed verifier error instead of a null
method exception.

Add focused negative tests for both forms of Git failure:

1. nonzero exit with valid-looking expected stdout; and
2. nonzero exit with no stdout.

No change is required to the pinned commit/tree/blob strategy itself.

## Independence and limits

This was an independent Curator rereview in a fresh exact-commit worktree. I did
not edit the verifier, manifests, inventory, implementation, or tests. The only
review-side repository change is this append-only report. The command shim is an
adversarial control, not evidence that the host Git executable is compromised.
The review was intentionally scoped to `verify_n00.ps1`; it does not rejudge the
rest of N00 or claim full-campaign acceptance.
