"""Bounded Windows path primitive probe; no repository code or test execution."""
import json
import os
from pathlib import Path
import tempfile

OUT = Path(__file__).parent
ordinary = Path(tempfile.mkdtemp(prefix="path-primitives-", dir=OUT))
results = {"os_name": os.name, "fixture_directory_retained": str(ordinary), "cases": []}
for mode in ("ordinary", "extended"):
    path = ordinary / mode
    while len(str(path)) < 330:
        path /= "continuity-long-path-component"
    if mode == "extended":
        path = Path("\\\\?\\" + str(path))
    record = {"mode": mode, "path": str(path), "characters": len(str(path)),
              "abspath_preserves_prefix": str(path) == os.path.abspath(path)}
    try:
        for parent in (*reversed(path.parents), path):
            try:
                parent.lstat()
            except FileNotFoundError:
                continue
        path.mkdir(parents=True, exist_ok=True)
        marker = path / "marker.txt"
        marker.write_bytes(b"primitive path probe\n")
        alias = path / "published.txt"
        os.link(marker, alias)
        record.update(created=True, bytes=alias.read_bytes().decode(), listed=sorted(p.name for p in path.iterdir()))
    except OSError as error:
        record.update(created=False, exception=type(error).__name__, winerror=getattr(error, "winerror", None),
                      errno=error.errno, message=str(error))
    results["cases"].append(record)
(OUT / "path-probe-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, indent=2))
