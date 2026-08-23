# Builder receipt: CONTINUATION-3060 exact-source full repository CI

## Candidate binding

- Repaired implementation candidate: `1aa731f58b2d97eae65782b2d79685cefd2ae333`
- Implementation tree: `7762abb323b8e108036a5ba20cfac1353d115041`
- Plan-document head tested: `f5402b9b170ddab5373b7823da6cc1e589342150`
- The diff from the implementation candidate through the tested head contains only
  Builder evidence and successor-plan documentation. It changes no launcher,
  controller, test, ADR, or `AGENTS.md` implementation path.

## Full gate

The required repository CI gate was run in a clean local execution environment after
removing inherited `GIT_*` variables, which otherwise cause the repository's
point-in-time explorer guard to deny its own Git inspection. This environment cleanup
does not alter code, test configuration, policy, or acceptance criteria.

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' } | ForEach-Object {
    Remove-Item -LiteralPath ("Env:" + $_.Name)
}
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

Result: **1,115 passed; 7 Windows symlink-capability skips; 0 failures and 0 errors**
in **1021.349 seconds**.

## Interpretation and boundary

The earlier unsanitized attempt is not a candidate failure: inherited Git variables
correctly triggered the existing explorer fail-closed guard before the repository gate
could inspect history. The clean rerun above is the admitted exact-source validation
receipt. It supports only `CONTINUATION-3060`'s local implementation closure. It does
not authenticate an external owner, publish a release, unblock `ROOT-3000`, or change
the blocked status of `PROMOTION-3990`.
