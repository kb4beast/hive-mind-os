"""Bind retained reproduction artifacts to actual immutable Git objects."""
import hashlib
import json
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parent
receipt = json.loads((root / "RESULTS.json").read_text(encoding="utf-8"))
tree = subprocess.check_output(["git", "-C", r"C:\h\continuity-draft1", "ls-tree", "-r", receipt["subject_commit"]]).decode()
objects = {}
for line in tree.splitlines():
    metadata, path = line.split("\t", 1)
    objects[path] = metadata.split()[2]
for row in receipt["source_manifest"]:
    assert objects[row["path"]] == row["git_blob"]
    assert hashlib.sha256((root / "baseline" / row["path"]).read_bytes()).hexdigest() == row["sha256"]
files = [root / name for name in ("REPORT.md", "RESULTS.json", "reproduce.py", "SETUP-ATTEMPT-1.txt", "seal.py")]
files += sorted((root / "inputs").rglob("*")) + sorted((root / "outputs").rglob("*"))
artifacts = [{"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": len(path.read_bytes()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files if path.is_file()]
manifest = {"schema_version": 1, "reviewer": "/root/delivery_curator", "subject_commit": receipt["subject_commit"], "subject_tree": receipt["subject_tree"], "status": "reproduced", "probes": 15, "actual_git_blob_comparisons": len(receipt["source_manifest"]), "all_blob_and_source_byte_checks_passed": True, "artifacts": artifacts, "source_manifest_location": "RESULTS.json#/source_manifest", "no_full_suite_or_execution_authority_claim": True}
(root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest_sha256": hashlib.sha256((root / "MANIFEST.json").read_bytes()).hexdigest(), "verified_blobs": len(receipt["source_manifest"]), "artifacts": len(artifacts)}, indent=2))
