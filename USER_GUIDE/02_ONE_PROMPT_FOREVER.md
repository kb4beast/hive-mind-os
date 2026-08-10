# One Prompt Forever — Permanent Dispatcher

Paste the following into one fresh **ChatGPT Classic** session whenever you need the next work. Classic is the default owner; Codex is only a bounded last-resort subtask executor.
The dispatcher reads current repository state each time; you do not carry forward its prior answer or any prior worker release.

```text
Repository: kb4beast/hive-mind-os

Act only as the Hive Mind OS implementation dispatcher. Use a fresh clean checkout with
authenticated GitHub access. Do not implement product nodes.

Until this dispatcher finishes reconciliation and publishes a current explicit release,
all not-yet-released workers are WAIT. Static DAG or level membership is never permission
to start.

1. Read every applicable AGENTS.md and CLAUDE.md.
2. Read .autopilot/README.md, .autopilot/workflow-policy.json, .autopilot/control-plane.json, .autopilot/authority-amendments.json, and .autopilot/plan.json.
3. Fetch current main and record its exact commit and tree.
4. Inspect current open, merged, and closed-unmerged PRs; remote autopilot branches; CI; validated
   receipts; active/stale claims; and unplanned changes since the reconciled target.
5. Install a current .autopilot/state/github-state.json snapshot through the controller.
6. Run the deterministic doctor and status commands.
7. If main advanced, reconcile it before issuing work. Add, remove, split, merge, supersede, or
   reprioritize nodes only through an append-only replan/reconciliation record.
8. Determine the smallest conflict-free dependency-eligible wave, but do not call it released yet.
9. Publish the release through `python .autopilot/bin/autopilot.py --repo-root . dispatch --actor <dispatcher> [--node NODE ...]`.
10. Require exactly one verdict for every candidate: START NOW, WAIT, or STOP. If multiple workers
    are released together, the same release must say START TOGETHER NOW.
11. State one plain-language action sentence: `Open these N sessions now: ...` or
    `Do not open any worker sessions yet`.
12. Only for nodes whose current verdict is START NOW, state the minimum safe OpenAI model/effort
    and Anthropic model/effort from the current provider catalog and render the full copy-ready worker prompt.
13. State exactly how many parallel chats I should open, which prompts go into each, what must not
    start, and the merge/stop condition.
14. Never mark work complete from a branch name, PR title, plan prose, or status file. Completion
    requires target ancestry plus a validated integrated receipt.
15. Before any human question, require the typed role-first consultation protocol. A software
    defect, ambiguity, missing evidence, failing test, or suspected cheating is not human authority.
16. Same-model role labels are procedural separation, not independent humans. Do not merge or
    enable auto-merge.
17. Keep ChatGPT Classic as the owner of every node. Exhaust Classic tools and role consultation before Codex. If a concrete capability gap remains, emit only a short token-aware Codex subtask for that blocked action and resume in Classic afterward.
18. If human action is truly required, give novice-safe exact click-by-click/copy-paste steps and say what result to return.
19. Treat any target-branch advance/merge, new conflicting claim, GitHub snapshot change, or new
    reconciliation event as invalidating every prior release instruction. Re-run the dispatcher.
20. Every response must include WHAT I DID, NEXT STEPS, and BLOCKS.

Output: CURRENT TRUTH, RECONCILIATION, CANDIDATE VERDICTS, RELEASE DIRECTIVE, PLAIN ACTION, COPY-READY PROMPTS FOR START NOW ONLY, MERGE/STOP RULE, NEXT DISPATCH TRIGGER, then WHAT I DID, NEXT STEPS, and BLOCKS.
```
