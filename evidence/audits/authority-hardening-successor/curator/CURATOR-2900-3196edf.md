# CURATOR-2900 local control receipt

- Candidate commit: `3196edf00cdbb8e52388b8a98afabc8bfb833cad`
- Candidate tree: `36f477e03a803286e300e73e0d1daa88d35fbe5a`
- Baseline: `2eef403f4aaf6c482390a241e8f9952cce20e5bc`
- Curator identity: `curator_authority_audit` (separate from Builder and Architect)
- Disposition: **adopt local controls; no authority or promotion claim**

## Independent reproduction

The Curator made no implementation edits and independently ran the scoped command
below against the candidate source. It passed **143 tests, zero failures or errors**.

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_autonomous_os tests.test_hive_cortex_effects tests.test_delivery_grants tests.test_hive_cortex_delivery tests.test_github_adapter tests.test_brain_kernel_authority -v
```

The exact committed candidate then passed the repository CI gate in a clean Git
environment: **1,100 tests passed, 7 platform skips, 0 failures/errors** in
1,065.013 seconds.

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -like 'GIT_*' } | ForEach-Object { Remove-Item -LiteralPath ("Env:" + $_.Name) }
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

The interactive host supplied `GIT_PAGER=cat`; the Explorer correctly rejects such
inherited Git configuration. Removing inherited `GIT_*` from the test process is the
clean CI execution model, not a relaxation of that check. SQLite `ResourceWarning`
messages were non-failing test-hygiene observations and are retained as follow-up debt.

## Adopted local controls

- `GRANT-2010`: bare delivery-grant ledgers cannot record or spend grants; matching
  anchored provenance remains usable.
- `EFFECT-2020`: registry-less effect gateways and durable outbox `enqueue`,
  `execute`, and `reconcile` refuse otherwise-issued work.
- `LEGACY-2030`: retired direct RepositoryMission GitHub delivery stops before a
  transport call.
- `AUTONOMOUS-2040`: autonomous push, draft-PR, comment, feedback, and even the
  retired adapter's private request entry point refuse before Git or HTTP I/O.

## Dissent, residuals, and rollback

- `ROOT-3000` remains blocked: the authority registry/root ceremony is in-process,
  not an externally administered verifier or signing authority.
- `RAW-GITHUB-2070` remains pending: public raw GitHubClient side-effect APIs have
  not yet been migrated behind controlled delivery.
- `DURABILITY-2050` still needs an independent Steward verdict that separates local
  recovery behavior from external-root custody.
- Therefore `CURATOR-2900`, `JUDGE-3910`, and `PROMOTION-3990` do not complete from
  this receipt. The local candidate can be rolled back by reverting commit
  `3196edf00cdbb8e52388b8a98afabc8bfb833cad`; this receipt and all negative findings
  remain retained.
