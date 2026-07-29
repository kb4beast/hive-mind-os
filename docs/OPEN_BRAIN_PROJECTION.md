# Portable open-brain projection

Phase 3 item 1 provides a small, offline way to turn explicitly released
safe-public Foundation memory metadata into ordinary Markdown and JSON.

```powershell
python -m hive_mind_os.foundation.brain project `
  --store C:\protected\foundation.sqlite3 `
  --repo C:\Repos\example `
  --tenant tenant-id `
  --repository-id repository-id
```

Verify without changing files:

```powershell
python -m hive_mind_os.foundation.brain check `
  --store C:\protected\foundation.sqlite3 `
  --repo C:\Repos\example `
  --tenant tenant-id `
  --repository-id repository-id
```

The public pack appears under `hive-mind/generated`. It can be read with any
Markdown/JSON-capable editor. Obsidian, an account, Sync, a plugin, an importer, a
network connection, and the existing `hive-mind` command are not required.

Treat `hive-mind/generated` as read-only. A human edit, delete, rename, unexpected
file, or stale manifest causes a visible conflict and is never silently overwritten.
Human notes may live outside that generated namespace. There is no Inbox, import, or
write-back path in this item.

Preserve the ignored `.hive-mind-projection-state` directory when you want later
updates to an existing pack. Its completion receipt is the ownership proof for a
future mutation. A clone without that state can verify or recognize an exact tree,
but a differing tree fails closed as a conflict instead of overwriting files.

The generated pack is not memory authority. The Foundation database remains canonical
and must live outside the public pack. Private/internal/quarantined memory and
protected content references are not projected.
