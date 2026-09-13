from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

root = Path("C:/h/node-guide1")
out = Path(__file__).parent
head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]).decode().strip()
state = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"]).decode()
assert head == "6e134f6251fdd30b6da712df8342d1d8986093a5"
assert tree == "a38f5ce501198b87739743114e0e155c0bf5b080" and not state
artifacts = []
for path in sorted(out.iterdir()):
    if path.is_file() and path.name != "REVIEW-MANIFEST.json":
        raw = path.read_bytes()
        artifacts.append({"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
manifest = {"reviewer": "/root/continuity_repair_builder", "head": head, "tree": tree,
            "created_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_porcelain": state,
            "status": "revise", "artifacts": artifacts,
            "fixture_retention": "External synthetic source and clones retained as probe working data; command receipts and explicit source construction are sealed above."}
raw = (json.dumps(manifest, indent=2) + "\n").encode()
(out / "REVIEW-MANIFEST.json").write_bytes(raw)
print(json.dumps({"manifest_sha256": hashlib.sha256(raw).hexdigest(), "status": "revise"}))
