# Phase 3 item 6 migration and rollback

## Preconditions

- Keep the stacked PR draft, open, unmerged, and inactive.
- Supply two or more independently generated item-3 cognitive namespaces.
- Confirm every source belongs to the intended tenant.
- Use a separate portfolio vault; never nest source and portfolio vaults.
- Run `check` before granting the bounded local write.

## Check

```powershell
python -m hive_mind_os.foundation.federation check `
  --source C:\vault-a\hive-mind\generated-cognitive `
  --source C:\vault-b\hive-mind\generated-cognitive `
  --portfolio-vault C:\portfolio-vault `
  --tenant tenant-id `
  --portfolio-repository-id portfolio-id
```

Check mode reads and validates sources but creates no portfolio. A successful result
reports desired manifest and tree digests.

## Projection

Run the command with `project`. It creates only
`hive-mind/federated-cognitive` beneath the portfolio vault and does not modify
sources, `.obsidian`, canonical stores, public stores, or protected state.

An exact rerun reports `unchanged`. Differing or unmanaged existing bytes fail
closed; this version does not update or delete a portfolio namespace.

Any `.federation-*` staging directory indicates interrupted work. Preserve and
inspect it; the projector refuses another write until the operator moves it out of
the target parent under normal recoverable-file policy.

## Rollback

1. Stop invoking the federation module.
2. Preserve its manifest and failure evidence.
3. Confirm the exact managed root, then move
   `hive-mind/federated-cognitive` out of the portfolio or remove that generated
   namespace under the operator's recoverable-file policy.
4. Leave source vaults and canonical/public/protected stores untouched.

No schema migration or database downgrade is required. Atomic first publication
assumes staging and final paths share a filesystem and the platform supports
no-replace rename. It is not a durability/fsync guarantee. Manual drift, concurrent
writers, deletion, private data, and remote synchronization require a later court.
