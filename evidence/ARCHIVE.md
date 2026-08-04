# Historical execution evidence

P5.1 removed the historical phase-execution corpus from `main` without deleting it.
The complete 968-file corpus is preserved by the immutable
`archive/evidence-corpus-2026-08-03` tag and the
`archive/p5-1-evidence-corpus` branch.

To inspect it locally:

```bash
git fetch --tags origin
git switch archive/evidence-corpus-2026-08-03
```

The archive retains `audits`, `benchmarks`, `experiments`, `handoffs`, `live`, and
`pit` evidence roots exactly as they were before removal. Current courtroom,
governance, and source-provenance evidence remains in this directory on `main`.
