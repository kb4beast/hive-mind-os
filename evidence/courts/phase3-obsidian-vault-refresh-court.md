# Court record: Phase 3 item 5 Obsidian vault refresh

- Case: `P3-OBSIDIAN-REFRESH-001`
- Disposition: pending
- Subject implementation: `fadf6e1b386eba61168c753b3cdab3d94503430f`
- Runtime: Obsidian Desktop `1.12.7`, Windows `10.0.26200`

## Claims

| Claim | Evidence | Disposition |
|---|---|---|
| Core Obsidian reflects item-1 external replacement in an already-open pane. | Third run, count `6 -> 7`, `5.601962s`. | pending |
| Core Obsidian reflects item-3 external replacement in an already-open pane. | Third run, total `7 -> 8`, `5.975783s`. | pending |
| Core Bases recomputes after a new generated idea note appears. | Third run, `1 -> 2` rows, `5.145992s`. | pending |
| The generated Canvas parses and renders embedded Bases. | Third-run Canvas screenshot and preserved target bytes. | pending |
| Generated item-4 bytes remain owned after runtime observation. | Third run unloaded Canvas, waited `329.74131s`, preserved all four target files, and returned item-4 `unchanged`. | pending |
| The behavior generalizes to other hosts, versions, profiles, Git remotes, or Sync. | No evidence. | defer |

## Advocate

The Explorer and Architect supported a real-projector, disposable-vault black-box
test. The candidate protocol binds visible outcomes to projector timestamps and
hashes and uses no plugin or watcher.

## Cross-examination

The first run disproved the initial integrity claim when Obsidian canonicalized Base
YAML. The second run's immediate check was also insufficient: Obsidian rewrote the
Canvas about four minutes later. Both losses remain append-only evidence. The third
run unloaded Canvas and survived the 300-second stability interval, but independent
roles must still reproduce the final candidate before judgment.

Remaining weaknesses:

- the Obsidian process and user profile predated the run;
- no official refresh latency guarantee exists;
- screenshots prove only the recorded host and fixture; and
- `.obsidian` and vault registration are local side effects, not product state.

## Independent roles and judgment

Cross-Examiner, Curator, Steward, Expert Witness, and distinct Judge identities will
be recorded only after the third run and final candidate bytes exist. Until then,
judgment is pending and no passing conformance claim is admitted.
