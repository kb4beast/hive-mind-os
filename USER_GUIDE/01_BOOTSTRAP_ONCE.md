# One-Time Bootstrap

1. Use a fresh checkout of current `main`.
2. Copy the contents of the bundle’s `REPO_ROOT/` into the checkout root.
3. Create branch `autopilot/boot-000`.
4. Run:

```bash
python -m compileall -q .autopilot/bin .autopilot/tests
python -m unittest discover -s .autopilot/tests -v
python .autopilot/bin/autopilot.py --repo-root . doctor --json
```

5. Commit only the declared bootstrap paths.
6. Push the branch and open a **draft** PR to `main`. Do not auto-merge.
7. After CI and review, merge manually under existing branch protection.
8. Start a fresh dispatcher session with `02_ONE_PROMPT_FOREVER.md`.

The bootstrap PR changes implementation coordination only. It must not alter Hive Mind OS product
runtime behavior.
